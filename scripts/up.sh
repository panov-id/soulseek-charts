#!/usr/bin/env bash
# Build images and start the whole stack in the background.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -f .env ]]; then
    echo "No .env file found. Copy .env.example to .env and fill in the credentials." >&2
    exit 1
fi

docker compose up --build --detach
docker compose ps
