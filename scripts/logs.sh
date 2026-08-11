#!/usr/bin/env bash
# Follow logs of every service, or of the service named as the first argument.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose logs --follow --tail 200 "$@"
