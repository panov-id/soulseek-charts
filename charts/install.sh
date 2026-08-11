#!/usr/bin/env bash
# Build soulseek-charts inside Docker and copy the finished binary to
# ~/.local/bin. Nothing is compiled or installed on the host itself — only the
# resulting statically linked file is copied out of the image.
set -euo pipefail

directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_directory="${1:-$HOME/.local/bin}"
binary_name="soulseek-charts"
image_name="soulseek-charts-build"

collector_archive="$(cd "$directory/../collector" && pwd)/data/raw"

docker build -t "$image_name" "$directory"

mkdir -p "$target_directory"

# `docker create` on a scratch image gives us a container to copy the file out
# of without ever running it.
container_id="$(docker create "$image_name")"
docker cp "$container_id:/$binary_name" "$target_directory/$binary_name"
docker rm "$container_id" >/dev/null

chmod +x "$target_directory/$binary_name"

echo "installed $target_directory/$binary_name"
echo

if ! printf '%s' ":$PATH:" | grep -q ":$target_directory:"; then
    echo "NOTE: $target_directory is not in PATH. Add to your shell profile:"
    echo "    export PATH=\"\$PATH:$target_directory\""
    echo
fi

echo "Point the tool at the archive by adding this to your shell profile:"
echo "    export SOULSEEK_ARCHIVE=\"$collector_archive\""
echo
echo "Then run:"
echo "    $binary_name -top 20"
echo "    $binary_name -since 24h -section formats"
echo "    $binary_name -json > charts.json"
