#!/usr/bin/env bash
# Reproduces the central claim of this project: one ordinary node sees
# essentially the whole search stream, so a second node adds nothing.
#
# Method: attach to several parents at once, tag every query with the parent
# that relayed it, then compare the sets. If depth in the tree reduced what a
# node sees, parents at different branch levels would deliver different queries.
#
#   1. Capture with several parents, from the probe directory:
#
#        VERBOSE=1 PARENTS=3 OUTPUT_NAME=coverage.jsonl bash run.sh 4m
#
#   2. Analyse:
#
#        bash coverage_experiment.sh /path/to/probe/results/coverage.jsonl
#
# Measured on 9 August 2026 with parents at branch levels 4, 6 and 6:
# 11 018 distinct queries in the common window, pairwise Jaccard 0.995–0.999,
# 99.4% of queries seen from all three parents, 0.3% from exactly one.
set -euo pipefail

file="${1:-}"
if [ -z "$file" ] || [ ! -f "$file" ]; then
    echo "usage: bash coverage_experiment.sh <coverage.jsonl>" >&2
    exit 1
fi

python3 - "$file" <<'PYTHON'
import json, sys, itertools
from collections import defaultdict

path = sys.argv[1]
records = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
print(f"records: {len(records)}")

by_parent = defaultdict(list)
levels = {}
for record in records:
    by_parent[record["parent"]].append(record["query"])
    levels[record["parent"]] = record.get("level")

print("\n=== per parent ===")
for parent, queries in by_parent.items():
    print(f"  {parent:20s} level {levels[parent]}  {len(queries):6d} queries, "
          f"{len(set(queries)):6d} unique")

# Only the window where every parent was connected: a parent adopted later
# would otherwise look like it delivered less.
first_seen = {parent: min(r["time"] for r in records if r["parent"] == parent)
              for parent in by_parent}
last_seen = {parent: max(r["time"] for r in records if r["parent"] == parent)
             for parent in by_parent}
window_start, window_end = max(first_seen.values()), min(last_seen.values())
print(f"\ncommon window: {window_start} .. {window_end}")

windowed = defaultdict(set)
for record in records:
    if window_start <= record["time"] <= window_end:
        windowed[record["parent"]].add(record["query"])

print("\n=== pairwise overlap ===")
for first, second in itertools.combinations(windowed, 2):
    a, b = windowed[first], windowed[second]
    intersection, union = len(a & b), len(a | b)
    print(f"  {first} vs {second}: intersection {intersection}, union {union}, "
          f"Jaccard {intersection/union:.3f}")

everywhere = set.intersection(*windowed.values())
anywhere = set.union(*windowed.values())
only_one = sum(1 for query in anywhere
               if sum(query in queries for queries in windowed.values()) == 1)
print(f"\nseen from every parent: {len(everywhere)} of {len(anywhere)} "
      f"({100*len(everywhere)/len(anywhere):.1f}%)")
print(f"seen from exactly one:  {only_one} ({100*only_one/len(anywhere):.1f}%)")
PYTHON
