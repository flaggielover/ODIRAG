#!/usr/bin/env bash
set -Eeuo pipefail

readonly ODIRAG_RELEASE_ROOT="${ODIRAG_RELEASE_ROOT:-/opt/odirag/releases}"
readonly ODIRAG_CURRENT_LINK="${ODIRAG_CURRENT_LINK:-/opt/odirag/current}"
readonly ODIRAG_PREVIOUS_LINK="${ODIRAG_PREVIOUS_LINK:-/opt/odirag/previous}"
readonly ODIRAG_RUNTIME_ENV_FILE="${ODIRAG_RUNTIME_ENV_FILE:-/etc/odirag/production.env}"
readonly ODIRAG_RELEASE_LOCK="${ODIRAG_RELEASE_LOCK:-/run/lock/odirag-release.lock}"

release_log() {
  printf '[odirag-release] %s\n' "$*"
}

release_die() {
  printf '[odirag-release] ERROR: %s\n' "$*" >&2
  return 1
}

require_release_command() {
  command -v "$1" >/dev/null 2>&1 || release_die "required command is unavailable: $1"
}

resolve_release_dir() {
  local requested="$1" resolved root_resolved
  resolved="$(realpath -e -- "$requested")" || return 1
  root_resolved="$(realpath -e -- "$ODIRAG_RELEASE_ROOT")" || return 1
  case "$resolved/" in
    "$root_resolved"/*/) printf '%s\n' "$resolved" ;;
    *) release_die "release directory is outside the approved release root" ;;
  esac
}

manifest_value() {
  local manifest="$1" key="$2" count line
  count="$(grep -c -E "^${key}=" "$manifest" || true)"
  [[ "$count" == "1" ]] || release_die "manifest key is missing or duplicated: $key"
  line="$(grep -E "^${key}=" "$manifest")"
  printf '%s\n' "${line#*=}"
}

validate_file_permissions() {
  local path="$1" mode
  [[ -s "$path" && ! -L "$path" ]] || release_die "required file is missing, empty, or a symlink"
  mode="$(stat -c '%a' -- "$path")"
  (( (8#$mode & 022) == 0 )) || release_die "required file is group/world writable"
}

load_release_manifest() {
  local release_dir="$1" manifest unexpected
  manifest="$release_dir/manifest.env"
  validate_file_permissions "$manifest"
  unexpected="$(grep -Ev '^(#.*|[[:space:]]*|ODIRAG_(RELEASE_ID|SOURCE_COMMIT|BACKEND_IMAGE_REF|FRONTEND_IMAGE_REF|ALEMBIC_HEAD|COMPOSE_SHA256|BUILD_CREATED)=[^[:space:]]+)$' "$manifest" || true)"
  [[ -z "$unexpected" ]] || release_die "manifest contains an unexpected key or whitespace"

  RELEASE_DIR="$release_dir"
  RELEASE_MANIFEST="$manifest"
  RELEASE_COMPOSE="$release_dir/deploy/production/compose.yml"
  RELEASE_ID="$(manifest_value "$manifest" ODIRAG_RELEASE_ID)"
  RELEASE_COMMIT="$(manifest_value "$manifest" ODIRAG_SOURCE_COMMIT)"
  RELEASE_BACKEND_REF="$(manifest_value "$manifest" ODIRAG_BACKEND_IMAGE_REF)"
  RELEASE_FRONTEND_REF="$(manifest_value "$manifest" ODIRAG_FRONTEND_IMAGE_REF)"
  RELEASE_ALEMBIC_HEAD="$(manifest_value "$manifest" ODIRAG_ALEMBIC_HEAD)"
  RELEASE_COMPOSE_SHA="$(manifest_value "$manifest" ODIRAG_COMPOSE_SHA256)"
  RELEASE_BUILD_CREATED="$(manifest_value "$manifest" ODIRAG_BUILD_CREATED)"

  [[ "$RELEASE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || release_die "invalid release id"
  [[ "$(basename -- "$release_dir")" == "$RELEASE_ID" ]] || release_die "release id does not match directory name"
  [[ "$RELEASE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || release_die "source commit must be a full Git SHA"
  [[ "$RELEASE_BACKEND_REF" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] || release_die "backend image is not an immutable GHCR digest reference"
  [[ "$RELEASE_FRONTEND_REF" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] || release_die "frontend image is not an immutable GHCR digest reference"
  [[ "$RELEASE_ALEMBIC_HEAD" =~ ^[0-9a-z_]+$ ]] || release_die "invalid Alembic head"
  [[ "$RELEASE_COMPOSE_SHA" =~ ^[0-9a-f]{64}$ ]] || release_die "invalid Compose checksum"
  [[ -f "$RELEASE_COMPOSE" && ! -L "$RELEASE_COMPOSE" ]] || release_die "release Compose file is missing"
  [[ "$(sha256sum "$RELEASE_COMPOSE" | awk '{print $1}')" == "$RELEASE_COMPOSE_SHA" ]] || release_die "release Compose checksum mismatch"
}

compose_for_release() {
  ODIRAG_RELEASE_ID="$RELEASE_ID" \
  ODIRAG_SOURCE_COMMIT="$RELEASE_COMMIT" \
  ODIRAG_BACKEND_IMAGE_REF="$RELEASE_BACKEND_REF" \
  ODIRAG_FRONTEND_IMAGE_REF="$RELEASE_FRONTEND_REF" \
    docker compose --env-file "$ODIRAG_RUNTIME_ENV_FILE" -f "$RELEASE_COMPOSE" "$@"
}

release_project_name() {
  local project
  project="$(sed -nE 's/^COMPOSE_PROJECT_NAME=([A-Za-z0-9_.-]+)$/\1/p' "$ODIRAG_RUNTIME_ENV_FILE" | head -n 1)"
  printf '%s\n' "${project:-odirag-prod}"
}

release_container_id() {
  local service="$1" project
  project="$(release_project_name)"
  docker ps -aq \
    --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=$service" | head -n 1
}

wait_release_service() {
  local service="$1" deadline="$2" container status
  while (( SECONDS < deadline )); do
    container="$(release_container_id "$service")"
    if [[ -n "$container" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
      [[ "$status" == "healthy" || "$status" == "running" ]] && return 0
    fi
    sleep 5
  done
  release_die "service did not become healthy: $service"
}

wait_release_stack() {
  local timeout_seconds="${1:-360}" deadline service
  deadline=$((SECONDS + timeout_seconds))
  for service in postgres redis qdrant backend worker scheduler frontend nginx; do
    wait_release_service "$service" "$deadline" || return 1
  done
  curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/health/live >/dev/null || return 1
  curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/health/ready >/dev/null || return 1
  curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/healthz >/dev/null || return 1
}

validate_release_images() {
  local backend_id frontend_id backend_revision frontend_revision backend_version frontend_version
  backend_id="$(docker image inspect --format '{{.Id}}' "$RELEASE_BACKEND_REF")" || return 1
  frontend_id="$(docker image inspect --format '{{.Id}}' "$RELEASE_FRONTEND_REF")" || return 1
  backend_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$RELEASE_BACKEND_REF")"
  frontend_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$RELEASE_FRONTEND_REF")"
  backend_version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$RELEASE_BACKEND_REF")"
  frontend_version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$RELEASE_FRONTEND_REF")"
  [[ "$backend_revision" == "$RELEASE_COMMIT" && "$frontend_revision" == "$RELEASE_COMMIT" ]] || release_die "image revision label mismatch"
  [[ "$backend_version" == "$RELEASE_ID" && "$frontend_version" == "$RELEASE_ID" ]] || release_die "image release label mismatch"
  RELEASE_BACKEND_IMAGE_ID="$backend_id"
  RELEASE_FRONTEND_IMAGE_ID="$frontend_id"
}

validate_release_migration() {
  local target_output target_head backend_container database_output database_head
  target_output="$(docker run --rm --entrypoint python "$RELEASE_BACKEND_REF" -m alembic heads)" || return 1
  target_head="$(grep -Eo '^[0-9a-z_]+' <<<"$target_output" | head -n 1)"
  [[ "$target_head" == "$RELEASE_ALEMBIC_HEAD" ]] || release_die "target image Alembic head mismatch"

  backend_container="$(release_container_id backend)"
  if [[ -n "$backend_container" ]]; then
    database_output="$(docker exec "$backend_container" python -m alembic current)" || return 1
    database_head="$(grep -Eo '^[0-9a-z_]+' <<<"$database_output" | tail -n 1)"
    [[ "$database_head" == "$RELEASE_ALEMBIC_HEAD" ]] || release_die "database migration head is not release-compatible"
  fi
}

activate_loaded_release() {
  validate_file_permissions "$ODIRAG_RUNTIME_ENV_FILE" || return 1
  compose_for_release config --quiet || return 1
  docker pull "$RELEASE_BACKEND_REF" || return 1
  docker pull "$RELEASE_FRONTEND_REF" || return 1
  validate_release_images || return 1
  validate_release_migration || return 1

  compose_for_release up -d --no-deps --no-build --pull never backend || return 1
  wait_release_service backend $((SECONDS + 300)) || return 1
  compose_for_release up -d --no-deps --no-build --pull never worker scheduler frontend || return 1
  wait_release_stack 360 || return 1

  local service container actual expected
  for service in backend worker scheduler; do
    container="$(release_container_id "$service")"
    actual="$(docker inspect --format '{{.Image}}' "$container")"
    expected="$RELEASE_BACKEND_IMAGE_ID"
    [[ "$actual" == "$expected" ]] || release_die "running backend-family image mismatch: $service"
  done
  container="$(release_container_id frontend)"
  actual="$(docker inspect --format '{{.Image}}' "$container")"
  [[ "$actual" == "$RELEASE_FRONTEND_IMAGE_ID" ]] || release_die "running frontend image mismatch"
}

promote_release_links() {
  local target="$1" old="$2" temp
  if [[ -n "$old" && "$old" != "$target" ]]; then
    temp="${ODIRAG_PREVIOUS_LINK}.tmp.$$"
    ln -s -- "$old" "$temp"
    mv -Tf -- "$temp" "$ODIRAG_PREVIOUS_LINK"
  fi
  temp="${ODIRAG_CURRENT_LINK}.tmp.$$"
  ln -s -- "$target" "$temp"
  mv -Tf -- "$temp" "$ODIRAG_CURRENT_LINK"
}

write_release_state() {
  local target="$1" previous="$2" mode="$3" duration="$4" state
  state="$target/deployment-state.json"
  python3 - "$state" "$RELEASE_ID" "$RELEASE_COMMIT" "$RELEASE_BACKEND_REF" \
    "$RELEASE_FRONTEND_REF" "$RELEASE_BACKEND_IMAGE_ID" "$RELEASE_FRONTEND_IMAGE_ID" \
    "$RELEASE_ALEMBIC_HEAD" "$RELEASE_COMPOSE_SHA" "$RELEASE_BUILD_CREATED" \
    "$previous" "$mode" "$duration" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime

(
    path,
    release_id,
    commit,
    backend_ref,
    frontend_ref,
    backend_id,
    frontend_id,
    alembic_head,
    compose_sha,
    build_created,
    previous,
    mode,
    duration,
) = sys.argv[1:]
payload = {
    "schema_version": 1,
    "release_id": release_id,
    "source_commit": commit,
    "backend_image_ref": backend_ref,
    "frontend_image_ref": frontend_ref,
    "backend_image_id": backend_id,
    "frontend_image_id": frontend_id,
    "alembic_head": alembic_head,
    "compose_sha256": compose_sha,
    "build_created": build_created,
    "previous_release": previous or None,
    "operation": mode,
    "duration_seconds": float(duration),
    "verified_at": datetime.now(UTC).isoformat(),
}
temporary = f"{path}.tmp"
with open(temporary, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.chmod(temporary, 0o644)
os.replace(temporary, path)
PY
}

acquire_release_lock() {
  require_release_command flock
  exec 9>"$ODIRAG_RELEASE_LOCK"
  flock -n 9 || release_die "another release operation holds the deployment lock"
}

release_preflight() {
  local command
  for command in curl docker flock grep realpath sha256sum stat python3; do
    require_release_command "$command" || return 1
  done
  docker compose version >/dev/null
  [[ "$(id -u)" == "0" ]] || release_die "release operations must run as root"
  [[ -d "$ODIRAG_RELEASE_ROOT" && ! -L "$ODIRAG_RELEASE_ROOT" ]] || release_die "release root is unavailable"
}
