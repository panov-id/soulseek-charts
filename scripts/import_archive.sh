#!/usr/bin/env bash
# Import the Go prototype's JSONL archive into ClickHouse.
#
#   ./scripts/import_archive.sh /path/to/collector/data/raw
#   ./scripts/import_archive.sh --limit=50000 /path/to/.../searches-2026-08-12.jsonl
#
# The archive is mounted read-only: this reads it, never writes to it.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

limit_argument=""
if [[ "${1:-}" == --limit=* ]]; then
    limit_argument="$1"
    shift
fi

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 [--limit=N] <archive file or directory>" >&2
    exit 1
fi

archive_path="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"

docker compose up --detach --wait clickhouse
docker compose run --rm --build --entrypoint python \
    --volume "${archive_path}:/archive:ro" \
    api -m soulseek_charts.storage.import_command ${limit_argument:+"$limit_argument"} /archive
