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
artifact="$BACKUP_ROOT/postgres/logical/postgres-logical-$backup_id.dump"
temporary="$artifact.partial"
metadata="$BACKUP_ROOT/postgres/logical/postgres-logical-$backup_id.txt"

db_name="$(docker exec "$container" sh -lc 'printf %s "$POSTGRES_DB"')"
db_user="$(docker exec "$container" sh -lc 'printf %s "$POSTGRES_USER"')"
version="$(docker exec "$container" postgres --version | tr -s ' ' | sed 's/[[:space:]]*$//')"
[[ "$db_name" != *$'\n'* && "$db_user" != *$'\n'* ]] || die "unexpected database metadata"

trap 'rm -f "$temporary"' EXIT HUP INT TERM
docker exec "$container" sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' > "$temporary"
test -s "$temporary" || die "logical dump is empty"
docker run --rm --network none -v "$temporary:/backup.dump:ro" \
  postgres:16-alpine pg_restore --list /backup.dump >/dev/null
mv -f "$temporary" "$artifact"
trap - EXIT HUP INT TERM
chmod 0640 "$artifact"

cat > "$metadata" <<EOF
backup_id=$backup_id
timestamp=$timestamp
component=postgresql_logical
postgres_version=$version
database=$db_name
database_user=$db_user
artifact=$artifact
EOF
chmod 0640 "$metadata"
record_manifest "$backup_id" "$timestamp" "postgresql_logical" "$container/$db_name" "$artifact" "$version" "restore-postgres.sh" "daily-7"
printf 'logical_backup=PASS-LIVE database=%s\n' "$db_name"
