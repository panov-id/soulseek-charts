"""Shared API dependencies.

The ClickHouse client is created on first use rather than at import time, so
importing the application (in tests, or to inspect the OpenAPI schema) does not
require a running database.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from soulseek_charts.api.cache import ResponseCache
from soulseek_charts.configuration import ClickHouseConfiguration
from soulseek_charts.storage.client import create_client


@lru_cache(maxsize=1)
def get_client() -> Any:
    return create_client(ClickHouseConfiguration.from_environment())


@lru_cache(maxsize=1)
def get_response_cache() -> ResponseCache:
    return ResponseCache()
