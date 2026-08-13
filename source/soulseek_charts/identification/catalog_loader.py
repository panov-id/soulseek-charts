"""Load a MusicBrainz artist JSON dump into the catalogue table.

The dump is a `.tar.xz` holding one JSON artist per line. Only names are kept:
the primary name plus aliases, each normalized to the query key. Everything
else in the dump — relationships, tags, ratings — is discarded, so a 1.6 GiB
dump becomes a catalogue of a few hundred MiB.

Names are streamed and deduplicated by key in memory, which the build host can
afford; only the compact result reaches the collector's storage.
"""

from __future__ import annotations

import json
import logging
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from soulseek_charts.parsing.normalization import build_artist_key

logger = logging.getLogger("soulseek_charts.identification.catalog_loader")

MEMBER_NAME = "mbdump/artist"
TABLE_NAME = "musicbrainz_artists"
COLUMN_NAMES = ["normalized_name", "display_name", "token_count"]
INSERT_BATCH_SIZE = 100_000
MINIMUM_KEY_LENGTH = 2

# Small blocks and no merge-on-insert keep the loader within a modest container.
INSERT_SETTINGS = {"max_insert_block_size": 100_000, "optimize_on_insert": 0}


def _names_in_record(record: dict[str, Any]) -> Iterator[str]:
    name = record.get("name")
    if isinstance(name, str):
        yield name
    for alias in record.get("aliases") or []:
        alias_name = alias.get("name") if isinstance(alias, dict) else None
        if isinstance(alias_name, str):
            yield alias_name


# MusicBrainz placeholders for compilations and unknowns — not real artists.
PLACEHOLDER_KEYS = frozenset(
    {
        "various artists",
        "unknown",
        "various",
        "no artist",
        "none",
        "untitled",
        "unknown artist",
        "soundtrack",
    }
)


def _is_useful_key(key: str) -> bool:
    return len(key) >= MINIMUM_KEY_LENGTH and not key.isdigit() and key not in PLACEHOLDER_KEYS


def iterate_artist_names(dump_path: Path) -> Iterator[tuple[str, str]]:
    """Yield (normalized_key, display_name) for every name in the dump."""
    with tarfile.open(dump_path, mode="r:xz") as archive:
        member = archive.getmember(MEMBER_NAME)
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"{MEMBER_NAME} missing from {dump_path}")

        for raw_line in extracted:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            for display_name in _names_in_record(record):
                key = build_artist_key(display_name)
                if _is_useful_key(key):
                    yield key, display_name


def load_catalogue(client: Any, dump_path: Path) -> int:
    """Replace the catalogue table with the names from the dump. Returns rows inserted.

    Names stream straight into ClickHouse in batches; the ReplacingMergeTree
    collapses keys that repeat. Nothing is accumulated in memory, so this stays
    flat regardless of catalogue size.
    """
    client.command(f"TRUNCATE TABLE IF EXISTS {TABLE_NAME}")

    batch: list[list[Any]] = []
    inserted = 0
    for key, display_name in iterate_artist_names(dump_path):
        # token_count is UInt8; a pathological name can exceed 255 tokens.
        token_count = min(key.count(" ") + 1, 255)
        batch.append([key, display_name, token_count])
        if len(batch) >= INSERT_BATCH_SIZE:
            client.insert(TABLE_NAME, batch, column_names=COLUMN_NAMES, settings=INSERT_SETTINGS)
            inserted += len(batch)
            batch = []
            if inserted % 1_000_000 == 0:
                logger.info("Inserted %d names so far", inserted)
    if batch:
        client.insert(TABLE_NAME, batch, column_names=COLUMN_NAMES, settings=INSERT_SETTINGS)
        inserted += len(batch)

    logger.info("Inserted %d names into %s (keys deduplicate on merge)", inserted, TABLE_NAME)
    return inserted
