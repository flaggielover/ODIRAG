#!/bin/sh
set -eu

source_path=${1:?WAL source path is required}
wal_name=${2:?WAL file name is required}
archive_dir=${ODIRAG_WAL_ARCHIVE_DIR:-/var/backups/odirag/postgres/wal}

# Archive WAL segments and pg_basebackup history files, but reject arbitrary names.
printf '%s' "$wal_name" | grep -Eq '^([0-9A-F]{24}|[0-9A-F]{24}\.[0-9A-F]{8}\.backup)$' || exit 1

mkdir -p "$archive_dir"
target="$archive_dir/$wal_name.gz"
if [ -f "$target" ]; then
  exit 0
fi

temporary="$target.tmp.$$"
trap 'rm -f "$temporary"' EXIT HUP INT TERM
gzip -c "$source_path" > "$temporary"
chmod 0640 "$temporary"
mv -f "$temporary" "$target"
trap - EXIT HUP INT TERM
