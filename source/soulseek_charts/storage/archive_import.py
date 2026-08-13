"""Import the Go prototype's JSONL archive into ClickHouse.

The archive holds one JSON object per observed search:

    {"time":"2026-08-12T07:58:31Z","query":"...","user":"98dad5a9388387bc"}

`user` is already a pseudonym in the prototype's format — eight bytes, hex —
so nothing is re-hashed here and no nickname is ever seen. Given the same key,
the collector produces the same pseudonyms, and the two collection periods
describe the same people.

The archive records no ticket, and the storage key is (date, pseudonym,
ticket): a constant would collapse everything one person searched in a day into
a single row. Imported rows therefore carry a ticket derived from the line
itself, which also makes re-importing the same file idempotent.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("soulseek_charts.storage.archive_import")

TABLE_NAME = "search_query_events"
COLUMN_NAMES = ["received_at", "searcher_pseudonym", "ticket", "query_text", "source"]
IMPORTED_SOURCE = "imported"
INSERT_BATCH_SIZE = 50_000


def derive_ticket(pseudonym: str, timestamp: str, query: str) -> int:
    """A stable stand-in for the ticket the archive does not record."""
    digest = hashlib.blake2b(f"{pseudonym}|{timestamp}|{query}".encode(), digest_size=4).digest()
    return int.from_bytes(digest, "big")


GZIP_MAGIC_BYTES = b"\x1f\x8b"


def is_gzipped(path: Path) -> bool:
    """Detect by signature, not by name: a mounted file may lose its suffix."""
    with path.open("rb") as archive_file:
        return archive_file.read(2) == GZIP_MAGIC_BYTES


def read_archive_lines(path: Path) -> Iterator[str]:
    if is_gzipped(path):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as archive_file:
            yield from archive_file
    else:
        with path.open("rt", encoding="utf-8", errors="replace") as archive_file:
            yield from archive_file


def parse_line(line: str) -> list[Any] | None:
    line = line.strip()
    if not line:
        return None

    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None

    # A long-running archive accumulates the occasional malformed line: a
    # truncated write, or a bare value where an object was expected. Skipping
    # them is right, crashing on them is not.
    if not isinstance(record, dict):
        return None

    try:
        received_at = datetime.fromisoformat(str(record["time"]).replace("Z", "+00:00"))
        pseudonym = str(record["user"])
        query_text = str(record["query"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return None

    if len(pseudonym) != 16:
        return None

    return [
        received_at.replace(tzinfo=None),
        pseudonym,
        derive_ticket(pseudonym, record["time"], query_text),
        query_text,
        IMPORTED_SOURCE,
    ]


def lacks_a_searcher(line: str) -> bool:
    """Records from before the prototype added pseudonymization carry no user.

    They are real observations, but nothing identifies who made them, so they
    cannot take part in counting demand in people. Mixing them in under a
    placeholder would collapse thousands of strangers into one "person"; they
    are skipped, and counted separately so the loss is never silent.
    """
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(record, dict) and "user" not in record and "query" in record


def import_archive_file(client: Any, path: Path, limit: int | None = None) -> tuple[int, int]:
    """Insert one archive file. Returns (imported, skipped)."""
    imported = 0
    skipped = 0
    without_searcher = 0
    batch: list[list[Any]] = []

    for line in read_archive_lines(path):
        row = parse_line(line)
        if row is None:
            skipped += 1
            if lacks_a_searcher(line):
                without_searcher += 1
            continue

        batch.append(row)
        if len(batch) >= INSERT_BATCH_SIZE:
            client.insert(TABLE_NAME, batch, column_names=COLUMN_NAMES)
            imported += len(batch)
            batch = []
            logger.info("%s: %d rows imported", path.name, imported)

        if limit is not None and imported + len(batch) >= limit:
            break

    if batch:
        client.insert(TABLE_NAME, batch, column_names=COLUMN_NAMES)
        imported += len(batch)

    if without_searcher:
        logger.warning(
            "%s: %d records predate pseudonymization and carry no searcher — "
            "skipped, they cannot be counted in people",
            path.name,
            without_searcher,
        )

    return imported, skipped
