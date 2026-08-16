#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout

container="${BACKEND_CONTAINER:-odirag-prod-backend-1}"
qdrant_container="${QDRANT_CONTAINER:-odirag-prod-qdrant-1}"
collection="${ODIRAG_QDRANT_COLLECTION:-odirag_chunks_bailian_v4}"
[[ "$collection" == "odirag_chunks_bailian_v4" ]] || die "snapshot target must be the active Bailian collection"
assert_production_container "$container"
assert_production_container "$qdrant_container"

backup_id="$(new_backup_id)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
version="$(docker inspect -f '{{.Config.Image}}' "$qdrant_container")"
info="$(docker exec "$container" python -c 'import httpx; d=httpx.get("http://qdrant:6333/collections/odirag_chunks_bailian_v4", timeout=20).json()["result"]; v=d["config"]["params"]["vectors"]; print("{}|{}|{}|{}".format(d["status"], d["points_count"], v["size"], v["distance"]))')"
IFS='|' read -r status points dimensions distance <<< "$info"
[[ "$status" == "green" && "$points" == "821" && "$dimensions" == "1536" && "$distance" == "Cosine" ]] || die "active Qdrant invariant mismatch: $info"

snapshot_name="$(docker exec "$container" python -c 'import httpx; d=httpx.post("http://qdrant:6333/collections/odirag_chunks_bailian_v4/snapshots", timeout=180).json(); print(d["result"]["name"])')"
case "$snapshot_name" in
  *.snapshot) ;;
  *) die "unexpected Qdrant snapshot name" ;;
esac

artifact="$BACKUP_ROOT/qdrant/qdrant-$collection-$backup_id.snapshot"
docker cp "$qdrant_container:/qdrant/snapshots/$collection/$snapshot_name" "$artifact.partial"
test -s "$artifact.partial" || die "Qdrant snapshot is empty"
mv -f "$artifact.partial" "$artifact"
chmod 0640 "$artifact"
metadata="$BACKUP_ROOT/qdrant/qdrant-$collection-$backup_id.txt"
cat > "$metadata" <<EOF
backup_id=$backup_id
timestamp=$timestamp
collection=$collection
snapshot_name=$snapshot_name
status=$status
points=$points
dimensions=$dimensions
distance=$distance
qdrant_image=$version
artifact=$artifact
EOF
chmod 0640 "$metadata"
record_manifest "$backup_id" "$timestamp" "qdrant_snapshot" "$collection" "$artifact" "$version" "restore-qdrant.sh" "daily-7"
printf 'qdrant_snapshot=PASS-LIVE collection=%s points=%s\n' "$collection" "$points"
