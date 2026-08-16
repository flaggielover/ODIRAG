#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout
container="${BACKEND_CONTAINER:-odirag-prod-backend-1}"
assert_production_container "$container"
docker inspect "$container" >/dev/null
backup_id="$(new_backup_id)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
artifact="$BACKUP_ROOT/attachments/attachments-$backup_id.tar.gz"
checksums="$BACKUP_ROOT/attachments/attachments-$backup_id.sha256"

docker exec "$container" sh -lc 'cd /app/data && tar -czf - attachments' > "$artifact.partial"
test -s "$artifact.partial" || die "attachment archive is empty"
mv -f "$artifact.partial" "$artifact"
docker exec "$container" sh -lc 'cd /app/data && find attachments -type f -print0 | sort -z | xargs -0 sha256sum' > "$checksums.partial"
test -s "$checksums.partial" || die "attachment checksum manifest is empty"
mv -f "$checksums.partial" "$checksums"
chmod 0640 "$artifact" "$checksums"
count="$(wc -l < "$checksums" | tr -d ' ' )"
[[ "$count" == "69" ]] || die "attachment file count mismatch: $count"
record_manifest "$backup_id" "$timestamp" "attachment_bytes" "$container:/app/data/attachments" "$artifact" "backend-runtime" "restore-attachments.sh" "weekly-4"
printf 'attachment_backup=PASS-LIVE files=%s checksum_manifest=%s\n' "$count" "$checksums"
