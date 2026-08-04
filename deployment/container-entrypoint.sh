#!/bin/sh
set -eu

data_dir="${ODIRAG_DATA_DIR:-/app/data}"
mkdir -p \
    "$data_dir/attachments" \
    "$data_dir/evaluation/runs" \
    "$data_dir/experiments/runs" \
    "$data_dir/indexes" \
    "$data_dir/parsed" \
    "$data_dir/raw" \
    "$data_dir/reports"

if [ "${ODIRAG_RUN_MIGRATIONS:-true}" = "true" ]; then
    max_attempts="${ODIRAG_MIGRATION_MAX_ATTEMPTS:-30}"
    retry_seconds="${ODIRAG_MIGRATION_RETRY_SECONDS:-2}"
    attempt=1

    while ! python -m alembic upgrade head; do
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "Database migration failed after ${max_attempts} attempts." >&2
            exit 1
        fi
        echo "Database migration attempt ${attempt} failed; retrying in ${retry_seconds}s." >&2
        attempt=$((attempt + 1))
        sleep "$retry_seconds"
    done
fi

exec "$@"
