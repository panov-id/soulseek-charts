#!/usr/bin/env bash
# Build and run the Soulseek search-stream probe inside Docker.
# Nothing is installed on the host.
#
#   SOULSEEK_USERNAME=... SOULSEEK_PASSWORD=... bash run.sh 5m
set -euo pipefail

directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image="soulseek-step0"
duration="${1:-5m}"

# Credentials may live in a local .env file instead of the environment.
# That file is gitignored and never leaves this machine.
if [ -f "$directory/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$directory/.env"
    set +a
fi

if [ -z "${SOULSEEK_USERNAME:-}" ] || [ -z "${SOULSEEK_PASSWORD:-}" ]; then
    echo "SOULSEEK_USERNAME and SOULSEEK_PASSWORD must be set" >&2
    echo "either export them, or create $directory/.env from .env.example" >&2
    exit 1
fi

# Soulseek allows one session per account: logging in here would disconnect
# a running client using the same username.
if pgrep -f "nicotine" >/dev/null 2>&1; then
    echo "WARNING: Nicotine+ appears to be running." >&2
    echo "Logging in with the same account will disconnect it." >&2
    echo >&2
fi

results_directory="$directory/results"
mkdir -p "$results_directory"

docker build -t "$image" "$directory"

docker run --rm -i \
    -e SOULSEEK_USERNAME \
    -e SOULSEEK_PASSWORD \
    -v "$results_directory:/data" \
    --user "$(id -u):$(id -g)" \
    "$image" -duration "$duration" ${VERBOSE:+-verbose} \
    ${CLIENT_MAJOR:+-major "$CLIENT_MAJOR"} ${CLIENT_MINOR:+-minor "$CLIENT_MINOR"} \
    ${PARENTS:+-parents "$PARENTS"} ${OUTPUT_NAME:+-output "/data/$OUTPUT_NAME"}

echo
echo "captured queries: $results_directory/${OUTPUT_NAME:-searches.jsonl}"
wc -l "$results_directory/${OUTPUT_NAME:-searches.jsonl}"
