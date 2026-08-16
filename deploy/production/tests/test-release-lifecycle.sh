#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
TEST_ROOT="$(mktemp -d /tmp/odirag-release-test.XXXXXX)"
MOCK_BIN="$TEST_ROOT/bin"
MOCK_STATE_DIR="$TEST_ROOT/state"
RELEASE_ROOT="$TEST_ROOT/releases"
CURRENT_LINK="$TEST_ROOT/current"
PREVIOUS_LINK="$TEST_ROOT/previous"
RUNTIME_ENV="$TEST_ROOT/production.env"
LOCK_FILE="$TEST_ROOT/release.lock"
JOURNAL_FILE="$TEST_ROOT/.release-transaction.env"

cleanup() {
  if [[ "${KEEP_TEST_ROOT:-0}" == "1" ]]; then
    printf 'test_root=%s\n' "$TEST_ROOT" >&2
    return
  fi
  case "$TEST_ROOT" in
    /tmp/odirag-release-test.*) rm -rf -- "$TEST_ROOT" ;;
  esac
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  if [[ "${DEBUG_TEST_LOGS:-0}" == "1" ]]; then
    for log in "$TEST_ROOT"/*.log; do
      [[ -f "$log" ]] || continue
      printf '%s\n' "--- $log ---" >&2
      sed -n '1,240p' "$log" >&2
    done
  fi
  exit 1
}

assert_equal() {
  local expected="$1" actual="$2" message="$3"
  [[ "$actual" == "$expected" ]] || fail "$message expected=$expected actual=$actual"
}

assert_absent() {
  [[ ! -e "$1" && ! -L "$1" ]] || fail "path should be absent: $1"
}

mkdir -p "$MOCK_BIN" "$MOCK_STATE_DIR" "$RELEASE_ROOT"
printf 'COMPOSE_PROJECT_NAME=odirag-prod\n' >"$RUNTIME_ENV"
chmod 0600 "$RUNTIME_ENV"

export MOCK_STATE_DIR
export MOCK_ALEMBIC_HEAD=0012_attachment_processing_audit
export MOCK_BUILD_CREATED=2026-08-16T00:00:00Z
export MOCK_OLD_ID=v0.1.0-r0
export MOCK_TARGET_ID=v0.1.0-r1
export MOCK_OLD_COMMIT="$(printf '1%.0s' {1..40})"
export MOCK_TARGET_COMMIT="$(printf '2%.0s' {1..40})"
export MOCK_OLD_BACKEND_REF="ghcr.io/test/odirag-backend@sha256:$(printf 'a%.0s' {1..64})"
export MOCK_OLD_FRONTEND_REF="ghcr.io/test/odirag-frontend@sha256:$(printf 'b%.0s' {1..64})"
export MOCK_LEGACY_BACKEND_REF="odirag/backend@sha256:$(printf 'a%.0s' {1..64})"
export MOCK_LEGACY_FRONTEND_REF="odirag/frontend@sha256:$(printf 'b%.0s' {1..64})"
export MOCK_TARGET_BACKEND_REF="ghcr.io/test/odirag-backend@sha256:$(printf 'c%.0s' {1..64})"
export MOCK_TARGET_FRONTEND_REF="ghcr.io/test/odirag-frontend@sha256:$(printf 'd%.0s' {1..64})"
export MOCK_OLD_BACKEND_IMAGE_ID="sha256:$(printf 'e%.0s' {1..64})"
export MOCK_OLD_FRONTEND_IMAGE_ID="sha256:$(printf 'f%.0s' {1..64})"
export MOCK_TARGET_BACKEND_IMAGE_ID="sha256:$(printf '1%.0s' {1..64})"
export MOCK_TARGET_FRONTEND_IMAGE_ID="sha256:$(printf '2%.0s' {1..64})"
export MOCK_CURRENT_LINK="$CURRENT_LINK"

cat >"$MOCK_BIN/id" <<'SH'
#!/usr/bin/env bash
[[ "${1:-}" == "-u" ]] && { printf '0\n'; exit 0; }
exec /usr/bin/id "$@"
SH

cat >"$MOCK_BIN/flock" <<'SH'
#!/usr/bin/env bash
[[ "${MOCK_FLOCK_FAIL:-0}" == "1" ]] && exit 1
exit 0
SH

cat >"$MOCK_BIN/curl" <<'SH'
#!/usr/bin/env bash
printf '%s' "${MOCK_HTTP_STATUS:-200}"
exit 0
SH

cat >"$MOCK_BIN/sleep" <<'SH'
#!/usr/bin/env bash
exit 0
SH

cat >"$MOCK_BIN/python3" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "-" ]]; then
  cat >/dev/null
  if [[ "$#" == "14" ]]; then
    state="$2"
    [[ "${MOCK_STATE_WRITE_FAIL:-0}" == "1" ]] && exit 1
    printf '{"schema_version":2,"release_id":"%s","source_commit":"%s","backend_image_ref":"%s","frontend_image_ref":"%s","backend_image_id":"%s","frontend_image_id":"%s","alembic_head":"%s","compose_sha256":"%s","build_created":"%s","previous_release":"%s","operation":"%s","duration_seconds":%s,"data_integrity_verified":true,"providers_verified":true,"verified_at":"2026-08-16T00:00:00+00:00"}\n' \
      "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}" "${13}" "${14}" >"$state"
    chmod 0444 "$state"
  elif [[ "$#" == "11" ]]; then
    [[ "${MOCK_STATE_VALIDATE_FAIL:-0}" != "1" ]] || exit 1
  else
    exit 1
  fi
  exit 0
fi
exec python "$@"
SH

cat >"$MOCK_BIN/mv" <<'SH'
#!/usr/bin/env bash
destination="${@: -1}"
if [[ -n "${MOCK_FAIL_CURRENT_PROMOTION_ONCE_FILE:-}" \
      && "$destination" == "$MOCK_CURRENT_LINK" \
      && ! -e "$MOCK_FAIL_CURRENT_PROMOTION_ONCE_FILE" ]]; then
  : >"$MOCK_FAIL_CURRENT_PROMOTION_ONCE_FILE"
  exit 1
fi
exec /usr/bin/mv "$@"
SH

cat >"$MOCK_BIN/cp" <<'SH'
#!/usr/bin/env bash
destination="${@: -1}"
if [[ "${MOCK_PARTIAL_BACKUP_FAIL:-0}" == "1" \
      && "$destination" == *.deployment-state.json.pretransaction.tmp ]]; then
  source="${@: -2:1}"
  head -c 1 -- "$source" >"$destination"
  exit 1
fi
exec /usr/bin/cp "$@"
SH

cat >"$MOCK_BIN/docker" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail

image_id() {
  case "$1" in
    "$MOCK_OLD_BACKEND_REF"|"$MOCK_LEGACY_BACKEND_REF") printf '%s\n' "$MOCK_OLD_BACKEND_IMAGE_ID" ;;
    "$MOCK_OLD_FRONTEND_REF"|"$MOCK_LEGACY_FRONTEND_REF") printf '%s\n' "$MOCK_OLD_FRONTEND_IMAGE_ID" ;;
    "$MOCK_TARGET_BACKEND_REF") printf '%s\n' "$MOCK_TARGET_BACKEND_IMAGE_ID" ;;
    "$MOCK_TARGET_FRONTEND_REF") printf '%s\n' "$MOCK_TARGET_FRONTEND_IMAGE_ID" ;;
    *) exit 1 ;;
  esac
}

repo_digest() {
  case "$1" in
    "$MOCK_OLD_BACKEND_IMAGE_ID"|"$MOCK_OLD_BACKEND_REF"|"$MOCK_LEGACY_BACKEND_REF")
      printf '%s\n%s\n' "$MOCK_OLD_BACKEND_REF" "$MOCK_LEGACY_BACKEND_REF"
      ;;
    "$MOCK_OLD_FRONTEND_IMAGE_ID"|"$MOCK_OLD_FRONTEND_REF"|"$MOCK_LEGACY_FRONTEND_REF")
      printf '%s\n%s\n' "$MOCK_OLD_FRONTEND_REF" "$MOCK_LEGACY_FRONTEND_REF"
      ;;
    "$MOCK_TARGET_BACKEND_IMAGE_ID"|"$MOCK_TARGET_BACKEND_REF") printf '%s\n' "$MOCK_TARGET_BACKEND_REF" ;;
    "$MOCK_TARGET_FRONTEND_IMAGE_ID"|"$MOCK_TARGET_FRONTEND_REF") printf '%s\n' "$MOCK_TARGET_FRONTEND_REF" ;;
    *) exit 1 ;;
  esac
}

release_id() {
  case "$1" in
    "$MOCK_OLD_BACKEND_REF"|"$MOCK_OLD_FRONTEND_REF"|"$MOCK_LEGACY_BACKEND_REF"|"$MOCK_LEGACY_FRONTEND_REF")
      printf '%s\n' "$MOCK_OLD_ID"
      ;;
    "$MOCK_TARGET_BACKEND_REF"|"$MOCK_TARGET_FRONTEND_REF") printf '%s\n' "$MOCK_TARGET_ID" ;;
    *) exit 1 ;;
  esac
}

revision() {
  case "$1" in
    "$MOCK_OLD_BACKEND_REF"|"$MOCK_OLD_FRONTEND_REF") printf '%s\n' "$MOCK_OLD_COMMIT" ;;
    "$MOCK_TARGET_BACKEND_REF"|"$MOCK_TARGET_FRONTEND_REF") printf '%s\n' "$MOCK_TARGET_COMMIT" ;;
    *) exit 1 ;;
  esac
}

active_ref() {
  case "$1" in
    backend|worker|scheduler) cat "$MOCK_STATE_DIR/backend-ref" ;;
    frontend) cat "$MOCK_STATE_DIR/frontend-ref" ;;
    *) exit 1 ;;
  esac
}

if [[ "${1:-}" == "compose" ]]; then
  [[ "${2:-}" == "version" ]] && exit 0
  compose_file=""
  for ((index=1; index <= $#; index++)); do
    if [[ "${!index}" == "-f" ]]; then
      next=$((index + 1))
      compose_file="${!next}"
    fi
  done
  if [[ " $* " == *" up "* ]]; then
    [[ " $* " == *" backend "* ]] && printf '%s\n' "$ODIRAG_BACKEND_IMAGE_REF" >"$MOCK_STATE_DIR/backend-ref"
    [[ " $* " == *" frontend "* ]] && printf '%s\n' "$ODIRAG_FRONTEND_IMAGE_REF" >"$MOCK_STATE_DIR/frontend-ref"
    if [[ " $* " == *" nginx "* ]]; then
      printf '%s\n' "$(dirname -- "$compose_file")/nginx.conf" >"$MOCK_STATE_DIR/nginx-source"
    fi
  fi
  exit 0
fi

case "${1:-}" in
  pull)
    [[ "${MOCK_PULL_FAIL_REF:-}" == "${2:-}" ]] && exit 1
    exit 0
    ;;
  cp) exit 0 ;;
  image)
    format="$4"
    ref="$5"
    case "$format" in
      '{{.Id}}') image_id "$ref" ;;
      *revision*) revision "$ref" ;;
      *version*) release_id "$ref" ;;
      *created*) printf '%s\n' "$MOCK_BUILD_CREATED" ;;
      *RepoDigests*) repo_digest "$ref" ;;
      *) exit 1 ;;
    esac
    ;;
  run)
    printf '%s (head)\n' "$MOCK_ALEMBIC_HEAD"
    if [[ "${MOCK_MULTIPLE_HEADS:-0}" == "1" ]]; then
      printf '9999_second_head (head)\n'
    fi
    exit 0
    ;;
  ps)
    service=""
    for argument in "$@"; do
      case "$argument" in
        label=com.docker.compose.service=*) service="${argument##*=}" ;;
      esac
    done
    [[ -n "$service" ]] && printf '%s-cid\n' "$service"
    ;;
  inspect)
    format="$3"
    container="$4"
    service="${container%-cid}"
    case "$format" in
      *State.Health*)
        active_release="$(release_id "$(cat "$MOCK_STATE_DIR/backend-ref")")"
        if [[ "${MOCK_HEALTH_FAIL_RELEASE:-}" == "$active_release" ]]; then
          printf 'unhealthy\n'
        else
          printf 'healthy\n'
        fi
        ;;
      '{{.Image}}') image_id "$(active_ref "$service")" ;;
      '{{.Config.Image}}') active_ref "$service" ;;
      *Mounts*) cat "$MOCK_STATE_DIR/nginx-source" ;;
      *) exit 1 ;;
    esac
    ;;
  exec)
    shift
    if [[ "${1:-}" == "--user" ]]; then
      shift 2
      exit 0
    fi
    container="$1"
    shift
    if [[ "$container" == "postgres-cid" ]]; then
      printf '%s\n' "$MOCK_ALEMBIC_HEAD"
      exit 0
    fi
    if [[ " $* " == *production-integrity-* ]]; then
      active="$(release_id "$(cat "$MOCK_STATE_DIR/backend-ref")")"
      [[ "${MOCK_INTEGRITY_FAIL_RELEASE:-}" == "$active" ]] && exit 1
      [[ "${MOCK_MARKERLESS_INTEGRITY_RELEASE:-}" == "$active" ]] && exit 0
      printf 'production_data_integrity=PASS-LIVE test=true\n'
      exit 0
    fi
    if [[ " $* " == *production-providers-* ]]; then
      active="$(release_id "$(cat "$MOCK_STATE_DIR/backend-ref")")"
      if [[ "${MOCK_SIGNAL_PROVIDER_RELEASE:-}" == "$active" ]]; then
        kill -TERM "$PPID"
        exit 143
      fi
      [[ "${MOCK_PROVIDER_FAIL_RELEASE:-}" == "$active" ]] && exit 1
      printf 'production_grounded_rag=PASS-LIVE test=true\n'
      printf 'production_out_of_scope_refusal=PASS-LIVE test=true\n'
      exit 0
    fi
    exit 0
    ;;
  *) exit 1 ;;
esac
SH

chmod 0755 "$MOCK_BIN"/*
export PATH="$MOCK_BIN:$PATH"

make_release() {
  local release_id="$1" commit="$2" backend_ref="$3" frontend_ref="$4" nginx_text="$5"
  local directory="$RELEASE_ROOT/$release_id"
  mkdir -p "$directory/deploy/production/scripts"
  printf 'services: {}\n' >"$directory/deploy/production/compose.yml"
  printf '%s\n' "$nginx_text" >"$directory/deploy/production/nginx.conf"
  printf 'print("integrity")\n' >"$directory/deploy/production/scripts/verify-production-integrity.py"
  printf 'print("providers")\n' >"$directory/deploy/production/scripts/verify-production-rag.py"
  local compose_sha nginx_sha integrity_sha provider_sha
  compose_sha="$(sha256sum "$directory/deploy/production/compose.yml" | awk '{print $1}')"
  nginx_sha="$(sha256sum "$directory/deploy/production/nginx.conf" | awk '{print $1}')"
  integrity_sha="$(sha256sum "$directory/deploy/production/scripts/verify-production-integrity.py" | awk '{print $1}')"
  provider_sha="$(sha256sum "$directory/deploy/production/scripts/verify-production-rag.py" | awk '{print $1}')"
  cat >"$directory/manifest.env" <<EOF
ODIRAG_RELEASE_ID=$release_id
ODIRAG_SOURCE_COMMIT=$commit
ODIRAG_BACKEND_IMAGE_REF=$backend_ref
ODIRAG_FRONTEND_IMAGE_REF=$frontend_ref
ODIRAG_ALEMBIC_HEAD=$MOCK_ALEMBIC_HEAD
ODIRAG_COMPOSE_SHA256=$compose_sha
ODIRAG_NGINX_SHA256=$nginx_sha
ODIRAG_INTEGRITY_CHECK_SHA256=$integrity_sha
ODIRAG_PROVIDER_CHECK_SHA256=$provider_sha
ODIRAG_BUILD_CREATED=$MOCK_BUILD_CREATED
EOF
  chmod 0644 "$directory/manifest.env" "$directory/deploy/production/compose.yml" \
    "$directory/deploy/production/nginx.conf" \
    "$directory/deploy/production/scripts/verify-production-integrity.py" \
    "$directory/deploy/production/scripts/verify-production-rag.py"
}

OLD_RELEASE="$RELEASE_ROOT/$MOCK_OLD_ID"
TARGET_RELEASE="$RELEASE_ROOT/$MOCK_TARGET_ID"
make_release "$MOCK_OLD_ID" "$MOCK_OLD_COMMIT" "$MOCK_OLD_BACKEND_REF" "$MOCK_OLD_FRONTEND_REF" "events { worker_connections 128; }"
make_release "$MOCK_TARGET_ID" "$MOCK_TARGET_COMMIT" "$MOCK_TARGET_BACKEND_REF" "$MOCK_TARGET_FRONTEND_REF" "events { worker_connections 256; }"

reset_old_state() {
  unlink "$CURRENT_LINK" 2>/dev/null || true
  unlink "$PREVIOUS_LINK" 2>/dev/null || true
  ln -s "$OLD_RELEASE" "$CURRENT_LINK"
  printf '%s\n' "$MOCK_OLD_BACKEND_REF" >"$MOCK_STATE_DIR/backend-ref"
  printf '%s\n' "$MOCK_OLD_FRONTEND_REF" >"$MOCK_STATE_DIR/frontend-ref"
  printf '%s\n' "$OLD_RELEASE/deploy/production/nginx.conf" >"$MOCK_STATE_DIR/nginx-source"
  rm -f -- "$TARGET_RELEASE/deployment-state.json" "$TARGET_RELEASE"/.deployment-state.json.pending.*
}

write_stale_release_journal() {
  cat >"$JOURNAL_FILE" <<EOF
ODIRAG_JOURNAL_VERSION=1
ODIRAG_JOURNAL_MODE=release
ODIRAG_JOURNAL_TARGET_DIR=$TARGET_RELEASE
ODIRAG_JOURNAL_ORIGINAL_CURRENT=$OLD_RELEASE
ODIRAG_JOURNAL_ORIGINAL_PREVIOUS=NONE
ODIRAG_JOURNAL_BACKEND_REF=$MOCK_OLD_BACKEND_REF
ODIRAG_JOURNAL_FRONTEND_REF=$MOCK_OLD_FRONTEND_REF
ODIRAG_JOURNAL_BACKEND_IMAGE_ID=$MOCK_OLD_BACKEND_IMAGE_ID
ODIRAG_JOURNAL_FRONTEND_IMAGE_ID=$MOCK_OLD_FRONTEND_IMAGE_ID
ODIRAG_JOURNAL_LEGACY_COMPOSE=-
ODIRAG_JOURNAL_LEGACY_NGINX=-
ODIRAG_JOURNAL_LEGACY_COMPOSE_SHA256=-
ODIRAG_JOURNAL_LEGACY_NGINX_SHA256=-
ODIRAG_JOURNAL_LEGACY_ALEMBIC_HEAD=-
ODIRAG_JOURNAL_TARGET_STATE_EXISTED=false
ODIRAG_JOURNAL_TARGET_STATE_BACKUP=NONE
ODIRAG_JOURNAL_TARGET_STATE_SHA256=NONE
EOF
  chmod 0600 "$JOURNAL_FILE"
}

run_deploy() {
  ODIRAG_RELEASE_ROOT="$RELEASE_ROOT" \
  ODIRAG_CURRENT_LINK="$CURRENT_LINK" \
  ODIRAG_PREVIOUS_LINK="$PREVIOUS_LINK" \
  ODIRAG_RUNTIME_ENV_FILE="$RUNTIME_ENV" \
  ODIRAG_RELEASE_LOCK="$LOCK_FILE" \
  ODIRAG_RELEASE_JOURNAL="$JOURNAL_FILE" \
    "$REPOSITORY_ROOT/deploy/production/scripts/deploy-release.sh" "$@"
}

run_verify() {
  ODIRAG_RELEASE_ROOT="$RELEASE_ROOT" \
  ODIRAG_CURRENT_LINK="$CURRENT_LINK" \
  ODIRAG_PREVIOUS_LINK="$PREVIOUS_LINK" \
  ODIRAG_RUNTIME_ENV_FILE="$RUNTIME_ENV" \
  ODIRAG_RELEASE_LOCK="$LOCK_FILE" \
  ODIRAG_RELEASE_JOURNAL="$JOURNAL_FILE" \
    "$REPOSITORY_ROOT/deploy/production/scripts/verify-release.sh" "$@"
}

reset_old_state
export MOCK_PROVIDER_FAIL_RELEASE="$MOCK_OLD_ID"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/current-preflight-failure.log" 2>&1; then
  fail "unverified current release unexpectedly allowed deployment"
fi
unset MOCK_PROVIDER_FAIL_RELEASE
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "current preflight failure changed current"
assert_absent "$PREVIOUS_LINK"
assert_equal "$MOCK_OLD_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "current preflight failure changed backend"
assert_absent "$TARGET_RELEASE/deployment-state.json"
grep -q 'current release is not a verified rollback target' "$TEST_ROOT/current-preflight-failure.log" \
  || fail "current preflight rejection evidence missing"

reset_old_state
export MOCK_PROVIDER_FAIL_RELEASE="$MOCK_TARGET_ID"
export MOCK_PULL_FAIL_REF="$MOCK_OLD_BACKEND_REF"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/provider-failure.log" 2>&1; then
  fail "provider failure unexpectedly deployed"
fi
unset MOCK_PROVIDER_FAIL_RELEASE
unset MOCK_PULL_FAIL_REF
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "provider failure did not restore current"
assert_absent "$PREVIOUS_LINK"
assert_absent "$JOURNAL_FILE"
assert_equal "$MOCK_OLD_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "provider failure did not restore backend"
assert_absent "$TARGET_RELEASE/deployment-state.json"
grep -q 'automatic recovery succeeded' "$TEST_ROOT/provider-failure.log" || fail "provider recovery evidence missing"

reset_old_state
export MOCK_SIGNAL_PROVIDER_RELEASE="$MOCK_TARGET_ID"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/signal-recovery.log" 2>&1; then
  fail "terminated candidate transaction unexpectedly deployed"
fi
unset MOCK_SIGNAL_PROVIDER_RELEASE
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "signal recovery did not restore current"
assert_equal "$MOCK_OLD_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "signal recovery did not restore backend"
assert_absent "$PREVIOUS_LINK"
assert_absent "$JOURNAL_FILE"
grep -q 'candidate transaction interrupted' "$TEST_ROOT/signal-recovery.log" \
  || fail "signal recovery evidence missing"

reset_old_state
cp "$TARGET_RELEASE/manifest.env" "$TARGET_RELEASE/manifest.env.empty-test"
cp "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py" \
  "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py.empty-test"
printf '# verifier exits successfully without a PASS marker\n' \
  >"$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py"
empty_sha="$(sha256sum "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py" | awk '{print $1}')"
sed -i "s/^ODIRAG_INTEGRITY_CHECK_SHA256=.*/ODIRAG_INTEGRITY_CHECK_SHA256=$empty_sha/" \
  "$TARGET_RELEASE/manifest.env"
export MOCK_MARKERLESS_INTEGRITY_RELEASE="$MOCK_TARGET_ID"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/empty-verifier.log" 2>&1; then
  fail "markerless integrity verifier unexpectedly deployed"
fi
unset MOCK_MARKERLESS_INTEGRITY_RELEASE
mv -f "$TARGET_RELEASE/manifest.env.empty-test" "$TARGET_RELEASE/manifest.env"
mv -f "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py.empty-test" \
  "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py"
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "markerless verifier changed current"
assert_absent "$JOURNAL_FILE"
grep -q 'did not emit its required PASS marker' "$TEST_ROOT/empty-verifier.log" \
  || fail "markerless verifier rejection evidence missing"

reset_old_state
chown 65534:65534 "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/non-root-release-file.log" 2>&1; then
  fail "non-root-owned release input unexpectedly deployed"
fi
chown 0:0 "$TARGET_RELEASE/deploy/production/scripts/verify-production-integrity.py"
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "non-root release input changed current"
assert_absent "$JOURNAL_FILE"
grep -q 'must be owned by root' "$TEST_ROOT/non-root-release-file.log" \
  || fail "non-root release input rejection evidence missing"

reset_old_state
export MOCK_HTTP_STATUS=204
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/non-200-health.log" 2>&1; then
  fail "non-200 health response unexpectedly deployed"
fi
unset MOCK_HTTP_STATUS
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "non-200 health response changed current"
assert_absent "$JOURNAL_FILE"
grep -q 'did not return HTTP 200' "$TEST_ROOT/non-200-health.log" \
  || fail "non-200 health rejection evidence missing"

reset_old_state
mv "$OLD_RELEASE/manifest.env" "$OLD_RELEASE/manifest.env.saved"
printf '%s\n' "$MOCK_LEGACY_BACKEND_REF" >"$MOCK_STATE_DIR/backend-ref"
printf '%s\n' "$MOCK_LEGACY_FRONTEND_REF" >"$MOCK_STATE_DIR/frontend-ref"
export MOCK_PROVIDER_FAIL_RELEASE="$MOCK_TARGET_ID"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/legacy-provider-failure.log" 2>&1; then
  fail "legacy bootstrap provider failure unexpectedly deployed"
fi
unset MOCK_PROVIDER_FAIL_RELEASE
mv "$OLD_RELEASE/manifest.env.saved" "$OLD_RELEASE/manifest.env"
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "legacy recovery did not restore current"
assert_absent "$PREVIOUS_LINK"
assert_equal "$MOCK_LEGACY_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "legacy recovery did not restore backend"
assert_equal "$MOCK_LEGACY_FRONTEND_REF" "$(cat "$MOCK_STATE_DIR/frontend-ref")" "legacy recovery did not restore frontend"
assert_equal "$OLD_RELEASE/deploy/production/nginx.conf" "$(cat "$MOCK_STATE_DIR/nginx-source")" "legacy recovery did not restore Nginx"
assert_absent "$TARGET_RELEASE/deployment-state.json"
grep -q 'mode=legacy-bootstrap' "$TEST_ROOT/legacy-provider-failure.log" || fail "legacy recovery evidence missing"
assert_absent "$JOURNAL_FILE"

reset_old_state
export MOCK_FAIL_CURRENT_PROMOTION_ONCE_FILE="$TEST_ROOT/current-promotion-failed"
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/pointer-failure.log" 2>&1; then
  fail "pointer failure unexpectedly deployed"
fi
unset MOCK_FAIL_CURRENT_PROMOTION_ONCE_FILE
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "pointer failure did not restore current"
assert_absent "$PREVIOUS_LINK"
assert_equal "$MOCK_OLD_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "pointer failure did not restore backend"
assert_absent "$TARGET_RELEASE/deployment-state.json"
assert_absent "$JOURNAL_FILE"

reset_old_state
printf '%s\n' "$MOCK_TARGET_BACKEND_REF" >"$MOCK_STATE_DIR/backend-ref"
printf '%s\n' "$MOCK_TARGET_FRONTEND_REF" >"$MOCK_STATE_DIR/frontend-ref"
printf '%s\n' "$TARGET_RELEASE/deploy/production/nginx.conf" >"$MOCK_STATE_DIR/nginx-source"
write_stale_release_journal
if ! run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/deploy-success.log" 2>&1; then
  fail "expected deployment success"
fi
grep -q 'unfinished_release_recovery=PASS-LIVE' "$TEST_ROOT/deploy-success.log" \
  || fail "unfinished transaction recovery evidence missing"
assert_absent "$JOURNAL_FILE"
assert_equal "$TARGET_RELEASE" "$(realpath -e "$CURRENT_LINK")" "successful deployment current mismatch"
assert_equal "$OLD_RELEASE" "$(realpath -e "$PREVIOUS_LINK")" "successful deployment previous mismatch"
[[ -f "$TARGET_RELEASE/deployment-state.json" ]] || fail "successful deployment state missing"
assert_equal "$MOCK_TARGET_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "successful deployment backend mismatch"
assert_equal "$TARGET_RELEASE/deploy/production/nginx.conf" "$(cat "$MOCK_STATE_DIR/nginx-source")" "Nginx config was not updated"
write_stale_release_journal
if run_verify --providers "$TARGET_RELEASE" >"$TEST_ROOT/verify-journal-present.log" 2>&1; then
  fail "verification accepted an unfinished release journal"
fi
rm -f -- "$JOURNAL_FILE"
grep -q 'unfinished release transaction' "$TEST_ROOT/verify-journal-present.log" \
  || fail "unfinished journal verification rejection evidence missing"
export MOCK_STATE_VALIDATE_FAIL=1
if run_verify --providers "$TARGET_RELEASE" >"$TEST_ROOT/verify-state-invalid.log" 2>&1; then
  fail "verification accepted an invalid deployment state"
fi
unset MOCK_STATE_VALIDATE_FAIL
if ! run_verify --providers "$TARGET_RELEASE" >"$TEST_ROOT/verify-success.log" 2>&1; then
  fail "expected current release verification success"
fi

if run_verify "$OLD_RELEASE" >"$TEST_ROOT/wrong-target.log" 2>&1; then
  fail "verification accepted a non-current target"
fi

printf '%s\n' "$MOCK_OLD_BACKEND_REF" >"$MOCK_STATE_DIR/backend-ref"
if run_verify "$TARGET_RELEASE" >"$TEST_ROOT/wrong-image.log" 2>&1; then
  fail "verification accepted the wrong running image"
fi
printf '%s\n' "$MOCK_TARGET_BACKEND_REF" >"$MOCK_STATE_DIR/backend-ref"

export MOCK_FLOCK_FAIL=1
if run_verify "$TARGET_RELEASE" >"$TEST_ROOT/lock-failure.log" 2>&1; then
  fail "verification ignored the release lock"
fi
unset MOCK_FLOCK_FAIL

export MOCK_MULTIPLE_HEADS=1
if run_verify "$TARGET_RELEASE" >"$TEST_ROOT/multiple-heads.log" 2>&1; then
  fail "verification accepted multiple Alembic heads"
fi
unset MOCK_MULTIPLE_HEADS

export MOCK_PROVIDER_FAIL_RELEASE="$MOCK_TARGET_ID"
export MOCK_HEALTH_FAIL_RELEASE="$MOCK_TARGET_ID"
if ! ODIRAG_RELEASE_ROOT="$RELEASE_ROOT" \
  ODIRAG_CURRENT_LINK="$CURRENT_LINK" \
  ODIRAG_PREVIOUS_LINK="$PREVIOUS_LINK" \
  ODIRAG_RUNTIME_ENV_FILE="$RUNTIME_ENV" \
  ODIRAG_RELEASE_LOCK="$LOCK_FILE" \
  ODIRAG_RELEASE_JOURNAL="$JOURNAL_FILE" \
    "$REPOSITORY_ROOT/deploy/production/scripts/rollback-release.sh" >"$TEST_ROOT/rollback-success.log" 2>&1; then
  fail "expected rollback success"
fi
unset MOCK_PROVIDER_FAIL_RELEASE
unset MOCK_HEALTH_FAIL_RELEASE
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "rollback current mismatch"
assert_equal "$TARGET_RELEASE" "$(realpath -e "$PREVIOUS_LINK")" "rollback previous mismatch"
assert_equal "$MOCK_OLD_BACKEND_REF" "$(cat "$MOCK_STATE_DIR/backend-ref")" "rollback backend mismatch"
assert_absent "$JOURNAL_FILE"

target_state_sha_before="$(sha256sum "$TARGET_RELEASE/deployment-state.json" | awk '{print $1}')"
export MOCK_PARTIAL_BACKUP_FAIL=1
if run_deploy "$TARGET_RELEASE" >"$TEST_ROOT/partial-state-backup.log" 2>&1; then
  fail "partial candidate state backup unexpectedly deployed"
fi
unset MOCK_PARTIAL_BACKUP_FAIL
assert_equal "$OLD_RELEASE" "$(realpath -e "$CURRENT_LINK")" "partial state backup changed current"
assert_equal "$target_state_sha_before" \
  "$(sha256sum "$TARGET_RELEASE/deployment-state.json" | awk '{print $1}')" \
  "partial state backup changed the prior deployment state"
assert_absent "$TARGET_RELEASE/.deployment-state.json.pretransaction"
assert_absent "$TARGET_RELEASE/.deployment-state.json.pretransaction.tmp"
assert_absent "$JOURNAL_FILE"

printf 'release_lifecycle_fault_injection=PASS scenarios=19\n'
