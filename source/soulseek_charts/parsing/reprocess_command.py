"""Parse raw events into the normalized layer.

    python -m soulseek_charts.parsing.reprocess_command [--since=YYYY-MM-DD]
    python -m soulseek_charts.parsing.reprocess_command --incremental

Runs over `search_query_events` and writes `parsed_search_queries`. Safe to run
again: rows carry `parser_version` as their ReplacingMergeTree version, so
reprocessing with an improved parser replaces rows instead of duplicating them.

`--incremental` parses only what is newer than the latest row already parsed at
the current parser version, so a scheduled run touches the day's new events
rather than the whole table again. When the parser version changes there is
nothing parsed at the new version yet, so it falls back to a full reparse on
its own.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from soulseek_charts.configuration import ClickHouseConfiguration, read_logging_level
from soulseek_charts.identification.resolver import (
    ArtistCatalogue,
    candidate_artist_keys,
    resolve,
)
from soulseek_charts.parsing.query_parser import PARSER_VERSION
from soulseek_charts.storage.client import create_client

CATALOGUE_LOOKUP = """
SELECT normalized_name FROM musicbrainz_artists WHERE normalized_name IN {keys:Array(String)}
"""

DERIVED_TABLES = (
    "parsed_search_queries",
    "artist_search_counts_hourly",
    "track_search_counts_hourly",
)

logger = logging.getLogger("soulseek_charts.parsing.reprocess")

# Each insert into parsed_search_queries fans out to two materialized views
# that aggregate with uniqState, so a large block is expensive in memory on a
# small host. A modest block keeps that cost bounded.
READ_BATCH_SIZE = 10_000

# optimize_on_insert=0 stops the ReplacingMergeTree from merging on every
# insert, which halves peak memory for a bulk rebuild.
INSERT_SETTINGS = {
    "max_insert_block_size": 10_000,
    "optimize_on_insert": 0,
    "max_threads": 1,
}

TARGET_TABLE = "parsed_search_queries"
TARGET_COLUMNS = [
    "received_at",
    "searcher_pseudonym",
    "ticket",
    "query_text",
    "artist_name",
    "album_name",
    "track_name",
    "parse_confidence",
    "parser_version",
    "key_epoch",
]

# Rows imported from the prototype's archive carry its pseudonyms, computed
# with its key; everything this node collected carries ours. The epoch keeps
# the two key spaces from being merged when people are counted.
ARCHIVE_KEY_EPOCH = 1
OWN_KEY_EPOCH = 2

DEFAULT_SINCE = "1970-01-01 00:00:00"

# Process one daily partition at a time and stream it in blocks. A single
# global `ORDER BY received_at` would sort the whole table, which a small host
# cannot hold in memory; scoping to a partition and streaming keeps the
# server-side working set to one block at a time.
DATES_QUERY = """
SELECT DISTINCT received_date
FROM search_query_events
WHERE received_at >= {since:DateTime64(3)}
ORDER BY received_date
"""

STREAM_QUERY = """
SELECT received_at, searcher_pseudonym, ticket, query_text, source
FROM search_query_events
WHERE received_date = {day:Date} AND received_at >= {since:DateTime64(3)}
"""

# The watermark uses the latest already-parsed row at the current version. A
# small overlap re-reads a few boundary rows; ReplacingMergeTree collapses the
# duplicates, so nothing is double-counted.
WATERMARK_QUERY = """
SELECT max(received_at) FROM parsed_search_queries WHERE parser_version = {version:UInt16}
"""
WATERMARK_OVERLAP_SECONDS = 2


def resolve_incremental_since(client: Any) -> str:
    result = client.query(WATERMARK_QUERY, parameters={"version": PARSER_VERSION})
    watermark = result.result_rows[0][0] if result.result_rows else None

    # A zero/None watermark means nothing is parsed at this version yet, so a
    # full reparse is the correct behaviour.
    if watermark is None or watermark.year <= 1970:
        logger.info("No prior parse at version %d — full reparse", PARSER_VERSION)
        return DEFAULT_SINCE

    from datetime import timedelta

    start = watermark - timedelta(seconds=WATERMARK_OVERLAP_SECONDS)
    logger.info("Incremental reparse from %s", start)
    return str(start.strftime("%Y-%m-%d %H:%M:%S.%f"))


# A whole batch's candidates overflow the HTTP field a parameter is sent in, so
# the IN-list is looked up in slices and the matches unioned.
CATALOGUE_LOOKUP_CHUNK = 4000


def build_batch_catalogue(catalogue_client: Any, queries: list[str]) -> ArtistCatalogue:
    """Look up only the artist keys this batch of queries could match.

    The catalogue stays on disk in ClickHouse rather than in the process's
    memory, so this runs on a small host unchanged.
    """
    candidates: set[str] = set()
    for query_text in queries:
        candidates.update(candidate_artist_keys(query_text))
    if not candidates:
        return ArtistCatalogue(frozenset())

    known: set[str] = set()
    candidate_list = list(candidates)
    for start in range(0, len(candidate_list), CATALOGUE_LOOKUP_CHUNK):
        chunk = candidate_list[start : start + CATALOGUE_LOOKUP_CHUNK]
        result = catalogue_client.query(CATALOGUE_LOOKUP, parameters={"keys": chunk})
        known.update(str(row[0]) for row in result.result_rows)

    return ArtistCatalogue(frozenset(known))


def _flush_batch(
    write_client: Any, raw_batch: list[tuple[Any, ...]], catalogue: ArtistCatalogue
) -> int:
    rows: list[list[Any]] = []
    for received_at, pseudonym, ticket, query_text, source in raw_batch:
        parsed = resolve(query_text, catalogue)
        rows.append(
            [
                received_at,
                pseudonym,
                ticket,
                query_text,
                parsed.artist_name,
                parsed.album_name,
                parsed.track_name,
                parsed.confidence,
                PARSER_VERSION,
                ARCHIVE_KEY_EPOCH if source == "imported" else OWN_KEY_EPOCH,
            ]
        )
    write_client.insert(TARGET_TABLE, rows, column_names=TARGET_COLUMNS, settings=INSERT_SETTINGS)
    return len(rows)


def reprocess(read_client: Any, write_client: Any, since: str) -> int:
    """Read the raw layer partition by partition, write the parsed layer.

    Separate clients for reading and writing so an insert (and the per-batch
    catalogue lookup) can run while the read stream stays open.
    """
    total = 0
    dates = read_client.query(DATES_QUERY, parameters={"since": since}).result_rows

    for date_row in dates:
        day = date_row[0]
        raw_batch: list[tuple[Any, ...]] = []

        with read_client.query_row_block_stream(
            STREAM_QUERY, parameters={"day": day, "since": since}
        ) as stream:
            for block in stream:
                for row in block:
                    raw_batch.append(tuple(row))
                    if len(raw_batch) >= READ_BATCH_SIZE:
                        catalogue = build_batch_catalogue(write_client, [r[3] for r in raw_batch])
                        total += _flush_batch(write_client, raw_batch, catalogue)
                        raw_batch = []

        if raw_batch:
            catalogue = build_batch_catalogue(write_client, [r[3] for r in raw_batch])
            total += _flush_batch(write_client, raw_batch, catalogue)

        logger.info("Parsed %d rows (through %s)", total, day)

    return total


def rebuild_derived_tables(client: Any) -> None:
    """Clear the parsed layer and aggregates before a full reparse.

    A materialized view fires on every insert into the parsed layer, so
    re-inserting without clearing would add aggregate states on top of the old
    ones and double every count. A full reparse must start from empty.
    """
    for table in DERIVED_TABLES:
        client.command(f"TRUNCATE TABLE IF EXISTS {table}")
    logger.info("Cleared derived tables for a full rebuild")


def main() -> int:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    arguments = sys.argv[1:]
    since = DEFAULT_SINCE
    incremental = "--incremental" in arguments
    rebuild = "--rebuild" in arguments
    for argument in arguments:
        if argument.startswith("--since="):
            since = f"{argument.split('=', 1)[1]} 00:00:00"

    configuration = ClickHouseConfiguration.from_environment()
    read_client = create_client(configuration)
    write_client = create_client(configuration)
    if incremental:
        since = resolve_incremental_since(read_client)
    if rebuild:
        rebuild_derived_tables(write_client)
    total = reprocess(read_client, write_client, since)
    logger.info("Done: %d rows parsed with parser version %d", total, PARSER_VERSION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
