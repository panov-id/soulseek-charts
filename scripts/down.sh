#!/usr/bin/env bash
# Stop the stack. Pass --volumes to drop collected data as well.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose down "$@"
