"""Load the artist catalogue: `python -m soulseek_charts.identification.catalog_command <dump>`."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from soulseek_charts.configuration import ClickHouseConfiguration, read_logging_level
from soulseek_charts.identification.catalog_loader import load_catalogue
from soulseek_charts.storage.client import create_client

logger = logging.getLogger("soulseek_charts.identification.catalog")


def main() -> int:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if len(sys.argv) != 2:
        logger.error("Usage: catalog_command <artist.tar.xz>")
        return 1

    dump_path = Path(sys.argv[1])
    if not dump_path.exists():
        logger.error("Dump not found: %s", dump_path)
        return 1

    client = create_client(ClickHouseConfiguration.from_environment())
    load_catalogue(client, dump_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
