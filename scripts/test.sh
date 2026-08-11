#!/usr/bin/env bash
# Run the test suite inside a throwaway container.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

# --build is required: without it a changed pyproject.toml is ignored and the
# run silently uses a stale image.
docker compose run --rm --build --no-deps --entrypoint sh \
    --volume "$project_root/source:/application/source:ro" \
    --volume "$project_root/tests:/application/tests:ro" \
    --env PYTEST_ADDOPTS="-p no:cacheprovider" \
    api -c 'pytest "$@"' -- "$@"
