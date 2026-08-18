#!/usr/bin/env bash
# Cron wrapper for sync_identification.sh.
#
# Runs a single instance at a time (flock), gives cron a sane PATH and HOME,
# logs to sync.log, and never lets a failed sync break the schedule. Cron
# fires this every two hours; the actual work is in sync_identification.sh.
set -uo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
export HOME="${HOME:-/home/eugene-panov}"

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

log="$project_root/sync.log"
lock="$project_root/.sync.lock"

# One sync at a time: a run can outlast the two-hour interval on a big catch-up,
# and overlapping syncs would fight over the same tables.
exec 9>"$lock"
if ! flock -n 9; then
    echo "$(date -Iseconds) skipped: a previous sync is still running" >>"$log"
    exit 0
fi

{
    echo "=== $(date -Iseconds) sync start ==="
    if ./scripts/sync_identification.sh; then
        echo "=== $(date -Iseconds) sync ok ==="
    else
        echo "=== $(date -Iseconds) sync FAILED (exit $?) ==="
    fi
} >>"$log" 2>&1

# Keep the log bounded.
if [ "$(wc -l <"$log")" -gt 5000 ]; then
    tail -n 2000 "$log" >"$log.tmp" && mv "$log.tmp" "$log"
fi
