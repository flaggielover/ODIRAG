#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=release-common.sh
source "$SCRIPT_DIR/release-common.sh"

providers=false
target=""
for argument in "$@"; do
  case "$argument" in
    --providers) providers=true ;;
    --*) release_die "unknown option" ;;
    *) [[ -z "$target" ]] || release_die "only one release directory may be supplied"; target="$argument" ;;
  esac
done

release_preflight
target="${target:-$(realpath -e -- "$ODIRAG_CURRENT_LINK")}"
target="$(resolve_release_dir "$target")"
load_release_manifest "$target"
validate_file_permissions "$ODIRAG_RUNTIME_ENV_FILE"
compose_for_release config --quiet
validate_release_images
validate_release_migration
wait_release_stack 60

postgres_container="$(release_container_id postgres)"
backend_container="$(release_container_id backend)"
counts="$(docker exec "$postgres_container" psql -U odirag -d odirag -Atqc "SELECT (SELECT count(*) FROM documents),(SELECT count(*) FROM chunks),(SELECT count(*) FROM attachments WHERE parse_status='parsed'),(SELECT count(*) FROM (SELECT id FROM chunks GROUP BY id HAVING count(*) > 1) duplicates),(SELECT count(*) FROM (SELECT document_id,chunk_index FROM chunks GROUP BY document_id,chunk_index HAVING count(*) > 1) duplicate_pairs);")"
IFS='|' read -r documents chunks parsed_attachments duplicate_chunks duplicate_pairs <<<"$counts"
[[ "$documents" == "182" && "$chunks" == "821" && "$parsed_attachments" == "60" ]] || release_die "PostgreSQL production counts changed"
[[ "$duplicate_chunks" == "0" && "$duplicate_pairs" == "0" ]] || release_die "PostgreSQL duplicate invariant failed"

attachment_files="$(docker exec "$backend_container" sh -ec 'find /app/data/attachments -type f -print | wc -l')"
[[ "$attachment_files" == "69" ]] || release_die "attachment file count changed"

qdrant="$(docker exec "$backend_container" python -c 'import httpx; r=httpx.get("http://qdrant:6333/collections/odirag_chunks_bailian_v4", timeout=10).json()["result"]; v=r["config"]["params"]["vectors"]; print("{}|{}|{}|{}".format(r["status"], r["points_count"], v["size"], v["distance"]))')"
IFS='|' read -r qdrant_status qdrant_points qdrant_size qdrant_distance <<<"$qdrant"
[[ "$qdrant_status" == "green" && "$qdrant_points" == "821" && "$qdrant_size" == "1536" && "$qdrant_distance" == "Cosine" ]] || release_die "active Qdrant collection invariant failed"

rollback_exists="$(docker exec "$backend_container" python -c 'import httpx; r=httpx.get("http://qdrant:6333/collections/odirag_chunks", timeout=10); print("true" if r.status_code == 200 else "false")')"
[[ "$rollback_exists" == "true" ]] || release_die "rollback Qdrant collection is missing"

if [[ "$providers" == "true" ]]; then
  temporary="/tmp/odirag-verify-production-rag.py"
  trap 'docker exec "$backend_container" rm -f -- "$temporary" >/dev/null 2>&1 || true' EXIT
  docker cp "$target/deploy/production/scripts/verify-production-rag.py" "$backend_container:$temporary" >/dev/null
  docker exec "$backend_container" python "$temporary"
  docker exec "$backend_container" rm -f -- "$temporary"
  trap - EXIT
fi

release_log "release_verification=PASS-LIVE id=$RELEASE_ID documents=$documents chunks=$chunks parsed_attachments=$parsed_attachments attachment_files=$attachment_files qdrant_points=$qdrant_points providers=$providers"
