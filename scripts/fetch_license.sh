#!/usr/bin/env bash
# Download the verbatim GPL-3.0 text into LICENSE.
# The licence text must be byte-exact, so it is fetched from gnu.org rather
# than reproduced by hand.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

curl --fail --silent --show-error --location \
    https://www.gnu.org/licenses/gpl-3.0.txt \
    --output LICENSE

echo "LICENSE written: $(wc -l < LICENSE) lines"
