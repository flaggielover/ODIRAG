#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/odirag}"
MANIFEST="${MANIFEST:-$BACKUP_ROOT/manifest.tsv}"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [[ "$(id -u)" == "0" ]] || die "run this backup operation with sudo"
}

require_backup_root() {
  [[ "$BACKUP_ROOT" == /var/backups/odirag ]] || die "BACKUP_ROOT must remain /var/backups/odirag"
}

ensure_backup_layout() {
  require_backup_root
  install -d -o root -g deploy -m 2711 \
    "$BACKUP_ROOT" \
    "$BACKUP_ROOT/postgres"
  install -d -o 70 -g 70 -m 2770 \
    "$BACKUP_ROOT/postgres/wal"
  install -d -o root -g deploy -m 2770 \
    "$BACKUP_ROOT/postgres/logical" \
    "$BACKUP_ROOT/postgres/base" \
    "$BACKUP_ROOT/postgres/pitr" \
    "$BACKUP_ROOT/qdrant" \
    "$BACKUP_ROOT/redis" \
    "$BACKUP_ROOT/attachments" \
    "$BACKUP_ROOT/restore-tests"
  if [[ ! -e "$MANIFEST" ]]; then
    printf 'backup_id\ttimestamp\tcomponent\tsource\tartifact\tsize_bytes\tsha256\tsoftware_version\trestore_procedure\tretention_class\n' > "$MANIFEST"
    chown root:deploy "$MANIFEST"
    chmod 0660 "$MANIFEST"
  fi
}

new_backup_id() {
  date -u +%Y%m%dT%H%M%SZ
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

size_file() {
  stat -c '%s' "$1"
}

record_manifest() {
  local backup_id="$1"
  local timestamp="$2"
  local component="$3"
  local source="$4"
  local artifact="$5"
  local version="$6"
  local restore_procedure="$7"
  local retention="$8"
  [[ -f "$artifact" ]] || die "artifact is missing: $artifact"
  local size sha
  size="$(size_file "$artifact")"
  sha="$(sha256_file "$artifact")"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$backup_id" "$timestamp" "$component" "$source" "$artifact" \
    "$size" "$sha" "$version" "$restore_procedure" "$retention" >> "$MANIFEST"
  printf '%s artifact=%s size=%s sha256=%s\n' "$component" "$artifact" "$size" "$sha"
}

assert_production_container() {
  local container="$1"
  case "$container" in
    odirag-prod-postgres-1|odirag-prod-redis-1|odirag-prod-qdrant-1|odirag-prod-backend-1) ;;
    *) die "refusing unknown production container: $container" ;;
  esac
}
