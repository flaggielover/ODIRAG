#!/bin/sh
set -eu

skip_seed=false
if [ "${1:-}" = "--skip-seed" ]; then
    skip_seed=true
elif [ "$#" -gt 0 ]; then
    echo "Usage: sh scripts/start_demo.sh [--skip-seed]" >&2
    exit 2
fi

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"

if [ -z "${ODIRAG_ADMIN_PASSWORD+x}" ] \
    && ! grep -Eq '^[[:space:]]*ODIRAG_ADMIN_PASSWORD=' .env 2>/dev/null; then
    export ODIRAG_ADMIN_PASSWORD=development-only-admin-password
fi

export ODIRAG_EMBEDDING_PROVIDER=deterministic
export ODIRAG_EMBEDDING_CACHE_PROVIDER=redis
export ODIRAG_EMBEDDING_DIMENSIONS=64
export ODIRAG_EMBEDDING_VERSION=demo-v1
export ODIRAG_VECTOR_STORE_PROVIDER=qdrant
export ODIRAG_QDRANT_COLLECTION=odirag_demo_chunks_v1
export ODIRAG_RERANK_PROVIDER=deterministic

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required but was not found on PATH." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required." >&2
    exit 1
fi

docker compose build backend
docker compose build frontend
docker compose --profile ui --profile async up --detach --no-build

attempt=1
while [ "$attempt" -le 90 ]; do
    container_id=$(docker compose ps --quiet backend)
    if [ -n "$container_id" ]; then
        state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
        if [ "$state" = "healthy" ]; then
            break
        fi
    fi
    if [ "$attempt" -eq 90 ]; then
        docker compose logs backend
        echo "The backend did not become healthy within 180 seconds." >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

if [ "$skip_seed" = "false" ]; then
    docker compose exec -T backend /app/deployment/initialize-demo.sh
fi

ui_address=$(docker compose port nginx 80)
api_address=$(docker compose port backend 8000)
printf '%s\n' \
    "ODIRAG is ready." \
    "UI:  http://${ui_address}" \
    "API: http://${api_address}/api/docs" \
    "Retrieval: deterministic embeddings + Qdrant + deterministic reranking" \
    "Login: ODIRAG_ADMIN_USERNAME / ODIRAG_ADMIN_PASSWORD (defaults: admin / development-only-admin-password)"
