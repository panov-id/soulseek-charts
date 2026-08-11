import pytest

from soulseek_charts.configuration import (
    ClickHouseConfiguration,
    CollectorConfiguration,
    ConfigurationError,
    read_integer,
)


def test_read_integer_returns_default_when_variable_is_absent(monkeypatch):
    monkeypatch.delenv("COLLECTOR_BATCH_SIZE", raising=False)
    assert read_integer("COLLECTOR_BATCH_SIZE", 1000) == 1000


def test_read_integer_rejects_malformed_value(monkeypatch):
    monkeypatch.setenv("COLLECTOR_BATCH_SIZE", "many")
    with pytest.raises(ConfigurationError):
        read_integer("COLLECTOR_BATCH_SIZE", 1000)


def test_collector_configuration_reads_environment(monkeypatch):
    monkeypatch.setenv("COLLECTOR_BATCH_SIZE", "250")
    monkeypatch.setenv("COLLECTOR_FLUSH_INTERVAL_SECONDS", "2")

    configuration = CollectorConfiguration.from_environment()

    assert configuration.batch_size == 250
    assert configuration.flush_interval_seconds == 2


def test_clickhouse_configuration_falls_back_to_service_defaults(monkeypatch):
    for variable_name in (
        "CLICKHOUSE_HOST",
        "CLICKHOUSE_PORT",
        "CLICKHOUSE_DATABASE",
        "CLICKHOUSE_USER",
        "CLICKHOUSE_PASSWORD",
    ):
        monkeypatch.delenv(variable_name, raising=False)

    configuration = ClickHouseConfiguration.from_environment()

    assert configuration.host == "clickhouse"
    assert configuration.port == 8123
    assert configuration.database == "soulseek_charts"
