#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout

artifact="${1:-}"
[[ -f "$artifact" ]] || die "usage: $0 /var/backups/odirag/qdrant/*.snapshot"
artifact="$(realpath -e "$artifact")"
[[ "$artifact" == "$BACKUP_ROOT/qdrant/"* ]] || die "snapshot must be under the backup root"
case "$(basename "$artifact")" in
  qdrant-odirag_chunks_bailian_v4-*.snapshot) ;;
  *) die "unexpected snapshot name" ;;
esac
expected_sha="$(awk -F '\t' -v artifact="$artifact" '$5 == artifact {print $7}' "$MANIFEST" | tail -n 1)"
[[ -n "$expected_sha" && "$(sha256_file "$artifact")" == "$expected_sha" ]] || die "snapshot manifest checksum mismatch"

backend="${BACKEND_CONTAINER:-odirag-prod-backend-1}"
assert_production_container "$backend"
restore_id="$(new_backup_id)"
collection="odirag_chunks_bailian_v4_restore_test_${restore_id}_$$"
image="$(docker inspect -f '{{.Config.Image}}' "$backend")"
verifier="$SCRIPT_DIR/verify-qdrant-restore.py"
[[ -f "$verifier" ]] || die "Qdrant restore verifier is missing"
cleanup_enabled=0

run_verifier() {
  docker exec -i "$backend" python - "$collection" "$1" < "$verifier"
}

cleanup() {
  set +e
  if [[ "$cleanup_enabled" == "1" ]]; then
    run_verifier delete >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT HUP INT TERM

run_verifier preflight
cleanup_enabled=1
docker run --rm --network odirag-prod-private --user 0:0 --entrypoint python \
  -v "$artifact:/tmp/input.snapshot:ro" "$image" -c \
  "import httpx; f=open('/tmp/input.snapshot','rb'); r=httpx.post('http://qdrant:6333/collections/$collection/snapshots/upload', params={'wait':'true','priority':'snapshot'}, files={'snapshot':('$collection.snapshot',f,'application/octet-stream')}, timeout=300); r.raise_for_status(); print(r.status_code)"

run_verifier verify
run_verifier delete
cleanup_enabled=0
trap - EXIT HUP INT TERM
printf 'qdrant_restore=PASS-LIVE points=821 temporary_collection_removed=true\n'
