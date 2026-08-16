#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout

base_artifact="${1:-}"
[[ -f "$base_artifact" ]] || die "usage: $0 /var/backups/odirag/postgres/base/postgres-base-*.tar.gz"
[[ "$base_artifact" == "$BACKUP_ROOT/postgres/base/"* ]] || die "base artifact must be under the backup root"
[[ "$base_artifact" != *.partial ]] || die "refusing partial artifact"

container="${POSTGRES_CONTAINER:-odirag-prod-postgres-1}"
assert_production_container "$container"
docker inspect "$container" >/dev/null
postgres_user="$(docker exec "$container" printenv POSTGRES_USER)"
postgres_db="$(docker exec "$container" printenv POSTGRES_DB)"
[[ -n "$postgres_user" && -n "$postgres_db" ]] || die "production PostgreSQL identity is unavailable"

drill_id="$(new_backup_id)"
target_name="odirag_dr_${drill_id}_t2"
restore_dir="$BACKUP_ROOT/restore-tests/pitr-$drill_id"
pitr_container="odirag-dr-pitr-$drill_id"
evidence="$BACKUP_ROOT/postgres/pitr/pitr-$drill_id.txt"
canary_created=0
archive_dir="$BACKUP_ROOT/postgres/wal"
before_count="$(find "$archive_dir" -maxdepth 1 -type f -name '*.gz' | wc -l)"

cleanup() {
  set +e
  docker rm -f "$pitr_container" >/dev/null 2>&1 || true
  if [[ "$canary_created" == "1" ]]; then
    docker exec "$container" psql -U "$postgres_user" -d "$postgres_db" -c 'DROP SCHEMA IF EXISTS dr_canary CASCADE' >/dev/null 2>&1 || true
  fi
  rm -rf "$restore_dir"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$restore_dir/data"
tar -xzf "$base_artifact" -C "$restore_dir/data"
pg_uid="$(docker exec "$container" id -u postgres)"
pg_gid="$(docker exec "$container" id -g postgres)"
chown -R "$pg_uid:$pg_gid" "$restore_dir/data"

docker exec "$container" psql -U "$postgres_user" -d "$postgres_db" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS dr_canary CASCADE; CREATE SCHEMA dr_canary; CREATE TABLE dr_canary.events (event text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now()); INSERT INTO dr_canary.events(event) VALUES ('A');" >/dev/null
canary_created=1
docker exec "$container" psql -U "$postgres_user" -d "$postgres_db" -c 'SELECT pg_switch_wal()' >/dev/null
sleep 2
t2_epoch="$(date +%s)"
docker exec "$container" psql -U "$postgres_user" -d "$postgres_db" -v ON_ERROR_STOP=1 -c "INSERT INTO dr_canary.events(event) VALUES ('B');" >/dev/null
docker exec "$container" psql -U "$postgres_user" -d "$postgres_db" -v ON_ERROR_STOP=1 -c "SELECT pg_create_restore_point('$target_name');" >/dev/null
sleep 1
t3_epoch="$(date +%s)"
docker exec "$container" psql -U "$postgres_user" -d "$postgres_db" -v ON_ERROR_STOP=1 -c "INSERT INTO dr_canary.events(event) VALUES ('C'); SELECT pg_switch_wal();" >/dev/null

for _ in $(seq 1 90); do
  current_count="$(find "$archive_dir" -maxdepth 1 -type f -name '*.gz' | wc -l)"
  [[ "$current_count" -gt "$before_count" ]] && break
  sleep 2
done
current_count="$(find "$archive_dir" -maxdepth 1 -type f -name '*.gz' | wc -l)"
[[ "$current_count" -gt "$before_count" ]] || die "WAL archive did not advance after canary writes"

cat > "$restore_dir/data/postgresql.auto.conf" <<EOF
restore_command = 'gzip -cd /var/backups/odirag/postgres/wal/%f.gz > %p'
recovery_target_name = '$target_name'
recovery_target_action = 'promote'
EOF
touch "$restore_dir/data/recovery.signal"
chown "$pg_uid:$pg_gid" "$restore_dir/data/postgresql.auto.conf" "$restore_dir/data/recovery.signal"

rto_start="$(date +%s%3N)"
docker run -d --name "$pitr_container" --network none \
  -v "$restore_dir/data:/var/lib/postgresql/data" \
  -v "$archive_dir:/var/backups/odirag/postgres/wal:ro" \
  postgres:16-alpine >/dev/null

ready=0
for _ in $(seq 1 120); do
  if docker exec "$pitr_container" pg_isready -U "$postgres_user" -d "$postgres_db" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == "1" ]] || die "isolated PITR instance did not become queryable"

promoted=0
for _ in $(seq 1 180); do
  recovery_state="$(docker exec "$pitr_container" psql -U "$postgres_user" -d "$postgres_db" -Atc 'SELECT pg_is_in_recovery()' 2>/dev/null || true)"
  if [[ "$recovery_state" == "f" ]]; then
    promoted=1
    break
  fi
  sleep 1
done
[[ "$promoted" == "1" ]] || die "isolated PITR instance did not reach the named restore point"

counts="$(docker exec "$pitr_container" psql -U "$postgres_user" -d "$postgres_db" -Atc "SELECT count(*) FILTER (WHERE event='A'),count(*) FILTER (WHERE event='B'),count(*) FILTER (WHERE event='C') FROM dr_canary.events")"
rto_end="$(date +%s%3N)"
IFS='|' read -r count_a count_b count_c <<< "$counts"
[[ "$count_a" == "1" && "$count_b" == "1" && "$count_c" == "0" ]] || die "PITR canary mismatch: $counts"
rto_ms=$((rto_end-rto_start))
rpo_seconds=$((t3_epoch-t2_epoch))

cat > "$evidence" <<EOF
drill_id=$drill_id
base_artifact=$base_artifact
target_restore_point=$target_name
canary=A,B present; C absent
measured_rpo_seconds=$rpo_seconds
measured_rto_ms=$rto_ms
target_rpo_minutes=15
target_rto_minutes=60
EOF
chmod 0640 "$evidence"
printf 'pitr=PASS-LIVE target=%s measured_rpo_seconds=%s measured_rto_ms=%s\n' "$target_name" "$rpo_seconds" "$rto_ms"
