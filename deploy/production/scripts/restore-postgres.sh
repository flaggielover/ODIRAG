#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

usage() {
  printf 'usage: %s /var/backups/odirag/postgres/logical/postgres-logical-*.dump\n' "$0" >&2
  exit 2
}

artifact="${1:-}"
[[ -n "$artifact" && -f "$artifact" ]] || usage
[[ "$artifact" == "$BACKUP_ROOT/postgres/logical/"* ]] || die "restore artifact must be under the backup root"
[[ "$artifact" != *.partial ]] || die "refusing partial artifact"

docker image inspect postgres:16-alpine >/dev/null
restore_id="$(new_backup_id)"
container="odirag-dr-postgres-$restore_id"
volume="odirag-dr-postgres-vol-$restore_id"
temp_password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"

cleanup() {
  set +e
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

docker volume create "$volume" >/dev/null
docker run -d --name "$container" --network none \
  -e POSTGRES_DB=odirag_restore \
  -e POSTGRES_USER=odirag_restore \
  -e POSTGRES_PASSWORD="$temp_password" \
  -v "$volume:/var/lib/postgresql/data" \
  postgres:16-alpine >/dev/null

for _ in $(seq 1 90); do
  docker exec "$container" pg_isready -U odirag_restore -d odirag_restore >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$container" pg_isready -U odirag_restore -d odirag_restore >/dev/null

restore_start="$(date +%s%3N)"
docker cp "$artifact" "$container:/tmp/restore.dump" >/dev/null
docker exec "$container" pg_restore -U odirag_restore -d odirag_restore --no-owner --no-privileges --exit-on-error /tmp/restore.dump
checks="$(docker exec "$container" psql -U odirag_restore -d odirag_restore -Atc "SELECT (SELECT count(*) FROM documents),(SELECT count(*) FROM chunks),(SELECT count(*) FROM chunks c LEFT JOIN documents d ON d.id=c.document_id WHERE d.id IS NULL),(SELECT count(*) FROM (SELECT document_id,chunk_index FROM chunks GROUP BY document_id,chunk_index HAVING count(*) > 1) duplicate_pairs),(SELECT count(*) FROM alembic_version)")"
restore_end="$(date +%s%3N)"
IFS='|' read -r documents chunks orphan_chunks duplicate_pairs alembic_rows <<< "$checks"
[[ "$documents" == "182" && "$chunks" == "821" && "$orphan_chunks" == "0" && "$duplicate_pairs" == "0" && "$alembic_rows" == "1" ]] || die "restore integrity mismatch: $checks"
chunk_ids_sha256="$(docker exec "$container" psql -U odirag_restore -d odirag_restore -Atc "SELECT chunk_id FROM chunks ORDER BY chunk_id" | sha256sum | awk '{print $1}')"
printf 'postgres_restore=PASS-LIVE documents=%s chunks=%s orphan_chunks=%s duplicate_pairs=%s alembic_rows=%s chunk_ids_sha256=%s rto_ms=%s\n' "$documents" "$chunks" "$orphan_chunks" "$duplicate_pairs" "$alembic_rows" "$chunk_ids_sha256" "$((restore_end-restore_start))"
