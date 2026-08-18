#!/usr/bin/env bash
# Install (or refresh) the every-two-hours sync cron entry for this user.
#
# Idempotent: any prior soulseek-charts sync line is removed before the current
# one is written, so re-running never duplicates the entry.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wrapper="$project_root/scripts/sync_cron.sh"
marker="# soulseek-charts sync"
entry="0 */2 * * * ${wrapper} ${marker}"

existing="$(crontab -l 2>/dev/null || true)"
kept="$(printf '%s\n' "$existing" | grep -vF "$marker" | sed '/^[[:space:]]*$/d' || true)"

{
    [ -n "$kept" ] && printf '%s\n' "$kept"
    printf '%s\n' "$entry"
} | crontab -

echo "Cron entry installed (runs at 00:00, 02:00, 04:00, ... local time):"
crontab -l | grep -F "$marker"
