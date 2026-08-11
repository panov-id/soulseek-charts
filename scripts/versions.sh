#!/usr/bin/env bash
# Print the versions of the key dependencies actually installed in the image.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose run --rm --build --no-deps --entrypoint sh api -c \
    'python --version && pip list | grep -Ei "aioslsk|clickhouse-connect|fastapi|uvicorn"'
