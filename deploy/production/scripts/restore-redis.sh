#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
artifact="${1:-}"
canary_key="${2:-}"
canary_value="${3:-}"
[[ -f "$artifact" && -n "$canary_key" && -n "$canary_value" ]] || die "usage: $0 RDB_ARTIFACT CANARY_KEY CANARY_VALUE"
[[ "$artifact" == "$BACKUP_ROOT/redis/"* ]] || die "RDB artifact must be under the backup root"
[[ "$artifact" != *.partial ]] || die "refusing partial artifact"

restore_id="$(new_backup_id)"
container="odirag-dr-redis-$restore_id"
volume="odirag-dr-redis-vol-$restore_id"
password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
cleanup() {
  set +e
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

docker volume create "$volume" >/dev/null
docker run -d --name "$container" --network none -e REDIS_PASSWORD="$password" \
  -v "$volume:/data" redis:7-alpine redis-server --appendonly no --requirepass "$password" >/dev/null
for _ in $(seq 1 60); do
  docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping' >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping' >/dev/null
docker stop "$container" >/dev/null
docker cp "$artifact" "$container:/data/dump.rdb"
docker start "$container" >/dev/null
for _ in $(seq 1 60); do
  docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping' >/dev/null 2>&1 && break
  sleep 1
done
value="$(docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw GET "$1"' sh "$canary_key")"
[[ "$value" == "$canary_value" ]] || die "Redis recovery canary mismatch"
dbsize="$(docker exec "$container" sh -lc 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --raw DBSIZE')"
[[ "$dbsize" =~ ^[1-9][0-9]*$ ]] || die "Redis recovery database is empty"
printf 'redis_restore=PASS-LIVE canary_verified=true dbsize=%s\n' "$dbsize"
