"""Batching writer between the network and ClickHouse.

At roughly 47 searches a second, one insert per search would be absurd, so
events are batched by size and by time, whichever comes first.

The database going away must never stop collection: the stream cannot be
replayed, while an insert can be retried. Events therefore accumulate in a
bounded queue during an outage, and if even that fills up the oldest are
dropped and counted rather than allowed to exhaust memory.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from soulseek_charts.collector.events import SearchQueryEvent

logger = logging.getLogger("soulseek_charts.collector.buffer")

TABLE_NAME = "search_query_events"
COLUMN_NAMES = ["received_at", "searcher_pseudonym", "ticket", "query_text", "source"]

# Roughly two minutes of traffic at the observed rate: enough to ride out a
# ClickHouse restart without unbounded memory growth.
DEFAULT_MAXIMUM_PENDING_EVENTS = 6000

RETRY_DELAY_SECONDS = 5.0


@dataclass
class BufferStatistics:
    received: int = 0
    written: int = 0
    dropped: int = 0
    failed_flushes: int = 0
    duplicates_skipped: int = 0

    def as_log_fields(self) -> str:
        return (
            f"received={self.received} written={self.written} "
            f"duplicates={self.duplicates_skipped} dropped={self.dropped} "
            f"failed_flushes={self.failed_flushes}"
        )


@dataclass
class SearchEventBuffer:
    client: Any
    batch_size: int
    flush_interval_seconds: float
    maximum_pending_events: int = DEFAULT_MAXIMUM_PENDING_EVENTS
    statistics: BufferStatistics = field(default_factory=BufferStatistics)
    _pending: deque[SearchQueryEvent] = field(init=False)

    def __post_init__(self) -> None:
        self._pending = deque()

    def add(self, event: SearchQueryEvent) -> None:
        self.statistics.received += 1

        if len(self._pending) >= self.maximum_pending_events:
            self._pending.popleft()
            self.statistics.dropped += 1
            if self.statistics.dropped % 1000 == 1:
                logger.error(
                    "Insert queue is full, dropping the oldest events (%d so far)",
                    self.statistics.dropped,
                )

        self._pending.append(event)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def _take_batch(self) -> list[SearchQueryEvent]:
        batch: list[SearchQueryEvent] = []
        while self._pending and len(batch) < self.batch_size:
            batch.append(self._pending.popleft())
        return batch

    def _return_batch(self, batch: list[SearchQueryEvent]) -> None:
        """Put a failed batch back at the front, oldest first."""
        for event in reversed(batch):
            if len(self._pending) >= self.maximum_pending_events:
                self.statistics.dropped += 1
                continue
            self._pending.appendleft(event)

    async def flush_once(self) -> int:
        batch = self._take_batch()
        if not batch:
            return 0

        rows = [
            [
                event.received_at,
                event.searcher_pseudonym,
                event.ticket,
                event.query_text,
                str(event.source),
            ]
            for event in batch
        ]

        try:
            # The ClickHouse driver is synchronous; keep it off the event loop
            # so the network side never stalls behind an insert.
            await asyncio.to_thread(self.client.insert, TABLE_NAME, rows, column_names=COLUMN_NAMES)
        except Exception as insertion_error:  # noqa: BLE001 - collection must survive anything
            self.statistics.failed_flushes += 1
            self._return_batch(batch)
            logger.warning(
                "Insert of %d events failed, will retry: %s", len(batch), insertion_error
            )
            return 0

        self.statistics.written += len(batch)
        return len(batch)

    async def run(self, stop_signal: asyncio.Event) -> None:
        """Flush until stopped, then drain what is left."""
        while not stop_signal.is_set():
            if self.pending_count >= self.batch_size:
                written = await self.flush_once()
                if written:
                    continue

            # Either the interval elapses or shutdown arrives; both then flush.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_signal.wait(), timeout=self.flush_interval_seconds)

            if self.pending_count:
                written = await self.flush_once()
                if not written and self.pending_count:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        logger.info("Draining %d pending events before shutdown", self.pending_count)
        while self.pending_count:
            if not await self.flush_once():
                logger.error("Could not drain %d events, giving up", self.pending_count)
                break
