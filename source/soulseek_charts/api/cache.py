"""A small in-process response cache.

Charts change at most once per hour, when the materialized views absorb a new
batch, so repeating an identical ClickHouse aggregation for every visitor is
pure waste. An in-process cache is enough while the API runs as one service;
a shared cache only becomes necessary with several replicas.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_TIME_TO_LIVE_SECONDS = 60.0
MAXIMUM_ENTRIES = 512


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class ResponseCache:
    def __init__(self, time_to_live_seconds: float = DEFAULT_TIME_TO_LIVE_SECONDS) -> None:
        self.time_to_live_seconds = time_to_live_seconds
        self._entries: dict[str, CacheEntry] = {}

    def get_or_call(self, key: str, producer: Callable[[], Any]) -> Any:
        now = time.monotonic()
        entry = self._entries.get(key)
        if entry is not None and entry.expires_at > now:
            return entry.value

        value = producer()

        if len(self._entries) >= MAXIMUM_ENTRIES:
            self._evict_expired(now)
        self._entries[key] = CacheEntry(value=value, expires_at=now + self.time_to_live_seconds)
        return value

    def _evict_expired(self, now: float) -> None:
        expired_keys = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired_keys:
            del self._entries[key]
        if not expired_keys:
            # Nothing has expired yet: drop the oldest entry to bound memory.
            oldest_key = min(self._entries, key=lambda key: self._entries[key].expires_at)
            del self._entries[oldest_key]

    def clear(self) -> None:
        self._entries.clear()
