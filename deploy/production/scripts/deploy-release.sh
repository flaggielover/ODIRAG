#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-common.sh
source "$SCRIPT_DIR/release-common.sh"

usage() {
  printf 'usage: %s {recovery-only | RELEASE_DIRECTORY [deploy|rollback]}\n' "$0" >&2
  exit 64
}

requested=""
operation=""
if [[ "$#" -eq 1 && "$1" == "recovery-only" ]]; then
  operation="recovery-only"
elif [[ "$#" -ge 1 && "$#" -le 2 ]]; then
  requested="$1"
  operation="${2:-deploy}"
  [[ "$operation" == "deploy" || "$operation" == "rollback" ]] || usage
else
  usage
fi

pending_state=""
recovery_mode=""
LEGACY_RECOVERY_AVAILABLE=false
transaction_started=false
transaction_committed=false
candidate_state_committed=false
recovery_in_progress=false
target=""
old=""
old_previous=""
candidate_release_id=""
started=""

assert_loaded_journal_image_identity() {
  [[ "$RELEASE_BACKEND_REF" == "$JOURNAL_BACKEND_REF" \
      && "$RELEASE_FRONTEND_REF" == "$JOURNAL_FRONTEND_REF" \
      && "$RELEASE_BACKEND_IMAGE_ID" == "$JOURNAL_BACKEND_IMAGE_ID" \
      && "$RELEASE_FRONTEND_IMAGE_ID" == "$JOURNAL_FRONTEND_IMAGE_ID" ]] \
    || { release_die "recovery image identity changed after transaction preparation"; return 1; }
}

restore_original_from_loaded_journal() {
  if [[ "$JOURNAL_MODE" == "release" ]]; then
    load_release_manifest "$JOURNAL_ORIGINAL_CURRENT" || return 1
    validate_loaded_recovery_descriptor || return 1
    assert_loaded_journal_image_identity || return 1
    activate_loaded_release false || return 1
    verify_loaded_release false || return 1
  else
    load_release_manifest "$JOURNAL_TARGET_DIR" || return 1
    LEGACY_RELEASE_DIR="$JOURNAL_ORIGINAL_CURRENT"
    LEGACY_RELEASE_ID="$(basename -- "$JOURNAL_ORIGINAL_CURRENT")"
    LEGACY_COMPOSE="$JOURNAL_LEGACY_COMPOSE"
    LEGACY_NGINX="$JOURNAL_LEGACY_NGINX"
    LEGACY_COMPOSE_SHA="$JOURNAL_LEGACY_COMPOSE_SHA"
    LEGACY_NGINX_SHA="$JOURNAL_LEGACY_NGINX_SHA"
    LEGACY_BACKEND_REF="$JOURNAL_BACKEND_REF"
    LEGACY_FRONTEND_REF="$JOURNAL_FRONTEND_REF"
    LEGACY_BACKEND_IMAGE_ID="$JOURNAL_BACKEND_IMAGE_ID"
    LEGACY_FRONTEND_IMAGE_ID="$JOURNAL_FRONTEND_IMAGE_ID"
    LEGACY_ALEMBIC_HEAD="$JOURNAL_LEGACY_ALEMBIC_HEAD"
    LEGACY_RECOVERY_AVAILABLE=true
    activate_legacy_recovery || return 1
  fi
  restore_candidate_state_from_journal || return 1
  restore_release_links "$JOURNAL_ORIGINAL_CURRENT" "$JOURNAL_ORIGINAL_PREVIOUS" \
    || return 1
  [[ "$(resolve_optional_release_link "$ODIRAG_CURRENT_LINK")" == "$JOURNAL_ORIGINAL_CURRENT" ]] \
    || { release_die "automatic recovery current pointer mismatch"; return 1; }
  release_log "automatic recovery succeeded mode=$JOURNAL_MODE original_current=$(basename -- "$JOURNAL_ORIGINAL_CURRENT") data_integrity=true"
}

recover_unfinished_transaction() {
  [[ -e "$ODIRAG_RELEASE_JOURNAL" || -L "$ODIRAG_RELEASE_JOURNAL" ]] || return 0
  release_log "unfinished release transaction detected; restoring its recorded original release"
  load_release_journal || return 1
  restore_original_from_loaded_journal || return 1
  clear_release_journal || return 1
  release_log "unfinished_release_recovery=PASS-LIVE"
}

run_recovery_only() {
  if [[ ! -e "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" ]]; then
    release_log "release_recovery_only=PASS-CONFIG recovered=false reason=no-journal"
    return 0
  fi
  recover_unfinished_transaction || return 1
  release_log "release_recovery_only=PASS-LIVE recovered=true"
}

prepare_recovery_path() {
  [[ -n "$old" ]] \
    || { release_die "deployment requires a current release that can be recovered"; return 1; }
  if [[ "$operation" == "rollback" ]]; then
    [[ -n "$old_previous" && "$target" == "$old_previous" ]] \
      || { release_die "rollback target must be the locked previous release"; return 1; }
    [[ -f "$old/manifest.env" ]] \
      || { release_die "rollback requires a manifest-backed current release"; return 1; }
    load_release_manifest "$old" || return 1
    validate_loaded_recovery_descriptor \
      || { release_die "current release recovery descriptor is invalid"; return 1; }
    recovery_mode=release
  elif [[ -f "$old/manifest.env" ]]; then
    load_release_manifest "$old" || return 1
    verify_loaded_release true \
      || { release_die "current release is not a verified rollback target"; return 1; }
    recovery_mode=release
  else
    capture_legacy_recovery_state "$old" || return 1
    recovery_mode=legacy-bootstrap
  fi
  if [[ "$recovery_mode" == "release" ]]; then
    recovery_backend_ref="$RELEASE_BACKEND_REF"
    recovery_frontend_ref="$RELEASE_FRONTEND_REF"
    recovery_backend_image_id="$RELEASE_BACKEND_IMAGE_ID"
    recovery_frontend_image_id="$RELEASE_FRONTEND_IMAGE_ID"
  else
    recovery_backend_ref="$LEGACY_BACKEND_REF"
    recovery_frontend_ref="$LEGACY_FRONTEND_REF"
    recovery_backend_image_id="$LEGACY_BACKEND_IMAGE_ID"
    recovery_frontend_image_id="$LEGACY_FRONTEND_IMAGE_ID"
  fi
  load_release_manifest "$target" || return 1
  run_release_integrity_check \
    || { release_die "pre-deployment production data baseline failed"; return 1; }
  release_log "recovery_preflight=PASS-CONFIG mode=$recovery_mode original_current=$(basename -- "$old") data_integrity=true"
}

prepare_transaction_journal() {
  local previous_token legacy_compose legacy_nginx legacy_compose_sha legacy_nginx_sha
  local legacy_alembic_head state state_existed state_backup state_sha
  previous_token="${old_previous:-NONE}"
  legacy_compose="-"
  legacy_nginx="-"
  legacy_compose_sha="-"
  legacy_nginx_sha="-"
  legacy_alembic_head="-"
  if [[ "$recovery_mode" == "legacy-bootstrap" ]]; then
    legacy_compose="$LEGACY_COMPOSE"
    legacy_nginx="$LEGACY_NGINX"
    legacy_compose_sha="$LEGACY_COMPOSE_SHA"
    legacy_nginx_sha="$LEGACY_NGINX_SHA"
    legacy_alembic_head="$LEGACY_ALEMBIC_HEAD"
  fi
  clear_orphan_candidate_state_backup "$target" || return 1
  state="$target/deployment-state.json"
  state_existed=false
  state_backup=NONE
  state_sha=NONE
  if [[ -e "$state" || -L "$state" ]]; then
    validate_file_permissions "$state" || return 1
    state_existed=true
    state_backup="$target/.deployment-state.json.pretransaction"
    state_sha="$(sha256sum "$state" | awk '{print $1}')" || return 1
  fi
  write_release_journal "$recovery_mode" "$target" "$old" "$previous_token" \
    "$recovery_backend_ref" "$recovery_frontend_ref" "$recovery_backend_image_id" \
    "$recovery_frontend_image_id" "$legacy_compose" "$legacy_nginx" \
    "$legacy_compose_sha" "$legacy_nginx_sha" "$legacy_alembic_head" \
    "$state_existed" "$state_backup" "$state_sha" || return 1
  load_release_journal || return 1
  transaction_started=true
  prepare_candidate_state_backup "$target" || return 1
}

activate_and_commit_candidate() {
  local finished duration
  chmod 0444 "$target/manifest.env" || { release_die "candidate manifest protection failed"; return 1; }
  activate_loaded_release true || { release_die "candidate activation failed"; return 1; }
  verify_loaded_release true || { release_die "candidate integrity/provider validation failed"; return 1; }
  finished="$(date +%s%3N)" || { release_die "candidate duration timestamp failed"; return 1; }
  duration="$(awk -v start="$started" -v finish="$finished" 'BEGIN { printf "%.3f", (finish-start)/1000 }')" \
    || { release_die "candidate duration calculation failed"; return 1; }
  pending_state="$target/.deployment-state.json.pending.$$"
  prepare_release_state "$target" "$old" "$operation" "$duration" >/dev/null \
    || { release_die "candidate state preparation failed"; return 1; }
  promote_release_links "$target" "$old" \
    || { release_die "candidate pointer promotion failed"; return 1; }
  commit_release_state "$target" "$pending_state" \
    || { release_die "candidate state commit failed"; return 1; }
  pending_state=""
  candidate_state_committed=true
  clear_release_journal || { release_die "release journal commit failed"; return 1; }
  transaction_committed=true
  transaction_started=false
  discard_candidate_state_backup \
    || release_log "WARNING: committed release retained an orphan state backup"
  release_log "release=PASS-LIVE id=$candidate_release_id operation=$operation duration_seconds=$duration providers=true data_integrity=true"
}

release_exit_handler() {
  local status=$? recovery_status=0
  trap - EXIT HUP INT TERM
  if [[ "$transaction_started" == "true" && "$transaction_committed" != "true" ]]; then
    if [[ ! -e "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" \
        && "$candidate_state_committed" == "true" ]]; then
      transaction_committed=true
    elif [[ "$recovery_in_progress" != "true" ]]; then
      recovery_in_progress=true
      set +e
      release_log "candidate transaction interrupted; attempting automatic recovery"
      load_release_journal
      recovery_status=$?
      if (( recovery_status == 0 )); then
        restore_original_from_loaded_journal
        recovery_status=$?
      fi
      discard_release_state "$target" "$pending_state"
      if (( recovery_status == 0 )); then
        clear_release_journal
        recovery_status=$?
      fi
      if (( recovery_status != 0 )); then
        release_log "ERROR: candidate failed and automatic recovery did not complete; journal retained"
        status=1
      fi
      set -e
    fi
  fi
  exit "$status"
}

trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
trap release_exit_handler EXIT

release_preflight
acquire_release_lock
if [[ "$operation" == "recovery-only" ]]; then
  run_recovery_only
  exit 0
fi
recover_unfinished_transaction
target="$(resolve_release_dir "$requested")"
old="$(resolve_optional_release_link "$ODIRAG_CURRENT_LINK")"
old_previous="$(resolve_optional_release_link "$ODIRAG_PREVIOUS_LINK")"
[[ "$target" != "$old" ]] || release_die "target release is already current"
started="$(date +%s%3N)"
load_release_manifest "$target"
candidate_release_id="$RELEASE_ID"
prepare_recovery_path
prepare_transaction_journal
release_log "activating release=$candidate_release_id operation=$operation providers=true data_integrity=true"
if ! activate_and_commit_candidate; then
  release_log "candidate transaction failed release=$candidate_release_id"
  exit 1
fi
