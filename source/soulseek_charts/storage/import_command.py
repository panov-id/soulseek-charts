"""Import archive files: `python -m soulseek_charts.storage.import_command <path>...`.

Accepts files or a directory of `searches-*.jsonl[.gz]`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from soulseek_charts.configuration import ClickHouseConfiguration, read_logging_level
from soulseek_charts.storage.archive_import import import_archive_file
from soulseek_charts.storage.client import create_client

logger = logging.getLogger("soulseek_charts.storage.import")


def collect_paths(arguments: list[str]) -> list[Path]:
    paths: list[Path] = []
    for argument in arguments:
        path = Path(argument)
        if path.is_dir():
            paths.extend(sorted(path.glob("searches-*.jsonl*")))
        elif path.exists():
            paths.append(path)
        else:
            logger.warning("Skipping %s: not found", path)
    return paths


def main() -> int:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    arguments = sys.argv[1:]
    limit: int | None = None
    if arguments and arguments[0].startswith("--limit="):
        limit = int(arguments[0].split("=", 1)[1])
        arguments = arguments[1:]

    paths = collect_paths(arguments)
    if not paths:
        logger.error("Nothing to import. Pass archive files or a directory.")
        return 1

    client = create_client(ClickHouseConfiguration.from_environment())

    total_imported = 0
    total_skipped = 0
    for path in paths:
        imported, skipped = import_archive_file(client, path, limit=limit)
        total_imported += imported
        total_skipped += skipped
        logger.info("%s: imported=%d skipped=%d", path.name, imported, skipped)

    logger.info("Done: imported=%d skipped=%d", total_imported, total_skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
