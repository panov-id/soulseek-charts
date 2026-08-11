#!/usr/bin/env bash
# Apply pending migrations to the configured ClickHouse database.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose up --detach --wait clickhouse
docker compose run --rm --build --entrypoint python api -m soulseek_charts.storage
