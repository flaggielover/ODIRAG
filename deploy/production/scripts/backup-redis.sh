#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout

container="${REDIS_CONTAINER:-odirag-prod-redis-1}"
assert_production_container "$container"
docker inspect "$container" >/dev/null
backup_id="$(new_backup_id)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
artifact="$BACKUP_ROOT/redis/redis-$backup_id.rdb"
aof_artifact="$BACKUP_ROOT/redis/redis-$backup_id-data.tar.gz"
metadata="$BACKUP_ROOT/redis/redis-$backup_id.txt"
canary_key="odirag:dr:canary:$backup_id"
canary_value="phase2-$backup_id"

docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw SET "$1" "$2" EX 86400' sh "$canary_key" "$canary_value" >/dev/null
cleanup() {
  set +e
  docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli DEL "$1"' sh "$canary_key" >/dev/null 2>&1 || true
  docker exec "$container" rm -f /tmp/odirag-phase2.rdb >/dev/null 2>&1 || true
  rm -f "$artifact.partial" "$aof_artifact.partial"
}
trap cleanup EXIT HUP INT TERM

docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --rdb /tmp/odirag-phase2.rdb >/dev/null'
docker cp "$container:/tmp/odirag-phase2.rdb" "$artifact.partial"
test -s "$artifact.partial" || die "Redis RDB artifact is empty"
mv -f "$artifact.partial" "$artifact"
docker exec "$container" sh -lc 'tar -C /data -czf - .' > "$aof_artifact.partial"
test -s "$aof_artifact.partial" || die "Redis persistence archive is empty"
mv -f "$aof_artifact.partial" "$aof_artifact"
chmod 0640 "$artifact" "$aof_artifact"

version="$(docker exec "$container" redis-server --version | tr -s ' ' | sed 's/[[:space:]]*$//')"
cat > "$metadata" <<EOF
backup_id=$backup_id
timestamp=$timestamp
component=redis
redis_version=$version
canary_key=$canary_key
canary_value=$canary_value
rdb_artifact=$artifact
aof_artifact=$aof_artifact
EOF
chmod 0640 "$metadata"
record_manifest "$backup_id" "$timestamp" "redis_rdb" "$container" "$artifact" "$version" "restore-redis.sh" "daily-3"
record_manifest "$backup_id" "$timestamp" "redis_aof_archive" "$container:/data" "$aof_artifact" "$version" "restore-redis.sh" "daily-3"
printf 'redis_backup=PASS-LIVE canary=%s\n' "$canary_key"
