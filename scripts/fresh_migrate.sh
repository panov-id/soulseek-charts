#!/usr/bin/env bash
# Verify that migrations bring an EMPTY database to the full schema, and that
# running them twice changes nothing. A throwaway database is used and dropped,
# so the real data is never touched.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

throwaway_database="fresh_migrate_check"

cleanup() {
    docker compose exec -T clickhouse clickhouse-client \
        --query "DROP DATABASE IF EXISTS ${throwaway_database}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up --detach --wait clickhouse
cleanup

echo "=== First run: empty database ==="
docker compose run --rm --build --entrypoint python \
    --env "CLICKHOUSE_DATABASE=${throwaway_database}" \
    api -m soulseek_charts.storage

echo "=== Second run: must apply nothing ==="
docker compose run --rm --entrypoint python \
    --env "CLICKHOUSE_DATABASE=${throwaway_database}" \
    api -m soulseek_charts.storage

echo "=== Resulting schema ==="
docker compose exec -T clickhouse clickhouse-client \
    --query "SHOW TABLES FROM ${throwaway_database}"
