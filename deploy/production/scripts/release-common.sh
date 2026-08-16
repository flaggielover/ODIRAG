#!/usr/bin/env bash
set -Eeuo pipefail

readonly ODIRAG_RELEASE_ROOT="${ODIRAG_RELEASE_ROOT:-/opt/odirag/releases}"
readonly ODIRAG_CURRENT_LINK="${ODIRAG_CURRENT_LINK:-/opt/odirag/current}"
readonly ODIRAG_PREVIOUS_LINK="${ODIRAG_PREVIOUS_LINK:-/opt/odirag/previous}"
readonly ODIRAG_RUNTIME_ENV_FILE="${ODIRAG_RUNTIME_ENV_FILE:-/etc/odirag/production.env}"
readonly ODIRAG_RELEASE_LOCK="${ODIRAG_RELEASE_LOCK:-/run/lock/odirag-release.lock}"
readonly ODIRAG_RELEASE_JOURNAL="${ODIRAG_RELEASE_JOURNAL:-/opt/odirag/.release-transaction.env}"

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

resolve_optional_release_link() {
  local link="$1"
  if [[ ! -e "$link" && ! -L "$link" ]]; then
    return 0
  fi
  [[ -L "$link" ]] || { release_die "release pointer is not a symbolic link: $link"; return 1; }
  resolve_release_dir "$link"
}

manifest_value() {
  local manifest="$1" key="$2" count line
  count="$(grep -c -E "^${key}=" "$manifest" || true)"
  [[ "$count" == "1" ]] || { release_die "manifest key is missing or duplicated: $key"; return 1; }
  line="$(grep -E "^${key}=" "$manifest")"
  printf '%s\n' "${line#*=}"
}

validate_file_permissions() {
  local path="$1" mode owner
  [[ -s "$path" && ! -L "$path" ]] \
    || { release_die "required file is missing, empty, or a symlink"; return 1; }
  mode="$(stat -c '%a' -- "$path")"
  owner="$(stat -c '%u' -- "$path")"
  [[ "$owner" == "0" ]] || { release_die "required file must be owned by root"; return 1; }
  (( (8#$mode & 022) == 0 )) || release_die "required file is group/world writable"
}

validate_directory_permissions() {
  local path="$1" mode owner
  [[ -d "$path" && ! -L "$path" ]] \
    || { release_die "required directory is missing or a symlink"; return 1; }
  mode="$(stat -c '%a' -- "$path")" || return 1
  owner="$(stat -c '%u' -- "$path")" || return 1
  [[ "$owner" == "0" ]] || { release_die "required directory must be owned by root"; return 1; }
  (( (8#$mode & 022) == 0 )) \
    || { release_die "required directory is group/world writable"; return 1; }
}

validate_runtime_environment() {
  local mode owner
  validate_file_permissions "$ODIRAG_RUNTIME_ENV_FILE" || return 1
  mode="$(stat -c '%a' -- "$ODIRAG_RUNTIME_ENV_FILE")" || return 1
  owner="$(stat -c '%u' -- "$ODIRAG_RUNTIME_ENV_FILE")" || return 1
  [[ "$owner" == "0" ]] || { release_die "runtime environment must be owned by root"; return 1; }
  [[ "$mode" == "600" || "$mode" == "640" ]] \
    || { release_die "runtime environment mode must be 0600 or 0640"; return 1; }
}

validate_sha256_file() {
  local path="$1" expected="$2"
  validate_file_permissions "$path" || return 1
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$expected" ]] \
    || release_die "release file checksum mismatch: $(basename -- "$path")"
}

load_release_manifest() {
  local release_dir="$1" manifest unexpected
  validate_directory_permissions "$release_dir" || return 1
  validate_directory_permissions "$release_dir/deploy" || return 1
  validate_directory_permissions "$release_dir/deploy/production" || return 1
  validate_directory_permissions "$release_dir/deploy/production/scripts" || return 1
  manifest="$release_dir/manifest.env"
  validate_file_permissions "$manifest" || return 1
  unexpected="$(grep -Ev '^(#.*|[[:space:]]*|ODIRAG_(RELEASE_ID|SOURCE_COMMIT|BACKEND_IMAGE_REF|FRONTEND_IMAGE_REF|ALEMBIC_HEAD|COMPOSE_SHA256|NGINX_SHA256|INTEGRITY_CHECK_SHA256|PROVIDER_CHECK_SHA256|BUILD_CREATED)=[^[:space:]]+)$' "$manifest" || true)"
  [[ -z "$unexpected" ]] || { release_die "manifest contains an unexpected key or whitespace"; return 1; }

  RELEASE_DIR="$release_dir"
  RELEASE_MANIFEST="$manifest"
  RELEASE_COMPOSE="$release_dir/deploy/production/compose.yml"
  RELEASE_NGINX="$release_dir/deploy/production/nginx.conf"
  RELEASE_INTEGRITY_CHECK="$release_dir/deploy/production/scripts/verify-production-integrity.py"
  RELEASE_PROVIDER_CHECK="$release_dir/deploy/production/scripts/verify-production-rag.py"
  RELEASE_ID="$(manifest_value "$manifest" ODIRAG_RELEASE_ID)"
  RELEASE_COMMIT="$(manifest_value "$manifest" ODIRAG_SOURCE_COMMIT)"
  RELEASE_BACKEND_REF="$(manifest_value "$manifest" ODIRAG_BACKEND_IMAGE_REF)"
  RELEASE_FRONTEND_REF="$(manifest_value "$manifest" ODIRAG_FRONTEND_IMAGE_REF)"
  RELEASE_ALEMBIC_HEAD="$(manifest_value "$manifest" ODIRAG_ALEMBIC_HEAD)"
  RELEASE_COMPOSE_SHA="$(manifest_value "$manifest" ODIRAG_COMPOSE_SHA256)"
  RELEASE_NGINX_SHA="$(manifest_value "$manifest" ODIRAG_NGINX_SHA256)"
  RELEASE_INTEGRITY_CHECK_SHA="$(manifest_value "$manifest" ODIRAG_INTEGRITY_CHECK_SHA256)"
  RELEASE_PROVIDER_CHECK_SHA="$(manifest_value "$manifest" ODIRAG_PROVIDER_CHECK_SHA256)"
  RELEASE_BUILD_CREATED="$(manifest_value "$manifest" ODIRAG_BUILD_CREATED)"

  [[ "$RELEASE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || { release_die "invalid release id"; return 1; }
  [[ "$(basename -- "$release_dir")" == "$RELEASE_ID" ]] || { release_die "release id does not match directory name"; return 1; }
  [[ "$RELEASE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { release_die "source commit must be a full Git SHA"; return 1; }
  [[ "$RELEASE_BACKEND_REF" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] || { release_die "backend image is not an immutable GHCR digest reference"; return 1; }
  [[ "$RELEASE_FRONTEND_REF" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] || { release_die "frontend image is not an immutable GHCR digest reference"; return 1; }
  [[ "$RELEASE_ALEMBIC_HEAD" =~ ^[0-9a-z_]+$ ]] || { release_die "invalid Alembic head"; return 1; }
  [[ "$RELEASE_COMPOSE_SHA" =~ ^[0-9a-f]{64}$ ]] || { release_die "invalid Compose checksum"; return 1; }
  [[ "$RELEASE_NGINX_SHA" =~ ^[0-9a-f]{64}$ ]] || { release_die "invalid Nginx checksum"; return 1; }
  [[ "$RELEASE_INTEGRITY_CHECK_SHA" =~ ^[0-9a-f]{64}$ ]] || { release_die "invalid integrity-check checksum"; return 1; }
  [[ "$RELEASE_PROVIDER_CHECK_SHA" =~ ^[0-9a-f]{64}$ ]] || { release_die "invalid provider-check checksum"; return 1; }
  [[ "$RELEASE_BUILD_CREATED" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([+-][0-9]{2}:[0-9]{2}|Z)$ ]] \
    || { release_die "invalid build timestamp"; return 1; }
  validate_sha256_file "$RELEASE_COMPOSE" "$RELEASE_COMPOSE_SHA" || return 1
  validate_sha256_file "$RELEASE_NGINX" "$RELEASE_NGINX_SHA" || return 1
  validate_sha256_file "$RELEASE_INTEGRITY_CHECK" "$RELEASE_INTEGRITY_CHECK_SHA" || return 1
  validate_sha256_file "$RELEASE_PROVIDER_CHECK" "$RELEASE_PROVIDER_CHECK_SHA" || return 1
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
  local -a containers
  project="$(release_project_name)"
  mapfile -t containers < <(
    docker ps -q \
      --filter "label=com.docker.compose.project=$project" \
      --filter "label=com.docker.compose.service=$service"
  )
  (( ${#containers[@]} <= 1 )) || { release_die "multiple running containers found for service: $service"; return 1; }
  if (( ${#containers[@]} == 1 )); then
    printf '%s\n' "${containers[0]}"
  fi
}

wait_release_service() {
  local service="$1" deadline="$2" container status
  while (( SECONDS < deadline )); do
    container="$(release_container_id "$service")" || return 1
    if [[ -n "$container" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "$container" 2>/dev/null || true)"
      [[ "$status" == "healthy" ]] && return 0
    fi
    sleep 5
  done
  release_die "service did not become healthy: $service"
}

require_http_200() {
  local url="$1" status
  status="$(curl --silent --show-error --max-time 10 --output /dev/null \
    --write-out '%{http_code}' "$url")" || return 1
  [[ "$status" == "200" ]] || { release_die "health endpoint did not return HTTP 200"; return 1; }
}

wait_release_stack() {
  local timeout_seconds="${1:-360}" deadline service
  deadline=$((SECONDS + timeout_seconds))
  for service in postgres redis qdrant backend worker scheduler frontend nginx; do
    wait_release_service "$service" "$deadline" || return 1
  done
  require_http_200 http://127.0.0.1:8080/health/live || return 1
  require_http_200 http://127.0.0.1:8080/health/ready || return 1
  require_http_200 http://127.0.0.1:8080/healthz || return 1
}

validate_release_images() {
  local backend_id frontend_id backend_revision frontend_revision backend_version frontend_version
  local backend_created frontend_created backend_digests frontend_digests
  backend_id="$(docker image inspect --format '{{.Id}}' "$RELEASE_BACKEND_REF")" || return 1
  frontend_id="$(docker image inspect --format '{{.Id}}' "$RELEASE_FRONTEND_REF")" || return 1
  backend_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$RELEASE_BACKEND_REF")"
  frontend_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$RELEASE_FRONTEND_REF")"
  backend_version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$RELEASE_BACKEND_REF")"
  frontend_version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$RELEASE_FRONTEND_REF")"
  backend_created="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.created"}}' "$RELEASE_BACKEND_REF")"
  frontend_created="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.created"}}' "$RELEASE_FRONTEND_REF")"
  backend_digests="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$RELEASE_BACKEND_REF")"
  frontend_digests="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$RELEASE_FRONTEND_REF")"
  [[ "$backend_revision" == "$RELEASE_COMMIT" && "$frontend_revision" == "$RELEASE_COMMIT" ]] || { release_die "image revision label mismatch"; return 1; }
  [[ "$backend_version" == "$RELEASE_ID" && "$frontend_version" == "$RELEASE_ID" ]] || { release_die "image release label mismatch"; return 1; }
  [[ "$backend_created" == "$RELEASE_BUILD_CREATED" && "$frontend_created" == "$RELEASE_BUILD_CREATED" ]] || { release_die "image build timestamp label mismatch"; return 1; }
  grep -Fqx -- "$RELEASE_BACKEND_REF" <<<"$backend_digests" || { release_die "backend RepoDigest mismatch"; return 1; }
  grep -Fqx -- "$RELEASE_FRONTEND_REF" <<<"$frontend_digests" || { release_die "frontend RepoDigest mismatch"; return 1; }
  RELEASE_BACKEND_IMAGE_ID="$backend_id"
  RELEASE_FRONTEND_IMAGE_ID="$frontend_id"
}

validate_release_migration() {
  local target_output postgres_container database_output
  local -a target_heads database_heads
  target_output="$(docker run --rm --entrypoint python "$RELEASE_BACKEND_REF" -m alembic heads)" || return 1
  mapfile -t target_heads < <(grep -Eo '^[0-9a-z_]+' <<<"$target_output")
  (( ${#target_heads[@]} == 1 )) || { release_die "target image must contain exactly one Alembic head"; return 1; }
  [[ "${target_heads[0]}" == "$RELEASE_ALEMBIC_HEAD" ]] || { release_die "target image Alembic head mismatch"; return 1; }

  postgres_container="$(release_container_id postgres)" || return 1
  [[ -n "$postgres_container" ]] || { release_die "running PostgreSQL container is required for migration validation"; return 1; }
  database_output="$(docker exec "$postgres_container" sh -ec 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT version_num FROM alembic_version ORDER BY version_num"')" || return 1
  mapfile -t database_heads < <(grep -Eo '^[0-9a-z_]+' <<<"$database_output")
  (( ${#database_heads[@]} == 1 )) || { release_die "database must contain exactly one Alembic head"; return 1; }
  [[ "${database_heads[0]}" == "$RELEASE_ALEMBIC_HEAD" ]] || { release_die "database migration head is not release-compatible"; return 1; }
}

validate_running_service_image() {
  local service="$1" expected_id="$2" expected_ref="$3" container actual_id actual_ref
  container="$(release_container_id "$service")" || return 1
  [[ -n "$container" ]] || { release_die "running release service is missing: $service"; return 1; }
  actual_id="$(docker inspect --format '{{.Image}}' "$container")" || return 1
  actual_ref="$(docker inspect --format '{{.Config.Image}}' "$container")" || return 1
  [[ "$actual_id" == "$expected_id" ]] || { release_die "running image ID mismatch: $service"; return 1; }
  [[ "$actual_ref" == "$expected_ref" ]] || { release_die "running digest reference mismatch: $service"; return 1; }
}

validate_running_release_images() {
  local service
  for service in backend worker scheduler; do
    validate_running_service_image "$service" "$RELEASE_BACKEND_IMAGE_ID" "$RELEASE_BACKEND_REF" || return 1
  done
  validate_running_service_image frontend "$RELEASE_FRONTEND_IMAGE_ID" "$RELEASE_FRONTEND_REF"
}

legacy_image_digest() {
  local image_id="$1" repository="$2"
  local -a digests
  mapfile -t digests < <(
    docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image_id" \
      | grep -E "^${repository}@sha256:[0-9a-f]{64}$"
  )
  (( ${#digests[@]} == 1 )) \
    || { release_die "legacy recovery requires exactly one immutable RepoDigest for $repository"; return 1; }
  printf '%s\n' "${digests[0]}"
}

capture_legacy_recovery_state() {
  local legacy_dir="$1" service container image_id postgres_container database_output nginx_container nginx_source
  local -a database_heads
  LEGACY_RELEASE_DIR="$legacy_dir"
  LEGACY_RELEASE_ID="$(basename -- "$legacy_dir")"
  LEGACY_COMPOSE="$legacy_dir/deploy/production/compose.yml"
  LEGACY_NGINX="$legacy_dir/deploy/production/nginx.conf"
  validate_directory_permissions "$legacy_dir" || return 1
  validate_directory_permissions "$legacy_dir/deploy" || return 1
  validate_directory_permissions "$legacy_dir/deploy/production" || return 1
  validate_file_permissions "$LEGACY_COMPOSE" || return 1
  validate_file_permissions "$LEGACY_NGINX" || return 1
  LEGACY_COMPOSE_SHA="$(sha256sum "$LEGACY_COMPOSE" | awk '{print $1}')" || return 1
  LEGACY_NGINX_SHA="$(sha256sum "$LEGACY_NGINX" | awk '{print $1}')" || return 1

  LEGACY_BACKEND_IMAGE_ID=""
  for service in backend worker scheduler; do
    container="$(release_container_id "$service")" || return 1
    [[ -n "$container" ]] || { release_die "legacy recovery service is missing: $service"; return 1; }
    image_id="$(docker inspect --format '{{.Image}}' "$container")" || return 1
    if [[ -z "$LEGACY_BACKEND_IMAGE_ID" ]]; then
      LEGACY_BACKEND_IMAGE_ID="$image_id"
    fi
    [[ "$image_id" == "$LEGACY_BACKEND_IMAGE_ID" ]] \
      || { release_die "legacy backend-family image IDs differ"; return 1; }
  done
  container="$(release_container_id frontend)" || return 1
  [[ -n "$container" ]] || { release_die "legacy frontend service is missing"; return 1; }
  LEGACY_FRONTEND_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$container")" || return 1
  LEGACY_BACKEND_REF="$(legacy_image_digest "$LEGACY_BACKEND_IMAGE_ID" 'odirag/backend')" || return 1
  LEGACY_FRONTEND_REF="$(legacy_image_digest "$LEGACY_FRONTEND_IMAGE_ID" 'odirag/frontend')" || return 1

  nginx_container="$(release_container_id nginx)" || return 1
  [[ -n "$nginx_container" ]] || { release_die "legacy Nginx service is missing"; return 1; }
  nginx_source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/nginx/nginx.conf"}}{{.Source}}{{end}}{{end}}' "$nginx_container")" || return 1
  [[ -n "$nginx_source" && -f "$nginx_source" ]] \
    || { release_die "legacy Nginx config mount is missing"; return 1; }
  [[ "$(sha256sum "$nginx_source" | awk '{print $1}')" == "$LEGACY_NGINX_SHA" ]] \
    || { release_die "legacy Nginx config does not match current release"; return 1; }

  postgres_container="$(release_container_id postgres)" || return 1
  [[ -n "$postgres_container" ]] \
    || { release_die "legacy recovery requires the running PostgreSQL container"; return 1; }
  database_output="$(docker exec "$postgres_container" sh -ec 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT version_num FROM alembic_version ORDER BY version_num"')" || return 1
  mapfile -t database_heads < <(grep -Eo '^[0-9a-z_]+' <<<"$database_output")
  (( ${#database_heads[@]} == 1 )) \
    || { release_die "legacy database must contain exactly one Alembic head"; return 1; }
  LEGACY_ALEMBIC_HEAD="${database_heads[0]}"
  wait_release_stack 60 || return 1
  LEGACY_RECOVERY_AVAILABLE=true
  release_log "legacy_bootstrap_recovery=PASS-CONFIG release=$LEGACY_RELEASE_ID immutable_local_digests=true"
}

validate_legacy_recovery_images() {
  local backend_id frontend_id backend_digests frontend_digests
  backend_id="$(docker image inspect --format '{{.Id}}' "$LEGACY_BACKEND_REF")" || return 1
  frontend_id="$(docker image inspect --format '{{.Id}}' "$LEGACY_FRONTEND_REF")" || return 1
  [[ "$backend_id" == "$LEGACY_BACKEND_IMAGE_ID" ]] \
    || { release_die "legacy backend image ID changed"; return 1; }
  [[ "$frontend_id" == "$LEGACY_FRONTEND_IMAGE_ID" ]] \
    || { release_die "legacy frontend image ID changed"; return 1; }
  backend_digests="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$backend_id")" || return 1
  frontend_digests="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$frontend_id")" || return 1
  grep -Fqx -- "$LEGACY_BACKEND_REF" <<<"$backend_digests" \
    || { release_die "legacy backend RepoDigest changed"; return 1; }
  grep -Fqx -- "$LEGACY_FRONTEND_REF" <<<"$frontend_digests" \
    || { release_die "legacy frontend RepoDigest changed"; return 1; }
}

activate_legacy_recovery() {
  [[ "${LEGACY_RECOVERY_AVAILABLE:-false}" == "true" ]] \
    || { release_die "legacy recovery state was not captured"; return 1; }
  validate_sha256_file "$LEGACY_COMPOSE" "$LEGACY_COMPOSE_SHA" || return 1
  validate_sha256_file "$LEGACY_NGINX" "$LEGACY_NGINX_SHA" || return 1
  validate_legacy_recovery_images || return 1

  RELEASE_ID="legacy-bootstrap-$LEGACY_RELEASE_ID"
  RELEASE_COMMIT="0000000000000000000000000000000000000000"
  RELEASE_COMPOSE="$LEGACY_COMPOSE"
  RELEASE_NGINX="$LEGACY_NGINX"
  RELEASE_NGINX_SHA="$LEGACY_NGINX_SHA"
  RELEASE_BACKEND_REF="$LEGACY_BACKEND_REF"
  RELEASE_FRONTEND_REF="$LEGACY_FRONTEND_REF"
  RELEASE_BACKEND_IMAGE_ID="$LEGACY_BACKEND_IMAGE_ID"
  RELEASE_FRONTEND_IMAGE_ID="$LEGACY_FRONTEND_IMAGE_ID"
  RELEASE_ALEMBIC_HEAD="$LEGACY_ALEMBIC_HEAD"

  compose_for_release config --quiet || return 1
  validate_release_migration || return 1
  compose_for_release up -d --no-deps --no-build --pull never backend || return 1
  wait_release_service backend $((SECONDS + 300)) || return 1
  compose_for_release up -d --no-deps --no-build --pull never worker scheduler frontend || return 1
  if release_nginx_needs_recreate; then
    compose_for_release up -d --no-deps --no-build --pull never nginx || return 1
  fi
  wait_release_stack 360 || return 1
  validate_running_release_images || return 1
  validate_running_nginx_config || return 1
  run_release_integrity_check || return 1
}

release_nginx_needs_recreate() {
  local container source current_sha
  container="$(release_container_id nginx)" || return 0
  [[ -n "$container" ]] || return 0
  source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/nginx/nginx.conf"}}{{.Source}}{{end}}{{end}}' "$container" 2>/dev/null || true)"
  [[ -n "$source" && -f "$source" ]] || return 0
  current_sha="$(sha256sum "$source" | awk '{print $1}')" || return 0
  [[ "$current_sha" != "$RELEASE_NGINX_SHA" ]]
}

validate_running_nginx_config() {
  local container source
  container="$(release_container_id nginx)" || return 1
  [[ -n "$container" ]] || { release_die "running Nginx service is missing"; return 1; }
  source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/nginx/nginx.conf"}}{{.Source}}{{end}}{{end}}' "$container")" || return 1
  [[ -n "$source" && -f "$source" ]] || { release_die "running Nginx config mount is missing"; return 1; }
  [[ "$(sha256sum "$source" | awk '{print $1}')" == "$RELEASE_NGINX_SHA" ]] || release_die "running Nginx config checksum mismatch"
}

activate_loaded_release() {
  local pull_images="${1:-true}"
  [[ "$pull_images" == "true" || "$pull_images" == "false" ]] \
    || { release_die "invalid image pull mode"; return 1; }
  validate_runtime_environment \
    || { release_die "runtime environment validation failed"; return 1; }
  compose_for_release config --quiet \
    || { release_die "release Compose validation failed"; return 1; }
  if [[ "$pull_images" == "true" ]]; then
    docker pull "$RELEASE_BACKEND_REF" \
      || { release_die "backend digest pull failed"; return 1; }
    docker pull "$RELEASE_FRONTEND_REF" \
      || { release_die "frontend digest pull failed"; return 1; }
  fi
  validate_release_images \
    || { release_die "release image identity validation failed"; return 1; }
  validate_release_migration \
    || { release_die "release migration compatibility validation failed"; return 1; }

  compose_for_release up -d --no-deps --no-build --pull never backend \
    || { release_die "backend activation failed"; return 1; }
  wait_release_service backend $((SECONDS + 300)) \
    || { release_die "backend health gate failed"; return 1; }
  compose_for_release up -d --no-deps --no-build --pull never worker scheduler frontend \
    || { release_die "worker/scheduler/frontend activation failed"; return 1; }
  if release_nginx_needs_recreate; then
    release_log "recreating Nginx because the mounted release config changed"
    compose_for_release up -d --no-deps --no-build --pull never nginx \
      || { release_die "Nginx activation failed"; return 1; }
  fi
  wait_release_stack 360 \
    || { release_die "release stack health gate failed"; return 1; }
  validate_running_release_images \
    || { release_die "running image identity validation failed"; return 1; }
  validate_running_nginx_config \
    || { release_die "running Nginx config validation failed"; return 1; }
}

run_release_python_check() {
  local script="$1" expected_sha="$2" check_name="$3" backend_container temporary status output marker
  shift 3
  (( $# > 0 )) || { release_die "release check requires a PASS marker"; return 1; }
  validate_sha256_file "$script" "$expected_sha" || return 1
  backend_container="$(release_container_id backend)" || return 1
  [[ -n "$backend_container" ]] || { release_die "backend is unavailable for release check: $check_name"; return 1; }
  temporary="/tmp/odirag-${check_name}-$$.py"
  docker cp "$script" "$backend_container:$temporary" >/dev/null || return 1
  status=0
  output="$(docker exec "$backend_container" python "$temporary")" || status=$?
  docker exec --user 0:0 "$backend_container" rm -f -- "$temporary" >/dev/null 2>&1 || {
    (( status != 0 )) || return 1
  }
  (( status == 0 )) || return "$status"
  for marker in "$@"; do
    grep -Eq "^${marker}([[:space:]]|$)" <<<"$output" \
      || { release_die "release check did not emit its required PASS marker: $check_name"; return 1; }
  done
  printf '%s\n' "$output"
}

run_release_integrity_check() {
  run_release_python_check "$RELEASE_INTEGRITY_CHECK" "$RELEASE_INTEGRITY_CHECK_SHA" \
    production-integrity production_data_integrity=PASS-LIVE
}

run_release_provider_check() {
  run_release_python_check "$RELEASE_PROVIDER_CHECK" "$RELEASE_PROVIDER_CHECK_SHA" \
    production-providers production_grounded_rag=PASS-LIVE \
    production_out_of_scope_refusal=PASS-LIVE
}

verify_loaded_release() {
  local providers="${1:-false}"
  validate_runtime_environment || return 1
  compose_for_release config --quiet || return 1
  validate_release_images || return 1
  validate_release_migration || return 1
  wait_release_stack 60 || return 1
  validate_running_release_images || return 1
  validate_running_nginx_config || return 1
  run_release_integrity_check || return 1
  if [[ "$providers" == "true" ]]; then
    run_release_provider_check || return 1
  fi
}

validate_loaded_recovery_descriptor() {
  validate_runtime_environment || return 1
  compose_for_release config --quiet || return 1
  validate_release_images || return 1
  validate_release_migration || return 1
}

release_journal_value() {
  local key="$1" count line
  count="$(grep -c -E "^${key}=" "$ODIRAG_RELEASE_JOURNAL" || true)"
  [[ "$count" == "1" ]] \
    || { release_die "release journal key is missing or duplicated: $key"; return 1; }
  line="$(grep -E "^${key}=" "$ODIRAG_RELEASE_JOURNAL")"
  printf '%s\n' "${line#*=}"
}

write_release_journal() {
  local mode="$1" target="$2" original_current="$3" original_previous="$4"
  local backend_ref="$5" frontend_ref="$6" backend_id="$7" frontend_id="$8"
  local legacy_compose="${9:--}" legacy_nginx="${10:--}"
  local legacy_compose_sha="${11:--}" legacy_nginx_sha="${12:--}"
  local legacy_alembic_head="${13:--}" state_existed="${14:-false}"
  local state_backup="${15:-NONE}" state_sha="${16:-NONE}" temporary
  [[ "$mode" == "release" || "$mode" == "legacy-bootstrap" ]] \
    || { release_die "invalid release journal mode"; return 1; }
  [[ ! -e "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" ]] \
    || { release_die "an unfinished release transaction already exists"; return 1; }
  for value in "$target" "$original_current" "$original_previous" "$backend_ref" \
    "$frontend_ref" "$backend_id" "$frontend_id" "$legacy_compose" "$legacy_nginx" \
    "$legacy_compose_sha" "$legacy_nginx_sha" "$legacy_alembic_head"; do
    [[ -n "$value" && "$value" != *[[:space:]]* ]] \
      || { release_die "release journal values must be non-empty and whitespace-free"; return 1; }
  done
  [[ "$state_existed" == "true" || "$state_existed" == "false" ]] \
    || { release_die "invalid candidate state journal flag"; return 1; }
  [[ -n "$state_backup" && "$state_backup" != *[[:space:]]* ]] \
    || { release_die "invalid candidate state backup path"; return 1; }
  [[ "$state_sha" == "NONE" || "$state_sha" =~ ^[0-9a-f]{64}$ ]] \
    || { release_die "invalid candidate state checksum"; return 1; }
  temporary="${ODIRAG_RELEASE_JOURNAL}.tmp.$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] \
    || { release_die "temporary release journal already exists"; return 1; }
  umask 077
  {
    printf 'ODIRAG_JOURNAL_VERSION=1\n'
    printf 'ODIRAG_JOURNAL_MODE=%s\n' "$mode"
    printf 'ODIRAG_JOURNAL_TARGET_DIR=%s\n' "$target"
    printf 'ODIRAG_JOURNAL_ORIGINAL_CURRENT=%s\n' "$original_current"
    printf 'ODIRAG_JOURNAL_ORIGINAL_PREVIOUS=%s\n' "$original_previous"
    printf 'ODIRAG_JOURNAL_BACKEND_REF=%s\n' "$backend_ref"
    printf 'ODIRAG_JOURNAL_FRONTEND_REF=%s\n' "$frontend_ref"
    printf 'ODIRAG_JOURNAL_BACKEND_IMAGE_ID=%s\n' "$backend_id"
    printf 'ODIRAG_JOURNAL_FRONTEND_IMAGE_ID=%s\n' "$frontend_id"
    printf 'ODIRAG_JOURNAL_LEGACY_COMPOSE=%s\n' "$legacy_compose"
    printf 'ODIRAG_JOURNAL_LEGACY_NGINX=%s\n' "$legacy_nginx"
    printf 'ODIRAG_JOURNAL_LEGACY_COMPOSE_SHA256=%s\n' "$legacy_compose_sha"
    printf 'ODIRAG_JOURNAL_LEGACY_NGINX_SHA256=%s\n' "$legacy_nginx_sha"
    printf 'ODIRAG_JOURNAL_LEGACY_ALEMBIC_HEAD=%s\n' "$legacy_alembic_head"
    printf 'ODIRAG_JOURNAL_TARGET_STATE_EXISTED=%s\n' "$state_existed"
    printf 'ODIRAG_JOURNAL_TARGET_STATE_BACKUP=%s\n' "$state_backup"
    printf 'ODIRAG_JOURNAL_TARGET_STATE_SHA256=%s\n' "$state_sha"
  } >"$temporary" || return 1
  chmod 0600 "$temporary" || return 1
  mv -Tf -- "$temporary" "$ODIRAG_RELEASE_JOURNAL"
}

load_release_journal() {
  local unexpected previous
  validate_file_permissions "$ODIRAG_RELEASE_JOURNAL" || return 1
  [[ "$(stat -c '%u' -- "$ODIRAG_RELEASE_JOURNAL")" == "0" \
      && "$(stat -c '%a' -- "$ODIRAG_RELEASE_JOURNAL")" == "600" ]] \
    || { release_die "release journal ownership or mode is unsafe"; return 1; }
  unexpected="$(grep -Ev '^(ODIRAG_JOURNAL_(VERSION|MODE|TARGET_DIR|ORIGINAL_CURRENT|ORIGINAL_PREVIOUS|BACKEND_REF|FRONTEND_REF|BACKEND_IMAGE_ID|FRONTEND_IMAGE_ID|LEGACY_COMPOSE|LEGACY_NGINX|LEGACY_COMPOSE_SHA256|LEGACY_NGINX_SHA256|LEGACY_ALEMBIC_HEAD|TARGET_STATE_EXISTED|TARGET_STATE_BACKUP|TARGET_STATE_SHA256))=[^[:space:]]+$' "$ODIRAG_RELEASE_JOURNAL" || true)"
  [[ -z "$unexpected" ]] || { release_die "release journal contains unexpected data"; return 1; }
  [[ "$(release_journal_value ODIRAG_JOURNAL_VERSION)" == "1" ]] \
    || { release_die "unsupported release journal version"; return 1; }
  JOURNAL_MODE="$(release_journal_value ODIRAG_JOURNAL_MODE)"
  [[ "$JOURNAL_MODE" == "release" || "$JOURNAL_MODE" == "legacy-bootstrap" ]] \
    || { release_die "invalid release journal mode"; return 1; }
  JOURNAL_TARGET_DIR="$(resolve_release_dir "$(release_journal_value ODIRAG_JOURNAL_TARGET_DIR)")" || return 1
  JOURNAL_ORIGINAL_CURRENT="$(resolve_release_dir "$(release_journal_value ODIRAG_JOURNAL_ORIGINAL_CURRENT)")" || return 1
  previous="$(release_journal_value ODIRAG_JOURNAL_ORIGINAL_PREVIOUS)"
  if [[ "$previous" == "NONE" ]]; then
    JOURNAL_ORIGINAL_PREVIOUS=""
  else
    JOURNAL_ORIGINAL_PREVIOUS="$(resolve_release_dir "$previous")" || return 1
  fi
  JOURNAL_BACKEND_REF="$(release_journal_value ODIRAG_JOURNAL_BACKEND_REF)"
  JOURNAL_FRONTEND_REF="$(release_journal_value ODIRAG_JOURNAL_FRONTEND_REF)"
  JOURNAL_BACKEND_IMAGE_ID="$(release_journal_value ODIRAG_JOURNAL_BACKEND_IMAGE_ID)"
  JOURNAL_FRONTEND_IMAGE_ID="$(release_journal_value ODIRAG_JOURNAL_FRONTEND_IMAGE_ID)"
  [[ "$JOURNAL_BACKEND_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ \
      && "$JOURNAL_FRONTEND_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || { release_die "invalid release journal image ID"; return 1; }
  JOURNAL_LEGACY_COMPOSE="$(release_journal_value ODIRAG_JOURNAL_LEGACY_COMPOSE)"
  JOURNAL_LEGACY_NGINX="$(release_journal_value ODIRAG_JOURNAL_LEGACY_NGINX)"
  JOURNAL_LEGACY_COMPOSE_SHA="$(release_journal_value ODIRAG_JOURNAL_LEGACY_COMPOSE_SHA256)"
  JOURNAL_LEGACY_NGINX_SHA="$(release_journal_value ODIRAG_JOURNAL_LEGACY_NGINX_SHA256)"
  JOURNAL_LEGACY_ALEMBIC_HEAD="$(release_journal_value ODIRAG_JOURNAL_LEGACY_ALEMBIC_HEAD)"
  JOURNAL_TARGET_STATE_EXISTED="$(release_journal_value ODIRAG_JOURNAL_TARGET_STATE_EXISTED)"
  JOURNAL_TARGET_STATE_BACKUP="$(release_journal_value ODIRAG_JOURNAL_TARGET_STATE_BACKUP)"
  JOURNAL_TARGET_STATE_SHA="$(release_journal_value ODIRAG_JOURNAL_TARGET_STATE_SHA256)"
  [[ "$JOURNAL_TARGET_STATE_EXISTED" == "true" || "$JOURNAL_TARGET_STATE_EXISTED" == "false" ]] \
    || { release_die "invalid candidate state journal flag"; return 1; }
  if [[ "$JOURNAL_TARGET_STATE_EXISTED" == "true" ]]; then
    [[ "$JOURNAL_TARGET_STATE_BACKUP" == "$JOURNAL_TARGET_DIR/.deployment-state.json.pretransaction" ]] \
      || { release_die "invalid candidate state backup path"; return 1; }
    [[ "$JOURNAL_TARGET_STATE_SHA" =~ ^[0-9a-f]{64}$ ]] \
      || { release_die "invalid candidate state checksum"; return 1; }
  else
    [[ "$JOURNAL_TARGET_STATE_BACKUP" == "NONE" && "$JOURNAL_TARGET_STATE_SHA" == "NONE" ]] \
      || { release_die "unexpected candidate state backup path"; return 1; }
  fi
  if [[ "$JOURNAL_MODE" == "release" ]]; then
    [[ "$JOURNAL_BACKEND_REF" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ \
        && "$JOURNAL_FRONTEND_REF" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] \
      || { release_die "invalid release journal GHCR reference"; return 1; }
    [[ "$JOURNAL_LEGACY_COMPOSE" == "-" && "$JOURNAL_LEGACY_NGINX" == "-" \
        && "$JOURNAL_LEGACY_COMPOSE_SHA" == "-" && "$JOURNAL_LEGACY_NGINX_SHA" == "-" \
        && "$JOURNAL_LEGACY_ALEMBIC_HEAD" == "-" ]] \
      || { release_die "normal release journal contains legacy state"; return 1; }
  else
    [[ "$JOURNAL_BACKEND_REF" =~ ^odirag/backend@sha256:[0-9a-f]{64}$ \
        && "$JOURNAL_FRONTEND_REF" =~ ^odirag/frontend@sha256:[0-9a-f]{64}$ ]] \
      || { release_die "invalid legacy release journal reference"; return 1; }
    [[ "$JOURNAL_LEGACY_COMPOSE" == "$JOURNAL_ORIGINAL_CURRENT/deploy/production/compose.yml" \
        && "$JOURNAL_LEGACY_NGINX" == "$JOURNAL_ORIGINAL_CURRENT/deploy/production/nginx.conf" \
        && "$JOURNAL_LEGACY_COMPOSE_SHA" =~ ^[0-9a-f]{64}$ \
        && "$JOURNAL_LEGACY_NGINX_SHA" =~ ^[0-9a-f]{64}$ \
        && "$JOURNAL_LEGACY_ALEMBIC_HEAD" =~ ^[0-9a-z_]+$ ]] \
      || { release_die "invalid legacy release journal state"; return 1; }
  fi
}

clear_release_journal() {
  if [[ ! -e "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" ]]; then
    return 0
  fi
  [[ -f "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" ]] \
    || { release_die "refusing to remove an invalid release journal"; return 1; }
  rm -f -- "$ODIRAG_RELEASE_JOURNAL"
}

prepare_candidate_state_backup() {
  local target="$1" state backup temporary expected_sha
  state="$target/deployment-state.json"
  backup="$target/.deployment-state.json.pretransaction"
  temporary="$target/.deployment-state.json.pretransaction.tmp"
  [[ ! -e "$backup" && ! -L "$backup" ]] \
    || { release_die "candidate state backup already exists"; return 1; }
  [[ ! -e "$temporary" && ! -L "$temporary" ]] \
    || { release_die "temporary candidate state backup already exists"; return 1; }
  if [[ "${JOURNAL_TARGET_STATE_EXISTED:-false}" != "true" ]]; then
    return 0
  fi
  validate_file_permissions "$state" || return 1
  expected_sha="$(sha256sum "$state" | awk '{print $1}')" || return 1
  [[ "$expected_sha" == "$JOURNAL_TARGET_STATE_SHA" ]] \
    || { release_die "candidate state changed before backup"; return 1; }
  cp -p -- "$state" "$temporary" || return 1
  validate_sha256_file "$temporary" "$JOURNAL_TARGET_STATE_SHA" || return 1
  mv -Tf -- "$temporary" "$backup"
}

clear_orphan_candidate_state_backup() {
  local target="$1" backup path
  backup="$target/.deployment-state.json.pretransaction"
  for path in "$backup" "$target/.deployment-state.json.pretransaction.tmp"; do
    if [[ ! -e "$path" && ! -L "$path" ]]; then
      continue
    fi
    [[ ! -e "$ODIRAG_RELEASE_JOURNAL" && ! -L "$ODIRAG_RELEASE_JOURNAL" ]] \
      || { release_die "candidate state backup belongs to an unfinished transaction"; return 1; }
    [[ -f "$path" && ! -L "$path" ]] \
      || { release_die "invalid orphan candidate state backup"; return 1; }
    rm -f -- "$path" || return 1
  done
}

restore_candidate_state_from_journal() {
  local state backup temporary current_sha
  state="$JOURNAL_TARGET_DIR/deployment-state.json"
  temporary="$JOURNAL_TARGET_DIR/.deployment-state.json.pretransaction.tmp"
  if [[ "$JOURNAL_TARGET_STATE_EXISTED" == "true" ]]; then
    backup="$JOURNAL_TARGET_STATE_BACKUP"
    if [[ -e "$backup" || -L "$backup" ]]; then
      validate_sha256_file "$backup" "$JOURNAL_TARGET_STATE_SHA" || return 1
      mv -Tf -- "$backup" "$state" || return 1
    else
      validate_file_permissions "$state" || return 1
      current_sha="$(sha256sum "$state" | awk '{print $1}')" || return 1
      [[ "$current_sha" == "$JOURNAL_TARGET_STATE_SHA" ]] \
        || { release_die "candidate state backup is missing after state changed"; return 1; }
    fi
    if [[ -e "$temporary" || -L "$temporary" ]]; then
      [[ -f "$temporary" && ! -L "$temporary" ]] \
        || { release_die "invalid temporary candidate state backup"; return 1; }
      rm -f -- "$temporary" || return 1
    fi
    return 0
  fi
  if [[ -e "$state" || -L "$state" ]]; then
    [[ -f "$state" && ! -L "$state" ]] \
      || { release_die "refusing to remove an invalid candidate state"; return 1; }
    rm -f -- "$state" || return 1
  fi
}

discard_candidate_state_backup() {
  local backup temporary
  [[ "${JOURNAL_TARGET_STATE_EXISTED:-false}" == "true" ]] || return 0
  backup="$JOURNAL_TARGET_STATE_BACKUP"
  temporary="$JOURNAL_TARGET_DIR/.deployment-state.json.pretransaction.tmp"
  if [[ -e "$backup" || -L "$backup" ]]; then
    [[ -f "$backup" && ! -L "$backup" ]] \
      || { release_die "refusing to remove an invalid candidate state backup"; return 1; }
    rm -f -- "$backup"
  fi
  if [[ -e "$temporary" || -L "$temporary" ]]; then
    [[ -f "$temporary" && ! -L "$temporary" ]] \
      || { release_die "refusing to remove an invalid temporary state backup"; return 1; }
    rm -f -- "$temporary"
  fi
}

atomic_set_release_link() {
  local link="$1" target="$2" temporary
  temporary="${link}.tmp.$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || { release_die "temporary release pointer already exists"; return 1; }
  ln -s -- "$target" "$temporary" || return 1
  if ! mv -Tf -- "$temporary" "$link"; then
    unlink -- "$temporary" >/dev/null 2>&1 || true
    return 1
  fi
}

atomic_clear_release_link() {
  local link="$1"
  if [[ ! -e "$link" && ! -L "$link" ]]; then
    return 0
  fi
  [[ -L "$link" ]] || { release_die "refusing to remove a non-symlink release pointer"; return 1; }
  unlink -- "$link"
}

set_or_clear_release_link() {
  local link="$1" target="$2"
  if [[ -n "$target" ]]; then
    atomic_set_release_link "$link" "$target"
  else
    atomic_clear_release_link "$link"
  fi
}

promote_release_links() {
  local target="$1" old="$2"
  set_or_clear_release_link "$ODIRAG_PREVIOUS_LINK" "$old" || return 1
  atomic_set_release_link "$ODIRAG_CURRENT_LINK" "$target"
}

restore_release_links() {
  local original_current="$1" original_previous="$2"
  set_or_clear_release_link "$ODIRAG_PREVIOUS_LINK" "$original_previous" || return 1
  set_or_clear_release_link "$ODIRAG_CURRENT_LINK" "$original_current"
}

prepare_release_state() {
  local target="$1" previous="$2" mode="$3" duration="$4" state
  state="$target/.deployment-state.json.pending.$$"
  [[ ! -e "$state" && ! -L "$state" ]] || { release_die "pending deployment state already exists"; return 1; }
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
    "schema_version": 2,
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
    "data_integrity_verified": True,
    "providers_verified": True,
    "verified_at": datetime.now(UTC).isoformat(),
}
with open(path, "x", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.chmod(path, 0o444)
PY
  printf '%s\n' "$state"
}

validate_release_state() {
  local state="$RELEASE_DIR/deployment-state.json" mode owner
  validate_file_permissions "$state" || return 1
  mode="$(stat -c '%a' -- "$state")" || return 1
  owner="$(stat -c '%u' -- "$state")" || return 1
  [[ "$owner" == "0" && "$mode" == "444" ]] \
    || { release_die "deployment state ownership or mode is invalid"; return 1; }
  python3 - "$state" "$RELEASE_ID" "$RELEASE_COMMIT" "$RELEASE_BACKEND_REF" \
    "$RELEASE_FRONTEND_REF" "$RELEASE_BACKEND_IMAGE_ID" "$RELEASE_FRONTEND_IMAGE_ID" \
    "$RELEASE_ALEMBIC_HEAD" "$RELEASE_COMPOSE_SHA" "$RELEASE_BUILD_CREATED" <<'PY'
import json
import sys
from datetime import datetime

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
) = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)
expected = {
    "schema_version": 2,
    "release_id": release_id,
    "source_commit": commit,
    "backend_image_ref": backend_ref,
    "frontend_image_ref": frontend_ref,
    "backend_image_id": backend_id,
    "frontend_image_id": frontend_id,
    "alembic_head": alembic_head,
    "compose_sha256": compose_sha,
    "build_created": build_created,
    "data_integrity_verified": True,
    "providers_verified": True,
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit("deployment state identity mismatch")
if payload.get("operation") not in {"deploy", "rollback"}:
    raise SystemExit("invalid deployment state operation")
if not isinstance(payload.get("duration_seconds"), (int, float)) or payload["duration_seconds"] < 0:
    raise SystemExit("invalid deployment duration")
if payload.get("previous_release") is not None and not isinstance(payload["previous_release"], str):
    raise SystemExit("invalid previous release")
datetime.fromisoformat(payload["verified_at"].replace("Z", "+00:00"))
PY
}

validate_pending_state_path() {
  local target="$1" pending="$2"
  case "$pending" in
    "$target"/.deployment-state.json.pending.*) ;;
    *) release_die "pending deployment state is outside the target release" ;;
  esac
}

commit_release_state() {
  local target="$1" pending="$2"
  validate_pending_state_path "$target" "$pending" || return 1
  validate_file_permissions "$pending" || return 1
  mv -Tf -- "$pending" "$target/deployment-state.json"
}

discard_release_state() {
  local target="$1" pending="$2"
  [[ -n "$pending" ]] || return 0
  validate_pending_state_path "$target" "$pending" || return 1
  if [[ -e "$pending" && ! -L "$pending" ]]; then
    rm -f -- "$pending"
  fi
}

acquire_release_lock() {
  require_release_command flock
  exec 9>"$ODIRAG_RELEASE_LOCK"
  flock -n 9 || release_die "another release operation holds the deployment lock"
}

release_preflight() {
  local command
  for command in awk cp curl docker flock grep ln mv python3 realpath rm sha256sum stat unlink; do
    require_release_command "$command" || return 1
  done
  docker compose version >/dev/null
  [[ "$(id -u)" == "0" ]] || { release_die "release operations must run as root"; return 1; }
  validate_directory_permissions "$(dirname -- "$ODIRAG_RELEASE_ROOT")" || return 1
  validate_directory_permissions "$ODIRAG_RELEASE_ROOT" || return 1
  [[ "$(dirname -- "$ODIRAG_RELEASE_JOURNAL")" == "$(dirname -- "$ODIRAG_RELEASE_ROOT")" ]] \
    || { release_die "release journal must be stored beside the release root"; return 1; }
}
