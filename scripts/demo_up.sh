#!/usr/bin/env bash
# Start the dashboard against a generated demo history, so the interface can be
# reviewed before real collection exists. Uses its own database and leaves the
# real one untouched. Tear it down with scripts/demo_down.sh.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

demo_database="demo_dashboard"

run_query() {
    docker compose exec -T clickhouse clickhouse-client --query "$1"
}

docker compose up --detach --wait clickhouse

run_query "DROP DATABASE IF EXISTS ${demo_database}"

docker compose run --rm --build --entrypoint python \
    --env "CLICKHOUSE_DATABASE=${demo_database}" \
    api -m soulseek_charts.storage

echo "=== Generating 45 days of demo history ==="
# Deterministic pseudo-random traffic: each artist has a weight out of 10, and
# a hash decides which day/slot combinations produced a search.
run_query "
INSERT INTO ${demo_database}.parsed_search_queries
    (received_at, searcher_pseudonym, ticket, query_text,
     artist_name, album_name, track_name, parse_confidence, parser_version)
SELECT
    now() - toIntervalDay(days.day_offset) - toIntervalHour(slots.slot) AS received_at,
    toFixedString(hex(sipHash64(toString(slots.slot % 7))), 16) AS searcher_pseudonym,
    toUInt32(cityHash64(days.day_offset, catalogue.entry.1, slots.slot) % 4000000000) AS ticket,
    concat(catalogue.entry.1, ' ', catalogue.entry.2) AS query_text,
    catalogue.entry.1 AS artist_name,
    '' AS album_name,
    catalogue.entry.2 AS track_name,
    toFloat32(0.9) AS parse_confidence,
    toUInt16(1) AS parser_version
FROM (SELECT number AS day_offset FROM numbers(45)) AS days
CROSS JOIN (
    SELECT arrayJoin([
        ('aphex twin', 'windowlicker', 7),
        ('boards of canada', 'roygbiv', 6),
        ('burial', 'archangel', 5),
        ('autechre', 'gantz graf', 4),
        ('nils frahm', 'says', 3),
        ('four tet', 'two thousand and seventeen', 3),
        ('portishead', 'glory box', 2),
        ('dj shadow', 'midnight in a perfect world', 2)
    ]) AS entry
) AS catalogue
CROSS JOIN (SELECT number AS slot FROM numbers(10)) AS slots
WHERE (cityHash64(days.day_offset, catalogue.entry.1, slots.slot) % 10)
      < toUInt64(catalogue.entry.3)
"

run_query "
SELECT count() AS rows, uniq(artist_name) AS artists
FROM ${demo_database}.parsed_search_queries
FORMAT PrettyCompactMonoBlock
"

echo "=== Starting the dashboard ==="
docker rm --force soulseek_charts_demo_api >/dev/null 2>&1 || true
docker compose run --detach --service-ports --name soulseek_charts_demo_api \
    --env "CLICKHOUSE_DATABASE=${demo_database}" api >/dev/null

for _ in $(seq 1 30); do
    if curl --silent --fail http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "Dashboard: http://127.0.0.1:8000/"
echo "API docs:  http://127.0.0.1:8000/api/v1/docs"
