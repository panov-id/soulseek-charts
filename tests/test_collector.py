import asyncio
from datetime import datetime

import pytest

from soulseek_charts.collector.buffer import SearchEventBuffer
from soulseek_charts.collector.events import SearchQueryEvent, SearchSource
from soulseek_charts.collector.node import SearchDeduplicator
from soulseek_charts.collector.watchdog import SilenceWatchdog


class RecordingClient:
    """A ClickHouse client stand-in that can be told to fail."""

    def __init__(self, failures_before_success: int = 0):
        self.failures_before_success = failures_before_success
        self.inserted_rows: list[list[object]] = []
        self.insert_calls = 0

    def insert(self, table, rows, column_names):
        self.insert_calls += 1
        if self.insert_calls <= self.failures_before_success:
            raise ConnectionError("ClickHouse is unavailable")
        self.inserted_rows.extend(rows)


def make_event(ticket: int, pseudonym: str = "0000000000000001") -> SearchQueryEvent:
    return SearchQueryEvent(
        received_at=datetime(2026, 8, 12, 10, 0, 0),
        searcher_pseudonym=pseudonym,
        ticket=ticket,
        query_text=f"query {ticket}",
        source=SearchSource.DISTRIBUTED,
    )


def test_the_node_shares_nothing():
    """Serving files is a legal risk out of proportion to a research task."""
    from soulseek_charts.collector.node import build_settings
    from soulseek_charts.configuration import SoulseekConfiguration

    settings = build_settings(
        SoulseekConfiguration(
            username="node",
            password="secret",
            server_host="server.slsknet.org",
            server_port=2416,
            listening_port=2234,
            client_version_major=None,
            client_version_minor=None,
        )
    )

    assert settings.shares.directories == []
    assert settings.shares.scan_on_start is False
    assert settings.network.server.port == 2416


def test_watchdog_trips_after_the_tolerance_of_silent_ticks():
    """The failure that cost a night: a live process collecting nothing."""
    watchdog = SilenceWatchdog(tolerance_ticks=3)

    assert watchdog.record(0.0) is False
    assert watchdog.record(0.0) is False
    assert watchdog.record(0.0) is True


def test_watchdog_resets_when_searches_resume():
    watchdog = SilenceWatchdog(tolerance_ticks=3)

    watchdog.record(0.0)
    watchdog.record(0.0)
    assert watchdog.record(12.5) is False
    assert watchdog.silent_ticks == 0
    # Two more silent ticks must not trip yet — the counter restarted.
    assert watchdog.record(0.0) is False
    assert watchdog.record(0.0) is False


def test_deduplicator_suppresses_the_same_search_twice():
    """Parents relay the same search; counting the copies inflates every chart."""
    deduplicator = SearchDeduplicator()

    assert deduplicator.is_new(("user", 1)) is True
    assert deduplicator.is_new(("user", 1)) is False
    assert deduplicator.is_new(("user", 2)) is True


def test_deduplicator_forgets_beyond_its_capacity():
    deduplicator = SearchDeduplicator(capacity=2)

    deduplicator.is_new(("user", 1))
    deduplicator.is_new(("user", 2))
    deduplicator.is_new(("user", 3))

    assert deduplicator.is_new(("user", 1)) is True


async def test_flush_writes_a_batch():
    client = RecordingClient()
    buffer = SearchEventBuffer(client=client, batch_size=10, flush_interval_seconds=1)

    for ticket in range(3):
        buffer.add(make_event(ticket))
    written = await buffer.flush_once()

    assert written == 3
    assert buffer.statistics.written == 3
    assert len(client.inserted_rows) == 3


async def test_events_survive_a_database_outage():
    """The stream cannot be replayed; an insert can be retried."""
    client = RecordingClient(failures_before_success=1)
    buffer = SearchEventBuffer(client=client, batch_size=10, flush_interval_seconds=1)

    buffer.add(make_event(1))
    buffer.add(make_event(2))

    assert await buffer.flush_once() == 0
    assert buffer.statistics.failed_flushes == 1
    assert buffer.pending_count == 2

    assert await buffer.flush_once() == 2
    assert [row[2] for row in client.inserted_rows] == [1, 2]


async def test_a_full_queue_drops_the_oldest_and_counts_it():
    client = RecordingClient()
    buffer = SearchEventBuffer(
        client=client, batch_size=10, flush_interval_seconds=1, maximum_pending_events=2
    )

    for ticket in range(4):
        buffer.add(make_event(ticket))

    assert buffer.pending_count == 2
    assert buffer.statistics.dropped == 2
    await buffer.flush_once()
    assert [row[2] for row in client.inserted_rows] == [2, 3]


async def test_run_drains_pending_events_on_shutdown():
    client = RecordingClient()
    buffer = SearchEventBuffer(client=client, batch_size=100, flush_interval_seconds=0.05)
    stop_signal = asyncio.Event()

    buffer.add(make_event(1))
    runner = asyncio.create_task(buffer.run(stop_signal))
    await asyncio.sleep(0.15)
    buffer.add(make_event(2))
    stop_signal.set()
    await asyncio.wait_for(runner, timeout=2)

    assert buffer.pending_count == 0
    assert buffer.statistics.written == 2


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (SearchSource.DISTRIBUTED, "distributed"),
        (SearchSource.DISTRIBUTED_SERVER, "distributed_server"),
    ],
)
def test_source_values_match_the_database_enum(source, expected):
    assert str(source) == expected
