"""Collector entry point.

Joins the Soulseek distributed network, records the search requests passing
through the node, and writes them to ClickHouse in batches.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from soulseek_charts.collector.buffer import SearchEventBuffer
from soulseek_charts.collector.node import CollectorNode
from soulseek_charts.collector.watchdog import SilenceWatchdog
from soulseek_charts.configuration import (
    ClickHouseConfiguration,
    CollectorConfiguration,
    PrivacyConfiguration,
    SoulseekConfiguration,
    read_logging_level,
)
from soulseek_charts.privacy import decode_secret
from soulseek_charts.storage.client import create_client

logger = logging.getLogger("soulseek_charts.collector")

STATISTICS_INTERVAL_SECONDS = 60.0


async def report_statistics(
    buffer: SearchEventBuffer,
    node: CollectorNode,
    stop_signal: asyncio.Event,
) -> bool:
    """Log throughput and watch for silence.

    Returns True if it asked for a restart (the stream went silent), False on
    an ordinary shutdown. A silent collector is indistinguishable from a broken
    one, so prolonged silence trips the watchdog.
    """
    previous_received = 0
    watchdog = SilenceWatchdog()

    while not stop_signal.is_set():
        try:
            await asyncio.wait_for(stop_signal.wait(), timeout=STATISTICS_INTERVAL_SECONDS)
            return False
        except TimeoutError:
            pass

        received = buffer.statistics.received
        rate = (received - previous_received) / STATISTICS_INTERVAL_SECONDS
        previous_received = received

        buffer.statistics.duplicates_skipped = node.duplicate_count
        logger.info(
            "%.1f searches/s pending=%d %s",
            rate,
            buffer.pending_count,
            buffer.statistics.as_log_fields(),
        )

        if watchdog.record(rate):
            logger.error(
                "No searches for %d minutes — exiting so the supervisor restarts the "
                "node with a fresh login and parent",
                watchdog.tolerance_ticks,
            )
            stop_signal.set()
            return True

        if rate == 0:
            logger.warning(
                "No searches in the last %.0f seconds (%d/%d before restart) — check "
                "the parent connection and the client version",
                STATISTICS_INTERVAL_SECONDS,
                watchdog.silent_ticks,
                watchdog.tolerance_ticks,
            )

    return False


async def run_collector(stop_signal: asyncio.Event) -> int:
    clickhouse_configuration = ClickHouseConfiguration.from_environment()
    collector_configuration = CollectorConfiguration.from_environment()
    soulseek_configuration = SoulseekConfiguration.from_environment()
    privacy_configuration = PrivacyConfiguration.from_environment()

    client = create_client(clickhouse_configuration)
    buffer = SearchEventBuffer(
        client=client,
        batch_size=collector_configuration.batch_size,
        flush_interval_seconds=collector_configuration.flush_interval_seconds,
    )
    node = CollectorNode(
        configuration=soulseek_configuration,
        pseudonymization_key=decode_secret(privacy_configuration.hash_secret),
        on_search=buffer.add,
    )

    logger.info(
        "Collector starting: storage=%s:%s/%s batch_size=%d flush_interval=%ds",
        clickhouse_configuration.host,
        clickhouse_configuration.port,
        clickhouse_configuration.database,
        collector_configuration.batch_size,
        collector_configuration.flush_interval_seconds,
    )

    await node.start()

    try:
        _, restart_requested = await asyncio.gather(
            buffer.run(stop_signal),
            report_statistics(buffer, node, stop_signal),
        )
    finally:
        await node.stop()
        logger.info("Collector stopped: %s", buffer.statistics.as_log_fields())

    # A non-zero code lets `restart: unless-stopped` bring the node back with a
    # clean login; a signalled shutdown exits zero and stays down.
    return 1 if restart_requested else 0


async def main() -> int:
    logging.basicConfig(
        level=read_logging_level(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    stop_signal = asyncio.Event()
    event_loop = asyncio.get_running_loop()
    for termination_signal in (signal.SIGINT, signal.SIGTERM):
        event_loop.add_signal_handler(termination_signal, stop_signal.set)

    return await run_collector(stop_signal)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
