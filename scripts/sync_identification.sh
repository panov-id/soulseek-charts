#!/usr/bin/env bash
# External identification for the small jump host.
#
# The jump (1.9 GiB) cannot resolve against the 3M-name catalogue in process,
# but it CAN serve the resulting charts. So resolution runs here, on a host with
# the catalogue and the RAM, and only the compact aggregates travel back:
#
#   1. pull new raw events from the jump into the local ClickHouse
#   2. reprocess incrementally here, against the catalogue
#   3. ship the refreshed aggregates to the jump, swapped in atomically
#
# The jump keeps collecting throughout; charts never go empty during a sync.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

ssh_target="root@jump"
ssh_key="$HOME/.ssh/vpn_deploy_ed25519"
remote_container="soulseek_charts_clickhouse"
buckets=20

local_ch() { docker compose exec -T clickhouse clickhouse-client "$@"; }
jump_ch() { ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" "docker exec -i ${remote_container} clickhouse-client $*"; }

# --- 1. Pull new raw from the jump ------------------------------------------

watermark="$(local_ch --query "SELECT max(received_at) FROM soulseek_charts.search_query_events")"
echo "Local raw watermark: ${watermark}"

new_on_jump="$(ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "docker exec -i ${remote_container} clickhouse-client --query \"SELECT count() FROM soulseek_charts.search_query_events WHERE received_at > '${watermark}'\"")"
echo "New raw rows on the jump: ${new_on_jump}"

if [ "${new_on_jump}" -gt 0 ]; then
    echo "=== Pulling new raw, one hour at a time ==="
    mapfile -t hours < <(ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
        "docker exec -i ${remote_container} clickhouse-client --query \"SELECT DISTINCT toStartOfHour(received_at) FROM soulseek_charts.search_query_events WHERE received_at > '${watermark}' ORDER BY 1 FORMAT TSV\"")
    for hour in "${hours[@]}"; do
        [ -z "$hour" ] && continue
        ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
            "docker exec -i ${remote_container} clickhouse-client --query \"SELECT * FROM soulseek_charts.search_query_events WHERE toStartOfHour(received_at) = '${hour}' AND received_at > '${watermark}' FORMAT Native\"" \
            | local_ch --query "INSERT INTO soulseek_charts.search_query_events FORMAT Native"
    done
fi

# --- 2. Resolve incrementally here ------------------------------------------

echo "=== Reprocessing incrementally against the catalogue ==="
docker compose run --rm --entrypoint python api \
    -m soulseek_charts.parsing.reprocess_command --incremental

# --- 3. Ship aggregates to the jump, swapped in atomically ------------------

for table in artist_search_counts_hourly track_search_counts_hourly; do
    staging="${table}_incoming"
    echo "=== Shipping ${table} ==="
    jump_ch --query "\"CREATE TABLE IF NOT EXISTS soulseek_charts.${staging} AS soulseek_charts.${table}\""
    jump_ch --query "\"TRUNCATE TABLE soulseek_charts.${staging}\""

    for bucket in $(seq 0 $((buckets - 1))); do
        local_ch --query "SELECT * FROM soulseek_charts.${table} FINAL WHERE cityHash64(artist_name) % ${buckets} = ${bucket} FORMAT Native" \
            < /dev/null \
            | ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
                "docker exec -i ${remote_container} clickhouse-client --max_memory_usage=250000000 --max_insert_block_size=25000 --max_threads=1 --query 'INSERT INTO soulseek_charts.${staging} FORMAT Native'"
    done

    # Atomic swap: the live table is replaced without a moment of emptiness.
    jump_ch --query "\"EXCHANGE TABLES soulseek_charts.${table} AND soulseek_charts.${staging}\""
    echo "  ${table} swapped in"
done

local_rows="$(local_ch --query "SELECT count() FROM soulseek_charts.artist_search_counts_hourly FINAL")"
jump_rows="$(jump_ch --query "'SELECT count() FROM soulseek_charts.artist_search_counts_hourly FINAL'")"
echo "Artist aggregate rows — local ${local_rows}, jump ${jump_rows}"
echo "Sync complete."
