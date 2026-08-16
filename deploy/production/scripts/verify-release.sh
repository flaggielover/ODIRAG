#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-common.sh
source "$SCRIPT_DIR/release-common.sh"

providers=false
target=""
for argument in "$@"; do
  case "$argument" in
    --providers) providers=true ;;
    --*) release_die "unknown option" ;;
    *) [[ -z "$target" ]] || release_die "only one release directory may be supplied"; target="$argument" ;;
  esac
done

release_preflight
acquire_release_lock
[[ ! -e "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" ]] \
  || release_die "unfinished release transaction must be recovered before verification"
current="$(resolve_optional_release_link "$ODIRAG_CURRENT_LINK")"
[[ -n "$current" ]] || release_die "no current release is available"
target="${target:-$current}"
target="$(resolve_release_dir "$target")"
[[ "$target" == "$current" ]] || release_die "verification target is not the current release"
load_release_manifest "$target"
verify_loaded_release "$providers"
[[ "$(resolve_optional_release_link "$ODIRAG_CURRENT_LINK")" == "$target" ]] || release_die "current release changed during verification"
validate_running_release_images
validate_release_state

release_log "release_verification=PASS-LIVE id=$RELEASE_ID current=true running_digests=true deployment_state=true data_integrity=true providers=$providers"
