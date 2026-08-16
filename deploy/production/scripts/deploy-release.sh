#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-common.sh
source "$SCRIPT_DIR/release-common.sh"

usage() {
  printf 'usage: %s RELEASE_DIRECTORY [deploy|rollback]\n' "$0" >&2
  exit 64
}

[[ "$#" -ge 1 && "$#" -le 2 ]] || usage
requested="$1"
operation="${2:-deploy}"
[[ "$operation" == "deploy" || "$operation" == "rollback" ]] || usage

release_preflight
acquire_release_lock
target="$(resolve_release_dir "$requested")"
old="$(realpath -e -- "$ODIRAG_CURRENT_LINK" 2>/dev/null || true)"
started="$(date +%s%3N)"

load_release_manifest "$target"
release_log "activating release=$RELEASE_ID operation=$operation"
if ! activate_loaded_release; then
  release_log "target activation failed"
  if [[ -n "$old" && "$old" != "$target" && -f "$old/manifest.env" ]]; then
    release_log "attempting automatic recovery to previous known-good release"
    load_release_manifest "$old"
    activate_loaded_release || release_die "target failed and automatic recovery failed"
    wait_release_stack 360 || release_die "automatic recovery did not restore health"
    release_log "automatic recovery succeeded"
  fi
  exit 1
fi

finished="$(date +%s%3N)"
duration="$(awk -v start="$started" -v finish="$finished" 'BEGIN { printf "%.3f", (finish-start)/1000 }')"
write_release_state "$target" "$old" "$operation" "$duration"
promote_release_links "$target" "$old"
chmod 0444 "$target/manifest.env" "$target/deployment-state.json"
release_log "release=PASS-LIVE id=$RELEASE_ID operation=$operation duration_seconds=$duration"
