"""How an entry's movement against the previous period is described."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChartMovement(StrEnum):
    NEW = "new"
    RE_ENTRY = "re_entry"
    UP = "up"
    DOWN = "down"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class Movement:
    kind: ChartMovement
    # Positions gained (positive) or lost (negative); None for entries that
    # were absent in the previous period.
    positions: int | None


def describe_movement(rank: int, previous_rank: int, seen_before: bool) -> Movement:
    """Classify an entry.

    `previous_rank` is 0 when the entry is absent from the previous period —
    that is what a ClickHouse LEFT JOIN yields for a missing row.
    """
    if previous_rank == 0:
        return Movement(ChartMovement.RE_ENTRY if seen_before else ChartMovement.NEW, None)

    if previous_rank == rank:
        return Movement(ChartMovement.UNCHANGED, 0)

    # Rank 1 is the top, so a smaller number is an improvement.
    positions = previous_rank - rank
    return Movement(ChartMovement.UP if positions > 0 else ChartMovement.DOWN, positions)
