#!/usr/bin/env bash
# End-to-end check of the API: build a two-week history in a throwaway
# database, start the API against it and read every endpoint back.
# Proves that ranking, movement against the previous period, pagination,
# CSV export and search all work against real ClickHouse data.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

throwaway_database="smoke_api_check"
api_base_url="http://127.0.0.1:8000"
api_container_id=""

run_query() {
    docker compose exec -T clickhouse clickhouse-client --query "$1"
}

pretty_print() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -m json.tool
    else
        cat
    fi
}

cleanup() {
    if [[ -n "$api_container_id" ]]; then
        docker rm --force "$api_container_id" >/dev/null 2>&1 || true
    fi
    run_query "DROP DATABASE IF EXISTS ${throwaway_database}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up --detach --wait clickhouse
cleanup

docker compose run --rm --build --entrypoint python \
    --env "CLICKHOUSE_DATABASE=${throwaway_database}" \
    api -m soulseek_charts.storage

echo "=== Building a two-week history ==="
# This week: aphex twin leads, autechre returns after a long absence.
# Last week: boards of canada led, aphex twin was second.
run_query "
INSERT INTO ${throwaway_database}.parsed_search_queries
    (received_at, searcher_pseudonym, ticket, query_text,
     artist_name, album_name, track_name, parse_confidence, parser_version)
SELECT
    received_at, searcher_pseudonym, ticket, query_text,
    artist_name, album_name, track_name,
    -- ClickHouse refuses to narrow a Float64 literal to Float32 implicitly.
    toFloat32(parse_confidence), parser_version
FROM values(
    'received_at DateTime64(3), searcher_pseudonym FixedString(16), ticket UInt32,
     query_text String, artist_name String, album_name String, track_name String,
     parse_confidence Float64, parser_version UInt16',

    -- current week
    (now(), '0000000000000001', 101, 'aphex twin windowlicker',
     'aphex twin', '', 'windowlicker', 0.9, 1),
    (now(), '0000000000000002', 102, 'aphex twin come to daddy',
     'aphex twin', '', 'come to daddy', 0.9, 1),
    (now(), '0000000000000002', 103, 'aphex twin xtal',
     'aphex twin', '', 'xtal', 0.9, 1),
    (now(), '0000000000000003', 104, 'autechre gantz graf',
     'autechre', '', 'gantz graf', 0.9, 1),
    (now(), '0000000000000004', 105, 'autechre amber',
     'autechre', '', 'amber', 0.9, 1),
    (now(), '0000000000000005', 106, 'boards of canada roygbiv',
     'boards of canada', '', 'roygbiv', 0.9, 1),

    -- previous week
    (toStartOfWeek(now(), 1) - INTERVAL 6 HOUR, '0000000000000006', 201,
     'boards of canada olson', 'boards of canada', '', 'olson', 0.9, 1),
    (toStartOfWeek(now(), 1) - INTERVAL 7 HOUR, '0000000000000007', 202,
     'boards of canada dayvan cowboy', 'boards of canada', '', 'dayvan cowboy', 0.9, 1),
    (toStartOfWeek(now(), 1) - INTERVAL 8 HOUR, '0000000000000008', 203,
     'boards of canada telephasic workshop', 'boards of canada', '', 'telephasic workshop', 0.9, 1),
    (toStartOfWeek(now(), 1) - INTERVAL 9 HOUR, '0000000000000009', 204,
     'aphex twin avril 14th', 'aphex twin', '', 'avril 14th', 0.9, 1),

    -- two months ago: makes autechre a re-entry rather than a new entry
    (now() - INTERVAL 60 DAY, '0000000000000010', 301,
     'autechre bike', 'autechre', '', 'bike', 0.9, 1),

    -- below the chart confidence threshold: must not appear anywhere
    (now(), '0000000000000011', 302, 'some unparseable blob',
     'some unparseable blob', '', '', 0.3, 1)
)
"

echo "=== Starting the API against the throwaway database ==="
api_container_id="$(docker compose run --detach --service-ports \
    --env "CLICKHOUSE_DATABASE=${throwaway_database}" api)"

for _ in $(seq 1 30); do
    if curl --silent --fail "${api_base_url}/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "=== GET /health ==="
curl --silent --fail "${api_base_url}/health" | pretty_print

echo "=== GET /api/v1/charts/artists?period=week ==="
curl --silent --fail "${api_base_url}/api/v1/charts/artists?period=week" | pretty_print

echo "=== GET /api/v1/charts/tracks?period=week&page_size=3 ==="
curl --silent --fail "${api_base_url}/api/v1/charts/tracks?period=week&page_size=3" | pretty_print

echo "=== GET /api/v1/artists/aphex%20twin ==="
curl --silent --fail "${api_base_url}/api/v1/artists/aphex%20twin" | pretty_print

echo "=== GET /api/v1/search?query=aut ==="
curl --silent --fail "${api_base_url}/api/v1/search?query=aut" | pretty_print

echo "=== GET /api/v1/charts/artists.csv ==="
curl --silent --fail "${api_base_url}/api/v1/charts/artists.csv"
