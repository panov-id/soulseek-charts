#!/usr/bin/env bash
# Transfer the collected raw events from the local ClickHouse to the jump.
#
# Only search_query_events moves — it is the source of truth. The parsed layer
# and the hourly aggregates are rebuilt on the jump by reprocessing, so nothing
# derived is copied and no layer can arrive out of sync.
#
# Run AFTER the local collector is stopped, so the snapshot is final and the
# single Soulseek session is free for the jump collector to take.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

ssh_target="root@jump"
ssh_key="$HOME/.ssh/vpn_deploy_ed25519"
remote_directory="/opt/soulseek-charts"
remote_container="soulseek_charts_clickhouse"

if docker ps --format '{{.Names}}' | grep -q '^soulseek_charts_collector$' \
    && [ "$(docker inspect -f '{{.State.Running}}' soulseek_charts_collector 2>/dev/null)" = "true" ]; then
    echo "The local collector is still running. Stop it first so the snapshot is" >&2
    echo "final and the Soulseek session is free:  docker compose stop collector" >&2
    exit 1
fi

local_rows="$(docker compose exec -T clickhouse clickhouse-client \
    --query "SELECT count() FROM soulseek_charts.search_query_events")"
echo "Local search_query_events: ${local_rows} rows"

# The jump ClickHouse is capped at 700 MiB, so a single 2.8M-row insert blows
# the budget. Transfer one day at a time, in small blocks, so peak memory on
# the jump stays low.
remote_insert="docker exec -i ${remote_container} clickhouse-client \
    --max_memory_usage=250000000 --max_insert_block_size=25000 --max_threads=1 \
    --query 'INSERT INTO soulseek_charts.search_query_events FORMAT Native'"

echo "=== Clearing any partial data on the jump for a clean transfer ==="
ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "docker exec -i ${remote_container} clickhouse-client --query 'TRUNCATE TABLE soulseek_charts.search_query_events'"

echo "=== Streaming rows to the jump, one hour at a time (Native, gzipped) ==="
# Hourly chunks (~40k rows each) keep every insert far under the jump's memory
# ceiling, so the conservative 700 MiB server limit can stay in place for the
# steady state instead of being raised for a one-off load.
#
# The hour list is read into an array first: a producer inside the loop reads
# stdin, and driving the loop from stdin would let it eat the remaining hours
# after the first iteration. Each producer also gets </dev/null for the same
# reason.
mapfile -t hour_list < <(docker compose exec -T clickhouse clickhouse-client \
    --query "SELECT DISTINCT toStartOfHour(received_at) FROM soulseek_charts.search_query_events ORDER BY 1 FORMAT TSV")

transferred=0
for hour in "${hour_list[@]}"; do
    [ -z "$hour" ] && continue
    docker compose exec -T clickhouse clickhouse-client \
        --query "SELECT * FROM soulseek_charts.search_query_events WHERE toStartOfHour(received_at) = '${hour}' FORMAT Native" \
        < /dev/null \
        | gzip \
        | ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" "gunzip | ${remote_insert}"
    transferred=$((transferred + 1))
    printf '\r  %d/%d hours transferred' "$transferred" "${#hour_list[@]}"
done
echo ""

remote_rows="$(ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "docker exec -i ${remote_container} clickhouse-client --query 'SELECT count() FROM soulseek_charts.search_query_events'")"
echo "Jump search_query_events: ${remote_rows} rows"

if [ "$local_rows" != "$remote_rows" ]; then
    echo "Row counts differ (local ${local_rows} vs jump ${remote_rows})." >&2
    echo "Not proceeding to reprocess; investigate before starting the collector." >&2
    exit 1
fi

echo "=== Rebuilding the parsed layer and aggregates on the jump ==="
ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "cd ${remote_directory} && docker compose -f docker-compose.jump.yml run --rm --entrypoint python api -m soulseek_charts.parsing.reprocess_command"

echo "Done. Rows match (${remote_rows}) and the jump aggregates are rebuilt."
echo "Next: start the collector on the jump:"
echo "  ssh root@jump 'cd ${remote_directory} && docker compose -f docker-compose.jump.yml up -d collector api'"
