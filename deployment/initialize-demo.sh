#!/bin/sh
set -eu

if [ -z "${ODIRAG_ADMIN_PASSWORD:-}" ]; then
    echo "ODIRAG_ADMIN_PASSWORD is required to reindex demo documents through the API." >&2
    exit 1
fi

python /app/scripts/seed_demo.py --database-url "$ODIRAG_DATABASE_URL"

python - <<'PY'
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

api_prefix = os.environ.get("ODIRAG_API_PREFIX", "/api").rstrip("/")
base_url = f"http://127.0.0.1:8000{api_prefix}"


def request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    api_request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(api_request, timeout=120) as response:
        if response.status == 204:
            return None
        return json.load(response)


tokens = request(
    "/auth/login",
    method="POST",
    payload={
        "username": os.environ.get("ODIRAG_ADMIN_USERNAME", "admin"),
        "password": os.environ["ODIRAG_ADMIN_PASSWORD"],
    },
)
access_token = str(tokens["access_token"])
query = urllib.parse.urlencode({"final_status": "approved", "limit": 500})
documents = request(f"/documents?{query}", token=access_token)
demo_documents = [
    document
    for document in documents
    if str((document.get("source") or {}).get("source_key", "")).startswith("demo-")
]
if not demo_documents:
    raise SystemExit("No approved demo documents were found after seeding.")

results = []
for document in demo_documents:
    results.append(
        request(
            f"/documents/{int(document['id'])}/reindex",
            method="POST",
            token=access_token,
        )
    )

print(
    json.dumps(
        {
            "indexed_documents": len(results),
            "chunk_count": sum(int(result["chunk_count"]) for result in results),
            "vector_store": os.environ.get("ODIRAG_VECTOR_STORE_PROVIDER"),
            "embedding_provider": os.environ.get("ODIRAG_EMBEDDING_PROVIDER"),
            "qdrant_collection": os.environ.get("ODIRAG_QDRANT_COLLECTION"),
        },
        ensure_ascii=False,
    )
)
PY
