#!/usr/bin/env bash
# Compile-only check: builds the Docker image without connecting anywhere.
# Catches Go compilation errors before the first live run.
set -euo pipefail

directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build -t soulseek-step0 "$directory"

echo
echo "build ok"
