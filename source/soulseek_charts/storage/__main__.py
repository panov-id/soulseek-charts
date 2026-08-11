"""Apply pending migrations: `python -m soulseek_charts.storage`."""

from __future__ import annotations

import logging

from soulseek_charts.configuration import ClickHouseConfiguration, read_logging_level
from soulseek_charts.storage.client import create_client
from soulseek_charts.storage.migrations import apply_migrations

logger = logging.getLogger("soulseek_charts.storage")


def main() -> None:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    configuration = ClickHouseConfiguration.from_environment()
    # The database itself may not exist yet, so connect without selecting it.
    client = create_client(configuration, with_database=False)

    applied_identifiers = apply_migrations(client, configuration.database)

    if applied_identifiers:
        logger.info(
            "Applied %d migration(s) to %s: %s",
            len(applied_identifiers),
            configuration.database,
            ", ".join(applied_identifiers),
        )
    else:
        logger.info("Database %s is already up to date", configuration.database)


if __name__ == "__main__":
    main()
