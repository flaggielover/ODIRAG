#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-common.sh
source "$SCRIPT_DIR/release-common.sh"

release_preflight
target="${1:-}"
if [[ -z "$target" ]]; then
  target="$(realpath -e -- "$ODIRAG_PREVIOUS_LINK" 2>/dev/null || true)"
fi
[[ -n "$target" ]] || release_die "no previous release is available"
target="$(resolve_release_dir "$target")"
current="$(realpath -e -- "$ODIRAG_CURRENT_LINK" 2>/dev/null || true)"
[[ "$target" != "$current" ]] || release_die "rollback target is already current"
[[ -f "$target/manifest.env" ]] || release_die "rollback target has no immutable manifest"

exec "$SCRIPT_DIR/deploy-release.sh" "$target" rollback
