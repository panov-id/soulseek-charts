"""Chart periods.

A chart always compares two adjacent windows of the same length, so every
entry can carry its movement against the previous period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class ChartPeriod(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class PeriodWindow:
    """Current window plus the start of the preceding one of equal length."""

    current_start: datetime
    current_end: datetime
    previous_start: datetime


def _start_of_day(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_previous_month(month_start: datetime) -> datetime:
    last_day_of_previous_month = month_start - timedelta(days=1)
    return last_day_of_previous_month.replace(day=1)


def resolve_period(period: ChartPeriod, reference: datetime | None = None) -> PeriodWindow:
    """Return the window a chart for `period` covers at `reference` time."""
    moment = reference or datetime.now(tz=UTC)
    moment = moment.replace(tzinfo=None)

    if period is ChartPeriod.DAY:
        current_start = _start_of_day(moment)
        return PeriodWindow(
            current_start=current_start,
            current_end=current_start + timedelta(days=1),
            previous_start=current_start - timedelta(days=1),
        )

    if period is ChartPeriod.WEEK:
        # Weeks start on Monday, matching how listeners talk about "this week".
        current_start = _start_of_day(moment) - timedelta(days=moment.weekday())
        return PeriodWindow(
            current_start=current_start,
            current_end=current_start + timedelta(days=7),
            previous_start=current_start - timedelta(days=7),
        )

    current_start = _start_of_day(moment).replace(day=1)
    next_month = (current_start + timedelta(days=32)).replace(day=1)
    return PeriodWindow(
        current_start=current_start,
        current_end=next_month,
        previous_start=_start_of_previous_month(current_start),
    )
