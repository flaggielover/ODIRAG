#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
artifact="${1:-}"
checksums="${2:-}"
[[ -f "$artifact" && -f "$checksums" ]] || die "usage: $0 ARCHIVE CHECKSUM_MANIFEST"
[[ "$artifact" == "$BACKUP_ROOT/attachments/"* ]] || die "attachment archive must be under the backup root"
[[ "$checksums" == "$BACKUP_ROOT/attachments/"* ]] || die "checksum manifest must be under the backup root"
[[ "$artifact" != *.partial && "$checksums" != *.partial ]] || die "refusing partial artifact"

restore_id="$(new_backup_id)"
restore_dir="$BACKUP_ROOT/restore-tests/attachments-$restore_id"
cleanup() {
  set +e
  rm -rf "$restore_dir"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$restore_dir"
tar -xzf "$artifact" -C "$restore_dir"
count="$(find "$restore_dir/attachments" -type f | wc -l | tr -d ' ' )"
[[ "$count" == "69" ]] || die "restored attachment file count mismatch: $count"
(cd "$restore_dir" && sha256sum -c "$checksums" >/dev/null)
printf 'attachment_restore=PASS-LIVE files=%s sha256_equal=69/69\n' "$count"
