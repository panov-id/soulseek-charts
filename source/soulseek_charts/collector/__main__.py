"""Collector entry point.

Stage 0 only establishes the process shape: configuration loading, logging and
graceful shutdown. Connecting to the Soulseek network is stage 2 of the
roadmap and is intentionally not implemented here.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from soulseek_charts.configuration import (
    ClickHouseConfiguration,
    CollectorConfiguration,
    SoulseekConfiguration,
    read_logging_level,
)

logger = logging.getLogger("soulseek_charts.collector")


async def run_collector(stop_signal: asyncio.Event) -> None:
    clickhouse_configuration = ClickHouseConfiguration.from_environment()
    collector_configuration = CollectorConfiguration.from_environment()

    logger.info(
        "Collector started: storage=%s:%s/%s batch_size=%d flush_interval=%ds",
        clickhouse_configuration.host,
        clickhouse_configuration.port,
        clickhouse_configuration.database,
        collector_configuration.batch_size,
        collector_configuration.flush_interval_seconds,
    )
    soulseek_configuration = SoulseekConfiguration.from_environment()
    if soulseek_configuration.claims_a_version:
        logger.info(
            "Claiming client version %s.%s — an explicit choice by the operator",
            soulseek_configuration.client_version_major,
            soulseek_configuration.client_version_minor,
        )
    else:
        logger.warning(
            "No client version set: the server will not offer distributed parents, "
            "so this node will record nothing. Set SOULSEEK_CLIENT_VERSION_MAJOR "
            "and SOULSEEK_CLIENT_VERSION_MINOR to override, deliberately."
        )

    logger.warning("Soulseek network connection is not implemented yet (roadmap stage 2)")

    await stop_signal.wait()
    logger.info("Collector stopped")


async def main() -> None:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    stop_signal = asyncio.Event()
    event_loop = asyncio.get_running_loop()
    for termination_signal in (signal.SIGINT, signal.SIGTERM):
        event_loop.add_signal_handler(termination_signal, stop_signal.set)

    await run_collector(stop_signal)


if __name__ == "__main__":
    asyncio.run(main())
