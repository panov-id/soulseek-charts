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
from soulseek_charts.parsing.query_parser import PARSER_VERSION, parse_search_query
from soulseek_charts.storage.client import create_client

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


def _parsed_row(
    received_at: Any, pseudonym: str, ticket: int, query_text: str, source: str
) -> list[Any]:
    parsed = parse_search_query(query_text)
    return [
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


def reprocess(read_client: Any, write_client: Any, since: str) -> int:
    """Read the raw layer partition by partition, write the parsed layer.

    Separate clients for reading and writing so an insert can run while the
    read stream for the current partition is still open.
    """
    total = 0
    dates = read_client.query(DATES_QUERY, parameters={"since": since}).result_rows

    for date_row in dates:
        day = date_row[0]
        batch: list[list[Any]] = []

        with read_client.query_row_block_stream(
            STREAM_QUERY, parameters={"day": day, "since": since}
        ) as stream:
            for block in stream:
                for received_at, pseudonym, ticket, query_text, source in block:
                    batch.append(_parsed_row(received_at, pseudonym, ticket, query_text, source))
                    if len(batch) >= READ_BATCH_SIZE:
                        write_client.insert(
                            TARGET_TABLE,
                            batch,
                            column_names=TARGET_COLUMNS,
                            settings=INSERT_SETTINGS,
                        )
                        total += len(batch)
                        batch = []

        if batch:
            write_client.insert(
                TARGET_TABLE, batch, column_names=TARGET_COLUMNS, settings=INSERT_SETTINGS
            )
            total += len(batch)

        logger.info("Parsed %d rows (through %s)", total, day)

    return total


def main() -> int:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    arguments = sys.argv[1:]
    since = DEFAULT_SINCE
    incremental = "--incremental" in arguments
    for argument in arguments:
        if argument.startswith("--since="):
            since = f"{argument.split('=', 1)[1]} 00:00:00"

    configuration = ClickHouseConfiguration.from_environment()
    read_client = create_client(configuration)
    write_client = create_client(configuration)
    if incremental:
        since = resolve_incremental_since(read_client)
    total = reprocess(read_client, write_client, since)
    logger.info("Done: %d rows parsed with parser version %d", total, PARSER_VERSION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
