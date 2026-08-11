#!/usr/bin/env bash
# Apply the formatter to the working tree. Mounted read-write on purpose:
# this is the one script that is allowed to change source files.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose run --rm --build --no-deps --entrypoint sh \
    --volume "$project_root/source:/application/source" \
    --volume "$project_root/tests:/application/tests" \
    --env RUFF_CACHE_DIR=/tmp/ruff_cache \
    --user "$(id -u):$(id -g)" \
    api -c 'ruff format source tests && ruff check --fix source tests'
