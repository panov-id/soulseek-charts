#!/usr/bin/env bash
# Stop the demo dashboard and drop its database.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker rm --force soulseek_charts_demo_api >/dev/null 2>&1 || true
docker compose exec -T clickhouse clickhouse-client \
    --query "DROP DATABASE IF EXISTS demo_dashboard" >/dev/null 2>&1 || true

echo "Demo stopped."
