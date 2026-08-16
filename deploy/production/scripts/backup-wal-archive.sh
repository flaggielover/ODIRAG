#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout
wal_dir="$BACKUP_ROOT/postgres/wal"
bundle_dir="$BACKUP_ROOT/postgres/wal-archives"
install -d -o root -g deploy -m 2770 "$bundle_dir"
backup_id="$(new_backup_id)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
artifact="$bundle_dir/wal-archive-$backup_id.tar.gz"

mapfile -t wal_files < <(find "$wal_dir" -maxdepth 1 -type f -name '*.gz' -printf '%f\n' | sort)
(( ${#wal_files[@]} > 0 )) || die "no archived WAL files found"
tar -C "$wal_dir" -czf "$artifact.partial" -- "${wal_files[@]}"
test -s "$artifact.partial" || die "WAL archive bundle is empty"
mv -f "$artifact.partial" "$artifact"
chmod 0640 "$artifact"
record_manifest "$backup_id" "$timestamp" "postgres_wal_archive" "$wal_dir" "$artifact" "postgres-16" "pitr-drill.sh" "hourly-2"
printf 'wal_archive_bundle=PASS-LIVE files=%s artifact=%s\n' "${#wal_files[@]}" "$artifact"
