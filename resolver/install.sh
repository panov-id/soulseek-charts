#!/usr/bin/env bash
# Build soulseek-resolve inside Docker and copy the binary to ~/.local/bin.
set -euo pipefail

directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_directory="${1:-$HOME/.local/bin}"
binary_name="soulseek-resolve"
image_name="soulseek-resolve-build"

docker build -t "$image_name" "$directory"

mkdir -p "$target_directory"
container_id="$(docker create "$image_name")"
docker cp "$container_id:/usr/local/bin/$binary_name" "$target_directory/$binary_name"
docker rm "$container_id" >/dev/null
chmod +x "$target_directory/$binary_name"

echo "installed $target_directory/$binary_name"
echo
echo "MusicBrainz requires a contact in the User-Agent. Add to your profile:"
echo "    export SOULSEEK_CONTACT=\"you@example.com\""
