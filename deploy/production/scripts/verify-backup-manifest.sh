#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout
[[ -f "$MANIFEST" ]] || die "manifest is missing"
checked=0
while IFS=$'\t' read -r backup_id timestamp component source artifact size expected_sha version restore retention; do
  [[ "$backup_id" == "backup_id" ]] && continue
  [[ -n "$artifact" ]] || die "manifest row has no artifact"
  [[ -f "$artifact" ]] || die "manifest artifact is missing: $artifact"
  actual_size="$(size_file "$artifact")"
  [[ "$actual_size" == "$size" ]] || die "manifest size mismatch: $artifact"
  actual_sha="$(sha256_file "$artifact")"
  [[ "$actual_sha" == "$expected_sha" ]] || die "manifest sha256 mismatch: $artifact"
  checked=$((checked + 1))
done < "$MANIFEST"
[[ "$checked" -gt "0" ]] || die "manifest has no artifact rows"
printf 'backup_manifest=PASS-LIVE artifacts_verified=%s\n' "$checked"
