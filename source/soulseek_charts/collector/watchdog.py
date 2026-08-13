"""Restart-on-silence watchdog.

A node that has lost its parent, or whose connection died while the process
stayed alive, keeps running and collects nothing — the failure mode that cost a
night of collection. The node can notice the silence but cannot reliably heal
it in place: a fresh login gets a new parent far more dependably than an
in-process reconnect. So once the stream has been silent for long enough, the
collector exits and lets the container supervisor restart it clean.
"""

from __future__ import annotations

# Consecutive silent statistics ticks (one per minute) before a restart is
# requested. A few minutes tolerates a slow join and brief network hiccups
# without flapping; beyond that the node is genuinely stuck.
DEFAULT_SILENCE_TOLERANCE_TICKS = 5


class SilenceWatchdog:
    def __init__(self, tolerance_ticks: int = DEFAULT_SILENCE_TOLERANCE_TICKS) -> None:
        self.tolerance_ticks = tolerance_ticks
        self.silent_ticks = 0

    def record(self, search_rate: float) -> bool:
        """Register one statistics tick. Returns True when a restart is due."""
        if search_rate > 0:
            self.silent_ticks = 0
            return False

        self.silent_ticks += 1
        return self.silent_ticks >= self.tolerance_ticks
