#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-common.sh
source "$SCRIPT_DIR/release-common.sh"

target="${1:-$ODIRAG_PREVIOUS_LINK}"
exec "$SCRIPT_DIR/deploy-release.sh" "$target" rollback
