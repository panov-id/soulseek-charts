#!/usr/bin/env bash
# Ship the working tree to the jump host and bring up ClickHouse there.
#
# The .env (credentials and the pseudonymization key) is copied separately with
# tight permissions and is never placed in the code tarball. Nothing is
# committed or pushed; the current working tree is what deploys.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

ssh_target="root@jump"
ssh_key="$HOME/.ssh/vpn_deploy_ed25519"
remote_directory="/opt/soulseek-charts"

ssh_run() {
    ssh -i "$ssh_key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$ssh_target" "$@"
}

echo "=== Preparing remote directory ==="
ssh_run "mkdir -p ${remote_directory}"

echo "=== Shipping code (tracked source, no data, no secrets) ==="
# Only what the stack needs to build and run. Explicit list keeps archive,
# screenshots, caches and the local .env out.
tar --exclude='__pycache__' --exclude='*.pyc' -czf - \
    source infrastructure scripts pyproject.toml docker-compose.jump.yml \
    | ssh_run "tar -xzf - -C ${remote_directory}"

echo "=== Shipping .env separately (mode 600) ==="
scp -i "$ssh_key" -o BatchMode=yes .env "${ssh_target}:${remote_directory}/.env"
ssh_run "chmod 600 ${remote_directory}/.env"

echo "=== Bringing up ClickHouse on the jump ==="
ssh_run "cd ${remote_directory} && docker compose -f docker-compose.jump.yml up -d --wait clickhouse"

echo "=== Applying migrations ==="
ssh_run "cd ${remote_directory} && docker compose -f docker-compose.jump.yml run --rm --build --entrypoint python api -m soulseek_charts.storage"

echo "Done. ClickHouse is up and migrated on the jump."
echo "Next: scripts/migrate_data_to_jump.sh to transfer the collected rows,"
echo "then start the collector there."
