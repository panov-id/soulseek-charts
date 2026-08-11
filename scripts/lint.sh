#!/usr/bin/env bash
# Run the linter and the type checker inside a throwaway container.
# The working tree is mounted so the checks see current files, not the image copy.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

docker compose run --rm --build --no-deps --entrypoint sh \
    --volume "$project_root/source:/application/source:ro" \
    --volume "$project_root/tests:/application/tests:ro" \
    --env RUFF_CACHE_DIR=/tmp/ruff_cache \
    --env MYPY_CACHE_DIR=/tmp/mypy_cache \
    api -c '
    set -e
    ruff check source tests
    ruff format --check source tests
    mypy source
'
