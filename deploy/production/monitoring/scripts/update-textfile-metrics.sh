#!/usr/bin/env bash
set -Eeuo pipefail

TEXTFILE_DIR="${NODE_EXPORTER_TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"
OUTPUT_FILE="$TEXTFILE_DIR/odirag-production.prom"
TEMP_FILE="$OUTPUT_FILE.tmp.$$"
BACKUP_ROOT="${ODIRAG_BACKUP_ROOT:-/var/backups/odirag}"
BACKEND_CONTAINER="${ODIRAG_BACKEND_CONTAINER:-odirag-prod-backend-1}"
POSTGRES_CONTAINER="${ODIRAG_POSTGRES_CONTAINER:-odirag-prod-postgres-1}"

cleanup() {
  rm -f -- "$TEMP_FILE"
}
trap cleanup EXIT

install -d -m 0755 "$TEXTFILE_DIR"

latest_mtime() {
  local path="$1"
  local value
  value="$(find "$path" -type f ! -name '*.partial' -printf '%T@\n' 2>/dev/null | sort -n | tail -n 1 || true)"
  value="${value%%.*}"
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$value"
  else
    printf '0\n'
  fi
}

container_metric() {
  local service="$1"
  local container="odirag-prod-$service-1"
  local state
  state="$(docker inspect --format '{{if .State.Running}}1{{else}}0{{end}}|{{.RestartCount}}' "$container" 2>/dev/null || printf '0|0')"
  printf 'odirag_container_running{stack="application",service="%s"} %s\n' "$service" "${state%%|*}"
  printf 'odirag_container_restarts_total{stack="application",service="%s"} %s\n' "$service" "${state##*|}"
}

qdrant_metrics() {
  local output
  if output="$(docker exec -i "$BACKEND_CONTAINER" python - <<'PY'
import json
import urllib.request

all_healthy = True
for collection in ("odirag_chunks_bailian_v4", "odirag_chunks"):
    try:
        with urllib.request.urlopen(
            f"http://qdrant:6333/collections/{collection}", timeout=5
        ) as response:
            result = json.load(response)["result"]
        status = str(result.get("status", "")).lower()
        points = int(result.get("points_count") or 0)
        exists = 1
        green = int(status == "green")
    except Exception:
        points = 0
        exists = 0
        green = 0
        all_healthy = False
    print(f'odirag_qdrant_collection_exists{{collection="{collection}"}} {exists}')
    print(f'odirag_qdrant_collection_green{{collection="{collection}"}} {green}')
    print(f'odirag_qdrant_collection_points{{collection="{collection}"}} {points}')
print(f'odirag_textfile_collector_success{{collector="qdrant"}} {int(all_healthy)}')
PY
  )"; then
    printf '%s\n' "$output"
  else
    for collection in odirag_chunks_bailian_v4 odirag_chunks; do
      printf 'odirag_qdrant_collection_exists{collection="%s"} 0\n' "$collection"
      printf 'odirag_qdrant_collection_green{collection="%s"} 0\n' "$collection"
      printf 'odirag_qdrant_collection_points{collection="%s"} 0\n' "$collection"
    done
    printf 'odirag_textfile_collector_success{collector="qdrant"} 0\n'
  fi
}

postgres_wal_metrics() {
  local output
  local pending
  if output="$(docker exec -i "$POSTGRES_CONTAINER" psql -v ON_ERROR_STOP=1 -U odirag -d odirag -At -F '|' <<'SQL'
SELECT failed_count, COALESCE(EXTRACT(EPOCH FROM last_archived_time)::bigint, 0)
FROM pg_stat_archiver;
SQL
  )" && [[ "$output" =~ ^[0-9]+\|[0-9]+$ ]] \
    && pending="$(docker exec "$POSTGRES_CONTAINER" sh -c \
      'find "$PGDATA/pg_wal/archive_status" -maxdepth 1 -type f -name "*.ready" -print 2>/dev/null | wc -l')" \
    && [[ "$pending" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$output" | awk -F '|' '{
      printf "odirag_postgres_wal_archive_failed_total %s\n", $1;
      printf "odirag_wal_archive_last_success_timestamp_seconds %s\n", $2;
    }'
    printf 'odirag_postgres_wal_archive_pending_files %s\n' "$pending"
    printf 'odirag_textfile_collector_success{collector="postgres"} 1\n'
  else
    printf 'odirag_textfile_collector_success{collector="postgres"} 0\n'
  fi
}

{
  printf '# HELP odirag_backup_last_success_timestamp_seconds Latest completed backup artifact mtime.\n'
  printf '# TYPE odirag_backup_last_success_timestamp_seconds gauge\n'
  printf 'odirag_backup_last_success_timestamp_seconds{component="postgres_logical"} %s\n' "$(latest_mtime "$BACKUP_ROOT/postgres/logical")"
  printf 'odirag_backup_last_success_timestamp_seconds{component="postgres_base"} %s\n' "$(latest_mtime "$BACKUP_ROOT/postgres/base")"
  printf 'odirag_backup_last_success_timestamp_seconds{component="qdrant"} %s\n' "$(latest_mtime "$BACKUP_ROOT/qdrant")"
  printf 'odirag_backup_last_success_timestamp_seconds{component="redis"} %s\n' "$(latest_mtime "$BACKUP_ROOT/redis")"
  printf 'odirag_backup_last_success_timestamp_seconds{component="attachments"} %s\n' "$(latest_mtime "$BACKUP_ROOT/attachments")"
  printf '# HELP odirag_container_running Whether a fixed production application container is running.\n'
  printf '# TYPE odirag_container_running gauge\n'
  printf '# HELP odirag_container_restarts_total Docker restart count for a fixed production application container.\n'
  printf '# TYPE odirag_container_restarts_total counter\n'
  for service in postgres redis qdrant backend worker scheduler frontend nginx; do
    container_metric "$service"
  done
  printf '# HELP odirag_qdrant_collection_points Point count for an allowlisted production collection.\n'
  printf '# TYPE odirag_qdrant_collection_points gauge\n'
  printf '# HELP odirag_qdrant_collection_green Whether an allowlisted collection reports green.\n'
  printf '# TYPE odirag_qdrant_collection_green gauge\n'
  printf '# HELP odirag_qdrant_collection_exists Whether an allowlisted collection exists.\n'
  printf '# TYPE odirag_qdrant_collection_exists gauge\n'
  printf '# HELP odirag_textfile_collector_success Whether a dependency-specific textfile collector succeeded.\n'
  printf '# TYPE odirag_textfile_collector_success gauge\n'
  qdrant_metrics
  printf '# HELP odirag_postgres_wal_archive_failed_total PostgreSQL archived WAL failure counter.\n'
  printf '# TYPE odirag_postgres_wal_archive_failed_total counter\n'
  printf '# HELP odirag_wal_archive_last_success_timestamp_seconds Last successful PostgreSQL WAL archive time.\n'
  printf '# TYPE odirag_wal_archive_last_success_timestamp_seconds gauge\n'
  printf '# HELP odirag_postgres_wal_archive_pending_files PostgreSQL WAL files currently waiting for archive.\n'
  printf '# TYPE odirag_postgres_wal_archive_pending_files gauge\n'
  postgres_wal_metrics
  printf '# HELP odirag_textfile_last_success_timestamp_seconds Last successful complete textfile publication time.\n'
  printf '# TYPE odirag_textfile_last_success_timestamp_seconds gauge\n'
  printf 'odirag_textfile_last_success_timestamp_seconds %s\n' "$(date +%s)"
} > "$TEMP_FILE"

chmod 0644 "$TEMP_FILE"
mv -f -- "$TEMP_FILE" "$OUTPUT_FILE"
trap - EXIT
