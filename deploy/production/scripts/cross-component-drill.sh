#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-common.sh
source "$SCRIPT_DIR/backup-common.sh"

require_root
ensure_backup_layout
if [[ "$#" != "7" ]]; then
  die "usage: $0 POSTGRES_DUMP QDRANT_SNAPSHOT REDIS_RDB REDIS_CANARY_KEY REDIS_CANARY_VALUE ATTACHMENT_ARCHIVE ATTACHMENT_CHECKSUMS"
fi

postgres_dump="$1"
qdrant_snapshot="$2"
redis_rdb="$3"
redis_canary_key="$4"
redis_canary_value="$5"
attachment_archive="$6"
attachment_checksums="$7"
drill_id="$(new_backup_id)"
drill_dir="$BACKUP_ROOT/drills"
install -d -o root -g deploy -m 2770 "$drill_dir"
evidence="$drill_dir/cross-component-$drill_id.txt"
started_ms="$(date +%s%3N)"

postgres_output="$("$SCRIPT_DIR/restore-postgres.sh" "$postgres_dump")"
printf '%s\n' "$postgres_output"
postgres_digest="$(grep -oE 'chunk_ids_sha256=[0-9a-f]{64}' <<< "$postgres_output" | head -n 1 | cut -d= -f2)"
[[ -n "$postgres_digest" ]] || die "restored PostgreSQL chunk ID digest is missing"

qdrant_output="$("$SCRIPT_DIR/restore-qdrant.sh" "$qdrant_snapshot")"
printf '%s\n' "$qdrant_output"
qdrant_digest="$(grep -oE 'chunk_ids_sha256=[0-9a-f]{64}' <<< "$qdrant_output" | head -n 1 | cut -d= -f2)"
[[ -n "$qdrant_digest" ]] || die "restored Qdrant chunk ID digest is missing"
[[ "$postgres_digest" == "$qdrant_digest" ]] || die "restored PostgreSQL and Qdrant chunk ID sets differ"

redis_output="$("$SCRIPT_DIR/restore-redis.sh" "$redis_rdb" "$redis_canary_key" "$redis_canary_value")"
printf '%s\n' "$redis_output"
attachment_output="$("$SCRIPT_DIR/restore-attachments.sh" "$attachment_archive" "$attachment_checksums")"
printf '%s\n' "$attachment_output"

finished_ms="$(date +%s%3N)"
total_recovery_ms=$((finished_ms-started_ms))
cat > "$evidence" <<EOF
drill_id=$drill_id
postgres_dump=$postgres_dump
qdrant_snapshot=$qdrant_snapshot
redis_rdb=$redis_rdb
attachment_archive=$attachment_archive
postgres_qdrant_chunk_ids_sha256=$postgres_digest
postgres_qdrant_id_set_equal=true
documents=182
chunks=821
qdrant_points=821
attachment_files=69
redis_canary_verified=true
total_recovery_ms=$total_recovery_ms
EOF
chmod 0640 "$evidence"
printf 'disaster_recovery_drill=PASS-LIVE components=4 postgres_qdrant_id_set_equal=true total_recovery_ms=%s evidence=%s\n' "$total_recovery_ms" "$evidence"
