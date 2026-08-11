#!/usr/bin/env bash
# What is rising: compare a recent window against a longer baseline.
#
#   SOULSEEK_ARCHIVE=/path/to/collector/data/raw bash trends.sh [recent_hours] [baseline_hours]
#
# Two things this gets right, both learned the hard way:
#
#   Demand is compared as a SHARE of the searchers in each window, not as an
#   absolute rate. Collection volume differs between windows — a collector
#   outage, a slow parent — and absolute rates then compare nothing.
#
#   The baseline list is not truncated. Ask for a small top and every item in
#   the recent window's tail is missing from the baseline and looks brand new.
#
# This belongs inside soulseek-charts as a flag; it lives here until then.
set -euo pipefail

if [ -z "${SOULSEEK_ARCHIVE:-}" ]; then
    echo "set SOULSEEK_ARCHIVE to the collector's raw archive directory" >&2
    exit 1
fi
if ! command -v soulseek-charts >/dev/null 2>&1; then
    echo "soulseek-charts not on PATH — run charts/install.sh first" >&2
    exit 1
fi

recent_hours="${1:-3}"
baseline_hours="${2:-24}"
workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT

soulseek-charts -json -top 20000 -since "${recent_hours}h"   > "$workspace/recent.json"
soulseek-charts -json -top 20000 -since "${baseline_hours}h" > "$workspace/baseline.json"

python3 - "$workspace/recent.json" "$workspace/baseline.json" \
         "$recent_hours" "$baseline_hours" <<'PYTHON'
import json, sys

recent = json.load(open(sys.argv[1]))
baseline = json.load(open(sys.argv[2]))
recent_hours, baseline_hours = float(sys.argv[3]), float(sys.argv[4])

def shares(report):
    population = max(report["searchers"], 1)
    return {row["item"]: (row["users"] / population, row["users"], row["searches"])
            for row in report.get("demand", [])}

recent_shares = shares(recent)
baseline_shares = shares(baseline)

print(f"recent:   {recent_hours}h, {recent['total']} queries, {recent['searchers']} searchers")
print(f"baseline: {baseline_hours}h, {baseline['total']} queries, {baseline['searchers']} searchers")

print("\n=== rising: share of searchers, recent vs baseline ===")
rows = []
for item, (share, users, searches) in recent_shares.items():
    # Below this the ratio is noise, not a trend.
    if users < 8:
        continue
    base_share = baseline_shares.get(item, (0, 0, 0))[0]
    factor = share / base_share if base_share > 0 else float("inf")
    rows.append((factor, share, base_share, users, searches, item))

rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
for factor, share, base_share, users, searches, item in rows[:20]:
    mark = "NEW" if factor == float("inf") else f"x{factor:.2f}"
    print(f"  {mark:>6}  {10000*share:5.1f} vs {10000*base_share:5.1f} per 10k searchers"
          f"  ({users} people, {searches} searches)  {item}")

print("\n=== top demand in the recent window ===")
for row in recent.get("demand", [])[:15]:
    print(f"  {row['users']:3d} people {row['searches']:5d} searches  {row['item']}")
PYTHON
