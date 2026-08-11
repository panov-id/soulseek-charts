#!/usr/bin/env bash
# Screenshot the running dashboard in light and dark, desktop and mobile.
# Playwright runs inside a container built on the official image; nothing is
# installed on the host. Start the dashboard first with scripts/demo_up.sh.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

base_url="${1:-http://127.0.0.1:8000}"
output_directory="$project_root/screenshots"
image_tag="soulseek-charts-screenshot"

mkdir -p "$output_directory"

docker build --tag "$image_tag" infrastructure/screenshot

# Host networking so the container reaches the port published on 127.0.0.1.
docker run --rm --network host \
    --volume "$output_directory:/output" \
    --user "$(id -u):$(id -g)" \
    "$image_tag" "$base_url"

echo "Screenshots in $output_directory"
