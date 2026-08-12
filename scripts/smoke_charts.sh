#!/usr/bin/env bash
# End-to-end check of the aggregation layer: insert sample parsed queries into
# a throwaway database and read a chart back through the materialized views.
# Proves that the AggregateFunction columns and the views actually work.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

throwaway_database="smoke_charts_check"

run_query() {
    docker compose exec -T clickhouse clickhouse-client --query "$1"
}

cleanup() {
    run_query "DROP DATABASE IF EXISTS ${throwaway_database}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up --detach --wait clickhouse
cleanup

docker compose run --rm --build --entrypoint python \
    --env "CLICKHOUSE_DATABASE=${throwaway_database}" \
    api -m soulseek_charts.storage

echo "=== Inserting sample parsed queries ==="
# Two distinct listeners look for Aphex Twin, one of them twice; a third
# listener looks for Boards of Canada once.
run_query "
INSERT INTO ${throwaway_database}.parsed_search_queries
    (received_at, searcher_pseudonym, ticket, query_text,
     artist_name, album_name, track_name, parse_confidence, parser_version)
VALUES
    ('2026-08-11 10:00:00.000', '0000000000000001', 1,
     'aphex twin windowlicker', 'aphex twin', '', 'windowlicker', 0.9, 1),
    ('2026-08-11 10:05:00.000', '0000000000000001', 2,
     'aphex twin come to daddy', 'aphex twin', '', 'come to daddy', 0.9, 1),
    ('2026-08-11 10:07:00.000', '0000000000000002', 3,
     'aphex twin windowlicker flac', 'aphex twin', '', 'windowlicker', 0.8, 1),
    ('2026-08-11 10:30:00.000', '0000000000000003', 4,
     'boards of canada dayvan cowboy', 'boards of canada', '', 'dayvan cowboy', 0.9, 1)
"

echo "=== Artist chart (hourly states merged) ==="
run_query "
SELECT
    artist_name,
    countMerge(search_count) AS searches,
    uniqMerge(unique_searchers) AS listeners
FROM ${throwaway_database}.artist_search_counts_hourly
GROUP BY artist_name
ORDER BY searches DESC
FORMAT PrettyCompactMonoBlock
"

echo "=== Track chart ==="
run_query "
SELECT
    artist_name,
    track_name,
    countMerge(search_count) AS searches,
    uniqMerge(unique_searchers) AS listeners
FROM ${throwaway_database}.track_search_counts_hourly
GROUP BY artist_name, track_name
ORDER BY searches DESC
FORMAT PrettyCompactMonoBlock
"
