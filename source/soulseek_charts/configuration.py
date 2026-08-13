"""Runtime configuration assembled from environment variables.

Every service reads its settings through this module so the set of supported
variables stays visible in one place and matches `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when a required environment variable is missing or malformed."""


def read_text(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ConfigurationError(f"Environment variable {name} is required")
    return value


def read_integer(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        return int(raw_value)
    except ValueError as conversion_error:
        raise ConfigurationError(
            f"Environment variable {name} must be an integer, got {raw_value!r}"
        ) from conversion_error


def read_optional_integer(name: str) -> int | None:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value == "":
        return None
    return read_integer(name, 0)


@dataclass(frozen=True)
class SoulseekConfiguration:
    username: str
    password: str
    server_host: str
    server_port: int
    listening_port: int
    # The server only offers distributed parents to client versions it
    # recognises. Under an unknown version the login succeeds and no parent
    # ever arrives, so the node records nothing. Claiming another project's
    # version makes their client answerable for this one's behaviour, so it is
    # never the default: the operator sets it deliberately or collects nothing.
    client_version_major: int | None
    client_version_minor: int | None

    @property
    def claims_a_version(self) -> bool:
        return self.client_version_major is not None

    @classmethod
    def from_environment(cls) -> SoulseekConfiguration:
        return cls(
            username=read_text("SOULSEEK_USERNAME"),
            password=read_text("SOULSEEK_PASSWORD"),
            server_host=read_text("SOULSEEK_SERVER_HOST", "server.slsknet.org"),
            server_port=read_integer("SOULSEEK_SERVER_PORT", 2416),
            listening_port=read_integer("SOULSEEK_LISTENING_PORT", 2234),
            client_version_major=read_optional_integer("SOULSEEK_CLIENT_VERSION_MAJOR"),
            client_version_minor=read_optional_integer("SOULSEEK_CLIENT_VERSION_MINOR"),
        )


@dataclass(frozen=True)
class ClickHouseConfiguration:
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_environment(cls) -> ClickHouseConfiguration:
        return cls(
            host=read_text("CLICKHOUSE_HOST", "clickhouse"),
            port=read_integer("CLICKHOUSE_PORT", 8123),
            database=read_text("CLICKHOUSE_DATABASE", "soulseek_charts"),
            user=read_text("CLICKHOUSE_USER", "default"),
            password=read_text("CLICKHOUSE_PASSWORD", ""),
        )


@dataclass(frozen=True)
class CollectorConfiguration:
    batch_size: int
    flush_interval_seconds: int

    @classmethod
    def from_environment(cls) -> CollectorConfiguration:
        return cls(
            batch_size=read_integer("COLLECTOR_BATCH_SIZE", 1000),
            flush_interval_seconds=read_integer("COLLECTOR_FLUSH_INTERVAL_SECONDS", 5),
        )


@dataclass(frozen=True)
class PrivacyConfiguration:
    """The hex-encoded key behind the stable pseudonym replacing usernames."""

    hash_secret: str

    @classmethod
    def from_environment(cls) -> PrivacyConfiguration:
        hash_secret = read_text("PRIVACY_HASH_SECRET")
        try:
            key = bytes.fromhex(hash_secret)
        except ValueError as conversion_error:
            raise ConfigurationError(
                "PRIVACY_HASH_SECRET must be hex-encoded; generate one with: openssl rand -hex 32"
            ) from conversion_error

        if len(key) != 32:
            raise ConfigurationError(
                "PRIVACY_HASH_SECRET must decode to 32 bytes (64 hex characters); "
                "generate one with: openssl rand -hex 32"
            )
        return cls(hash_secret=hash_secret)


def read_logging_level() -> str:
    return read_text("LOG_LEVEL", "INFO").upper()
