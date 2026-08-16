#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout

container="${POSTGRES_CONTAINER:-odirag-prod-postgres-1}"
assert_production_container "$container"
docker inspect "$container" >/dev/null

backup_id="$(new_backup_id)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
partial="$BACKUP_ROOT/postgres/base/$backup_id.partial"
artifact="$BACKUP_ROOT/postgres/base/postgres-base-$backup_id.tar.gz"
metadata="$BACKUP_ROOT/postgres/base/postgres-base-$backup_id.txt"
version="$(docker exec "$container" postgres --version | tr -s ' ' | sed 's/[[:space:]]*$//')"
start="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

install -d -o root -g deploy -m 2770 "$partial"
docker exec -u 0 "$container" sh -lc "rm -rf '$partial'; mkdir -p '$partial'; chown postgres:postgres '$partial'"
docker exec "$container" sh -lc "pg_basebackup -U \"\$POSTGRES_USER\" -D '$partial' --format=plain --wal-method=stream --checkpoint=fast --manifest-checksums=SHA256 --no-password"
docker exec "$container" pg_verifybackup "$partial"
tar -C "$partial" -czf "$artifact.partial" .
mv -f "$artifact.partial" "$artifact"
finish="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
rm -rf "$partial"
chmod 0640 "$artifact"

cat > "$metadata" <<EOF
backup_id=$backup_id
component=postgresql_physical_base
postgres_version=$version
start=$start
finish=$finish
artifact=$artifact
EOF
chmod 0640 "$metadata"
record_manifest "$backup_id" "$timestamp" "postgresql_physical_base" "$container" "$artifact" "$version" "pitr-drill.sh" "weekly-4"
printf 'base_backup=PASS-LIVE artifact=%s\n' "$artifact"
