"""Chart queries against the hourly aggregate tables.

Daily, weekly and monthly charts are all merges of the same hourly states, so
there is exactly one source of truth for every grain.

Every query is aware of the pseudonymization key epoch. Searches are summed
across epochs freely — a search is a search whoever made it. People are not:
the same person carries unrelated pseudonyms under two different keys, so a
window covering both would count them twice. Where that happens the listener
count is withheld rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from soulseek_charts.charts.periods import PeriodWindow
from soulseek_charts.charts.ranking import Movement, describe_movement

MAXIMUM_PAGE_SIZE = 200

ARTIST_CHART_QUERY = """
WITH
current_by_epoch AS (
    SELECT
        artist_name,
        key_epoch,
        countMerge(search_count) AS searches,
        uniqMerge(unique_searchers) AS listeners
    FROM artist_search_counts_hourly
    WHERE hour_start >= {current_start:DateTime} AND hour_start < {current_end:DateTime}
    GROUP BY artist_name, key_epoch
),
current_period AS (
    SELECT
        artist_name,
        sum(searches) AS searches,
        max(listeners) AS listeners,
        count() AS epoch_count
    FROM current_by_epoch
    GROUP BY artist_name
),
current_ranked AS (
    SELECT
        artist_name,
        searches,
        listeners,
        epoch_count,
        row_number() OVER (ORDER BY searches DESC, artist_name ASC) AS position
    FROM current_period
),
previous_period AS (
    SELECT artist_name, sum(searches) AS searches
    FROM (
        SELECT artist_name, key_epoch, countMerge(search_count) AS searches
        FROM artist_search_counts_hourly
        WHERE hour_start >= {previous_start:DateTime} AND hour_start < {current_start:DateTime}
        GROUP BY artist_name, key_epoch
    )
    GROUP BY artist_name
),
previous_ranked AS (
    SELECT
        artist_name,
        row_number() OVER (ORDER BY searches DESC, artist_name ASC) AS position
    FROM previous_period
),
seen_before AS (
    SELECT DISTINCT artist_name
    FROM artist_search_counts_hourly
    WHERE hour_start < {previous_start:DateTime}
)
SELECT
    current_ranked.position,
    current_ranked.artist_name,
    current_ranked.searches,
    current_ranked.listeners,
    current_ranked.epoch_count,
    previous_ranked.position AS previous_position,
    current_ranked.artist_name IN (SELECT artist_name FROM seen_before) AS was_seen_before
FROM current_ranked
LEFT JOIN previous_ranked USING (artist_name)
ORDER BY current_ranked.position
LIMIT {page_size:UInt32} OFFSET {offset:UInt32}
"""

TRACK_CHART_QUERY = """
WITH
current_by_epoch AS (
    SELECT
        artist_name,
        track_name,
        key_epoch,
        countMerge(search_count) AS searches,
        uniqMerge(unique_searchers) AS listeners
    FROM track_search_counts_hourly
    WHERE hour_start >= {current_start:DateTime} AND hour_start < {current_end:DateTime}
    GROUP BY artist_name, track_name, key_epoch
),
current_period AS (
    SELECT
        artist_name,
        track_name,
        sum(searches) AS searches,
        max(listeners) AS listeners,
        count() AS epoch_count
    FROM current_by_epoch
    GROUP BY artist_name, track_name
),
current_ranked AS (
    SELECT
        artist_name,
        track_name,
        searches,
        listeners,
        epoch_count,
        row_number() OVER (ORDER BY searches DESC, artist_name ASC, track_name ASC) AS position
    FROM current_period
),
previous_period AS (
    SELECT artist_name, track_name, sum(searches) AS searches
    FROM (
        SELECT artist_name, track_name, key_epoch, countMerge(search_count) AS searches
        FROM track_search_counts_hourly
        WHERE hour_start >= {previous_start:DateTime} AND hour_start < {current_start:DateTime}
        GROUP BY artist_name, track_name, key_epoch
    )
    GROUP BY artist_name, track_name
),
previous_ranked AS (
    SELECT
        artist_name,
        track_name,
        row_number() OVER (ORDER BY searches DESC, artist_name ASC, track_name ASC) AS position
    FROM previous_period
)
SELECT
    current_ranked.position,
    current_ranked.artist_name,
    current_ranked.track_name,
    current_ranked.searches,
    current_ranked.listeners,
    current_ranked.epoch_count,
    previous_ranked.position AS previous_position
FROM current_ranked
LEFT JOIN previous_ranked USING (artist_name, track_name)
ORDER BY current_ranked.position
LIMIT {page_size:UInt32} OFFSET {offset:UInt32}
"""

ARTIST_TIME_SERIES_QUERY = """
SELECT
    day,
    sum(searches) AS searches,
    max(listeners) AS listeners,
    count() AS epoch_count
FROM (
    SELECT
        toStartOfDay(hour_start) AS day,
        key_epoch,
        countMerge(search_count) AS searches,
        uniqMerge(unique_searchers) AS listeners
    FROM artist_search_counts_hourly
    WHERE artist_name = {artist_name:String} AND hour_start >= {start:DateTime}
    GROUP BY day, key_epoch
)
GROUP BY day
ORDER BY day
"""

ARTIST_TOP_TRACKS_QUERY = """
SELECT
    track_name,
    sum(searches) AS searches,
    max(listeners) AS listeners,
    count() AS epoch_count
FROM (
    SELECT
        track_name,
        key_epoch,
        countMerge(search_count) AS searches,
        uniqMerge(unique_searchers) AS listeners
    FROM track_search_counts_hourly
    WHERE artist_name = {artist_name:String} AND hour_start >= {start:DateTime}
    GROUP BY track_name, key_epoch
)
GROUP BY track_name
ORDER BY searches DESC
LIMIT {page_size:UInt32}
"""

ARTIST_SEARCH_QUERY = """
SELECT
    artist_name,
    sum(searches) AS searches
FROM (
    SELECT artist_name, key_epoch, countMerge(search_count) AS searches
    FROM artist_search_counts_hourly
    WHERE positionCaseInsensitive(artist_name, {query_text:String}) > 0
      AND hour_start >= {start:DateTime}
    GROUP BY artist_name, key_epoch
)
GROUP BY artist_name
ORDER BY searches DESC
LIMIT {page_size:UInt32}
"""


def listeners_or_none(listeners: Any, epoch_count: Any) -> int | None:
    """Withhold the count when the window spans two pseudonymization keys."""
    return int(listeners) if int(epoch_count) == 1 else None


@dataclass(frozen=True)
class ArtistChartEntry:
    position: int
    artist_name: str
    searches: int
    listeners: int | None
    movement: Movement


@dataclass(frozen=True)
class TrackChartEntry:
    position: int
    artist_name: str
    track_name: str
    searches: int
    listeners: int | None
    movement: Movement


@dataclass(frozen=True)
class TimeSeriesPoint:
    day: datetime
    searches: int
    listeners: int | None


@dataclass(frozen=True)
class TrackSummary:
    track_name: str
    searches: int
    listeners: int | None


def read_artist_chart(
    client: Any,
    window: PeriodWindow,
    page_size: int,
    offset: int,
) -> list[ArtistChartEntry]:
    result = client.query(
        ARTIST_CHART_QUERY,
        parameters={
            "current_start": window.current_start,
            "current_end": window.current_end,
            "previous_start": window.previous_start,
            "page_size": min(page_size, MAXIMUM_PAGE_SIZE),
            "offset": offset,
        },
    )
    return [
        ArtistChartEntry(
            position=int(row[0]),
            artist_name=str(row[1]),
            searches=int(row[2]),
            listeners=listeners_or_none(row[3], row[4]),
            movement=describe_movement(int(row[0]), int(row[5]), bool(row[6])),
        )
        for row in result.result_rows
    ]


def read_track_chart(
    client: Any,
    window: PeriodWindow,
    page_size: int,
    offset: int,
) -> list[TrackChartEntry]:
    result = client.query(
        TRACK_CHART_QUERY,
        parameters={
            "current_start": window.current_start,
            "current_end": window.current_end,
            "previous_start": window.previous_start,
            "page_size": min(page_size, MAXIMUM_PAGE_SIZE),
            "offset": offset,
        },
    )
    return [
        TrackChartEntry(
            position=int(row[0]),
            artist_name=str(row[1]),
            track_name=str(row[2]),
            searches=int(row[3]),
            listeners=listeners_or_none(row[4], row[5]),
            # Tracks do not distinguish a re-entry from a new entry: the extra
            # lifetime lookup is not worth its cost at track cardinality.
            movement=describe_movement(int(row[0]), int(row[6]), seen_before=False),
        )
        for row in result.result_rows
    ]


def read_artist_time_series(
    client: Any,
    artist_name: str,
    start: datetime,
) -> list[TimeSeriesPoint]:
    result = client.query(
        ARTIST_TIME_SERIES_QUERY,
        parameters={"artist_name": artist_name, "start": start},
    )
    return [
        TimeSeriesPoint(
            day=row[0],
            searches=int(row[1]),
            listeners=listeners_or_none(row[2], row[3]),
        )
        for row in result.result_rows
    ]


def read_artist_top_tracks(
    client: Any,
    artist_name: str,
    start: datetime,
    page_size: int,
) -> list[TrackSummary]:
    result = client.query(
        ARTIST_TOP_TRACKS_QUERY,
        parameters={
            "artist_name": artist_name,
            "start": start,
            "page_size": min(page_size, MAXIMUM_PAGE_SIZE),
        },
    )
    return [
        TrackSummary(
            track_name=str(row[0]),
            searches=int(row[1]),
            listeners=listeners_or_none(row[2], row[3]),
        )
        for row in result.result_rows
    ]


def search_artists(
    client: Any,
    query_text: str,
    start: datetime,
    page_size: int,
) -> list[tuple[str, int]]:
    result = client.query(
        ARTIST_SEARCH_QUERY,
        parameters={
            "query_text": query_text,
            "start": start,
            "page_size": min(page_size, MAXIMUM_PAGE_SIZE),
        },
    )
    return [(str(row[0]), int(row[1])) for row in result.result_rows]
