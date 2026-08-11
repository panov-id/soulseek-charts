"""ClickHouse connection helpers shared by the collector, the API and migrations."""

from __future__ import annotations

from typing import Any

import clickhouse_connect

from soulseek_charts.configuration import ClickHouseConfiguration


def create_client(
    configuration: ClickHouseConfiguration,
    *,
    with_database: bool = True,
) -> Any:
    """Open a ClickHouse connection.

    `with_database=False` is used by the migration runner, which has to connect
    before the target database exists.
    """
    connection_arguments: dict[str, Any] = {
        "host": configuration.host,
        "port": configuration.port,
        "username": configuration.user,
        "password": configuration.password,
    }
    if with_database:
        connection_arguments["database"] = configuration.database

    return clickhouse_connect.get_client(**connection_arguments)
