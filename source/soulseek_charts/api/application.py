"""FastAPI application serving the charts.

Everything lives under /api/v1: the shape of a chart entry is a public
contract, and breaking it later must require a new version rather than a
silent change.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from soulseek_charts import __version__
from soulseek_charts.api.cache import ResponseCache
from soulseek_charts.api.dependencies import get_client, get_response_cache
from soulseek_charts.charts import repository
from soulseek_charts.charts.periods import ChartPeriod, resolve_period
from soulseek_charts.charts.repository import MAXIMUM_PAGE_SIZE

DEFAULT_PAGE_SIZE = 50
DEFAULT_HISTORY_DAYS = 90

STATIC_DIRECTORY = Path(__file__).parent.parent / "web" / "static"

application = FastAPI(
    title="soulseek-charts",
    version=__version__,
    description="What the Soulseek network is looking for.",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)

PageSize = Annotated[int, Query(ge=1, le=MAXIMUM_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


class MovementModel(BaseModel):
    kind: str = Field(description="new, re_entry, up, down or unchanged")
    positions: int | None = Field(
        default=None,
        description="Positions gained or lost; null when the entry is absent from the "
        "previous period",
    )


class ArtistChartEntryModel(BaseModel):
    position: int
    artist_name: str
    searches: int
    listeners: int | None = Field(
        default=None,
        description="Distinct people; null when the window spans two "
        "pseudonymization keys, where the same person would be counted twice",
    )
    movement: MovementModel


class TrackChartEntryModel(BaseModel):
    position: int
    artist_name: str
    track_name: str
    searches: int
    listeners: int | None = None
    movement: MovementModel


class ChartModel(BaseModel):
    period: ChartPeriod
    period_start: datetime
    period_end: datetime
    page_size: int
    offset: int
    entries: list[ArtistChartEntryModel] | list[TrackChartEntryModel]


class TimeSeriesPointModel(BaseModel):
    day: datetime
    searches: int
    listeners: int | None = None


class TrackSummaryModel(BaseModel):
    track_name: str
    searches: int
    listeners: int | None = None


class ArtistDetailModel(BaseModel):
    artist_name: str
    history: list[TimeSeriesPointModel]
    top_tracks: list[TrackSummaryModel]


class ArtistSearchResultModel(BaseModel):
    artist_name: str
    searches: int


class HealthModel(BaseModel):
    status: str
    version: str


def _history_start(days: int) -> datetime:
    return (datetime.now(tz=UTC) - timedelta(days=days)).replace(tzinfo=None)


@application.get("/health", response_model=HealthModel)
def read_health() -> HealthModel:
    return HealthModel(status="ok", version=__version__)


@application.get("/api/v1/charts/artists", response_model=ChartModel)
def read_artist_chart(
    cache: Annotated[ResponseCache, Depends(get_response_cache)],
    period: ChartPeriod = ChartPeriod.WEEK,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ChartModel:
    window = resolve_period(period)
    cache_key = f"artists:{period}:{window.current_start}:{page_size}:{offset}"

    entries = cache.get_or_call(
        cache_key,
        lambda: repository.read_artist_chart(get_client(), window, page_size, offset),
    )

    return ChartModel(
        period=period,
        period_start=window.current_start,
        period_end=window.current_end,
        page_size=page_size,
        offset=offset,
        entries=[
            ArtistChartEntryModel(
                position=entry.position,
                artist_name=entry.artist_name,
                searches=entry.searches,
                listeners=entry.listeners,
                movement=MovementModel(
                    kind=entry.movement.kind, positions=entry.movement.positions
                ),
            )
            for entry in entries
        ],
    )


@application.get("/api/v1/charts/tracks", response_model=ChartModel)
def read_track_chart(
    cache: Annotated[ResponseCache, Depends(get_response_cache)],
    period: ChartPeriod = ChartPeriod.WEEK,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ChartModel:
    window = resolve_period(period)
    cache_key = f"tracks:{period}:{window.current_start}:{page_size}:{offset}"

    entries = cache.get_or_call(
        cache_key,
        lambda: repository.read_track_chart(get_client(), window, page_size, offset),
    )

    return ChartModel(
        period=period,
        period_start=window.current_start,
        period_end=window.current_end,
        page_size=page_size,
        offset=offset,
        entries=[
            TrackChartEntryModel(
                position=entry.position,
                artist_name=entry.artist_name,
                track_name=entry.track_name,
                searches=entry.searches,
                listeners=entry.listeners,
                movement=MovementModel(
                    kind=entry.movement.kind, positions=entry.movement.positions
                ),
            )
            for entry in entries
        ],
    )


@application.get(
    "/api/v1/charts/artists.csv",
    response_class=PlainTextResponse,
    summary="The artist chart as CSV, for researchers",
)
def export_artist_chart(
    period: ChartPeriod = ChartPeriod.WEEK,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> PlainTextResponse:
    window = resolve_period(period)
    entries = repository.read_artist_chart(get_client(), window, page_size, offset=0)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["position", "artist_name", "searches", "listeners", "movement", "positions"])
    for entry in entries:
        writer.writerow(
            [
                entry.position,
                entry.artist_name,
                entry.searches,
                entry.listeners if entry.listeners is not None else "",
                entry.movement.kind,
                entry.movement.positions if entry.movement.positions is not None else "",
            ]
        )

    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="artists-{period}.csv"'},
    )


@application.get("/api/v1/artists/{artist_name}", response_model=ArtistDetailModel)
def read_artist_detail(
    artist_name: str,
    cache: Annotated[ResponseCache, Depends(get_response_cache)],
    history_days: Annotated[int, Query(ge=1, le=365)] = DEFAULT_HISTORY_DAYS,
) -> ArtistDetailModel:
    start = _history_start(history_days)
    cache_key = f"artist:{artist_name}:{history_days}"

    def load() -> ArtistDetailModel:
        client = get_client()
        return ArtistDetailModel(
            artist_name=artist_name,
            history=[
                TimeSeriesPointModel(
                    day=point.day, searches=point.searches, listeners=point.listeners
                )
                for point in repository.read_artist_time_series(client, artist_name, start)
            ],
            top_tracks=[
                TrackSummaryModel(
                    track_name=track.track_name,
                    searches=track.searches,
                    listeners=track.listeners,
                )
                for track in repository.read_artist_top_tracks(
                    client, artist_name, start, DEFAULT_PAGE_SIZE
                )
            ],
        )

    detail: ArtistDetailModel = cache.get_or_call(cache_key, load)
    return detail


@application.get("/api/v1/search", response_model=list[ArtistSearchResultModel])
def search_artists(
    query: Annotated[str, Query(min_length=2, max_length=100)],
    history_days: Annotated[int, Query(ge=1, le=365)] = DEFAULT_HISTORY_DAYS,
    page_size: PageSize = 20,
) -> list[ArtistSearchResultModel]:
    matches = repository.search_artists(
        get_client(), query, _history_start(history_days), page_size
    )
    return [
        ArtistSearchResultModel(artist_name=artist_name, searches=searches)
        for artist_name, searches in matches
    ]


# Mounted last: the API routes above are matched first, everything else is the
# dashboard.
application.mount("/", StaticFiles(directory=STATIC_DIRECTORY, html=True), name="dashboard")
