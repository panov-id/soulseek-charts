#!/usr/bin/env bash
# Transfer the MusicBrainz artist catalogue from the local ClickHouse to the
# jump. The catalogue is built locally from the 1.6 GiB dump; only the compact
# table (a few hundred MiB) crosses to the jump.
#
# Sent in hash buckets so each insert stays well under the jump's memory
# ceiling, the same reason the raw transfer was chunked.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

ssh_target="root@jump"
ssh_key="$HOME/.ssh/vpn_deploy_ed25519"
remote_container="soulseek_charts_clickhouse"
buckets=20

remote_insert="docker exec -i ${remote_container} clickhouse-client \
    --max_memory_usage=300000000 --max_insert_block_size=50000 --max_threads=1 \
    --query 'INSERT INTO soulseek_charts.musicbrainz_artists FORMAT Native'"

local_rows="$(docker compose exec -T clickhouse clickhouse-client \
    --query "SELECT count() FROM soulseek_charts.musicbrainz_artists FINAL")"
echo "Local catalogue: ${local_rows} distinct artist keys"

echo "=== Clearing the catalogue on the jump ==="
ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "docker exec -i ${remote_container} clickhouse-client --query 'TRUNCATE TABLE soulseek_charts.musicbrainz_artists'"

echo "=== Streaming the catalogue in ${buckets} buckets (Native, gzipped) ==="
for bucket in $(seq 0 $((buckets - 1))); do
    docker compose exec -T clickhouse clickhouse-client \
        --query "SELECT normalized_name, display_name, token_count
                 FROM soulseek_charts.musicbrainz_artists FINAL
                 WHERE cityHash64(normalized_name) % ${buckets} = ${bucket}
                 FORMAT Native" \
        < /dev/null \
        | gzip \
        | ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" "gunzip | ${remote_insert}"
    printf '\r  %d/%d buckets transferred' "$((bucket + 1))" "$buckets"
done
echo ""

ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "docker exec -i ${remote_container} clickhouse-client --query 'OPTIMIZE TABLE soulseek_charts.musicbrainz_artists FINAL'" || true

remote_rows="$(ssh -i "$ssh_key" -o BatchMode=yes "$ssh_target" \
    "docker exec -i ${remote_container} clickhouse-client --query 'SELECT count() FROM soulseek_charts.musicbrainz_artists FINAL'")"
echo "Jump catalogue: ${remote_rows} distinct artist keys"

if [ "$local_rows" != "$remote_rows" ]; then
    echo "Counts differ (local ${local_rows} vs jump ${remote_rows}); investigate." >&2
    exit 1
fi
echo "Catalogue transferred, counts match (${remote_rows})."
