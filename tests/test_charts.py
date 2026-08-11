from datetime import datetime

import pytest

from soulseek_charts.charts.periods import ChartPeriod, resolve_period
from soulseek_charts.charts.ranking import ChartMovement, describe_movement


def test_week_window_starts_on_monday():
    # 2026-08-13 is a Thursday.
    window = resolve_period(ChartPeriod.WEEK, datetime(2026, 8, 13, 15, 30))

    assert window.current_start == datetime(2026, 8, 10)
    assert window.current_end == datetime(2026, 8, 17)
    assert window.previous_start == datetime(2026, 8, 3)


def test_day_window_covers_the_reference_day():
    window = resolve_period(ChartPeriod.DAY, datetime(2026, 8, 13, 15, 30))

    assert window.current_start == datetime(2026, 8, 13)
    assert window.current_end == datetime(2026, 8, 14)
    assert window.previous_start == datetime(2026, 8, 12)


def test_month_window_handles_the_year_boundary():
    window = resolve_period(ChartPeriod.MONTH, datetime(2026, 1, 17, 9, 0))

    assert window.current_start == datetime(2026, 1, 1)
    assert window.current_end == datetime(2026, 2, 1)
    assert window.previous_start == datetime(2025, 12, 1)


@pytest.mark.parametrize("period", [ChartPeriod.DAY, ChartPeriod.WEEK])
def test_fixed_length_periods_compare_windows_of_equal_length(period):
    window = resolve_period(period, datetime(2026, 3, 15, 12, 0))

    current_length = window.current_end - window.current_start
    previous_length = window.current_start - window.previous_start
    assert current_length == previous_length


def test_month_compares_against_the_calendar_previous_month():
    """Months are deliberately unequal in length.

    Comparing March (31 days) against February (28) slightly favours March,
    but a "previous month" that is not the calendar month would be worse: it
    would not match what the number is called on the dashboard.
    """
    window = resolve_period(ChartPeriod.MONTH, datetime(2026, 3, 15, 12, 0))

    assert window.current_start == datetime(2026, 3, 1)
    assert window.current_end == datetime(2026, 4, 1)
    assert window.previous_start == datetime(2026, 2, 1)


@pytest.mark.parametrize(
    ("position", "previous_position", "seen_before", "expected_kind", "expected_positions"),
    [
        (1, 5, True, ChartMovement.UP, 4),
        (7, 3, True, ChartMovement.DOWN, -4),
        (2, 2, True, ChartMovement.UNCHANGED, 0),
        (4, 0, False, ChartMovement.NEW, None),
        (4, 0, True, ChartMovement.RE_ENTRY, None),
    ],
)
def test_describe_movement(
    position, previous_position, seen_before, expected_kind, expected_positions
):
    movement = describe_movement(position, previous_position, seen_before)

    assert movement.kind == expected_kind
    assert movement.positions == expected_positions
