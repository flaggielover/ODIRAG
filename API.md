# API Reference

ODIRAG exposes a FastAPI JSON API under `/api`. Interactive OpenAPI documentation is available
at `/api/docs`, and the machine-readable schema is at `/api/openapi.json`.

## Authentication

Call `POST /api/auth/login` with an administrator username and password. Send the returned access
token as `Authorization: Bearer <token>`. Refresh tokens are single-use: refreshing increments the
user token version, invalidates the old refresh token, and revokes access tokens from the previous
version. `POST /api/auth/logout` revokes the current token family.

```json
{
  "username": "admin",
  "password": "development-only-admin-password"
}
```

The login and refresh responses contain `access_token`, `refresh_token`, `token_type`, and
`expires_in`. Do not persist tokens in logs or source control.

## Error Contract

All handled failures use one envelope:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Document was not found",
    "details": {"identifier": "42"},
    "request_id": "..."
  }
}
```

Common status codes are `401` authentication failure, `403` permission failure, `404` missing
resource, `409` state conflict, `422` validation failure, `429` rate limited, `502` invalid
provider response, and `503` unavailable dependency/provider. Provider error details are logged
server-side and are not returned verbatim. Rate-limited responses include `Retry-After` and
`X-RateLimit-*` headers.

## Endpoint Groups

| Area | Method and path | Purpose |
| --- | --- | --- |
| Auth | `POST /api/auth/login` | Issue an access/refresh pair |
| Auth | `POST /api/auth/refresh` | Rotate a refresh token and issue a new pair |
| Auth | `GET /api/auth/me` | Return the authenticated user |
| Auth | `POST /api/auth/logout` | Revoke the current token family |
| Sources | `GET/POST /api/sources` | List or create source definitions |
| Sources | `GET/PUT/DELETE /api/sources/{id}` | Read, replace, or delete a source |
| Sources | `POST /api/sources/{id}/test` | Run SSRF-protected connectivity validation |
| Crawling | `GET/POST /api/crawl-tasks` | List or create crawl tasks |
| Crawling | `GET /api/crawl-tasks/{id}` | Inspect task state and counters |
| Crawling | `POST /api/crawl-tasks/{id}/retry` | Reset and requeue an eligible task |
| Crawling | `POST /api/crawl-tasks/{id}/cancel` | Cancel a task |
| Documents | `GET /api/documents` | Filter and list documents |
| Documents | `GET /api/documents/{id}` | Read document, versions, reviews, and attachments |
| Documents | `POST /api/documents/{id}/reindex` | Run chunking, embedding, vector upsert, and BM25 refresh |
| Documents | `GET /api/documents/{id}/chunks` | Inspect stored chunks and vector status |
| Reviews | `GET /api/reviews/pending` | List documents requiring review |
| Reviews | `POST /api/reviews/{id}/run` | Run rules and configured LLM review |
| Reviews | `POST /api/reviews/{id}/approve` | Approve a document |
| Reviews | `POST /api/reviews/{id}/reject` | Reject a document |
| Reviews | `POST /api/reviews/{id}/manual-review` | Store an explicit human decision |
| Retrieval | `POST /api/search` | Run BM25, vector, hybrid, or hybrid-rerank search |
| Retrieval | `POST /api/search/debug` | Return analysis, every retrieval stage, timings, and config |
| Chat | `POST /api/chat` | Route SQL/RAG/composite, validate evidence, answer or refuse |
| Chat | `GET /api/chat/traces` | List persisted query traces |
| Chat | `GET /api/chat/traces/{id}` | Inspect one trace |
| Chat | `GET /api/chat/traces/{id}/lineage` | Traverse citation-to-source lineage |
| Feedback | `GET/POST /api/feedback` | List or create trace feedback |
| Feedback | `POST /api/feedback/{id}/convert-to-evaluation` | Convert actionable negative feedback into a verified question |
| Evaluation | `POST /api/evaluations/run` | Run verified questions through the real chat service |
| Evaluation | `GET /api/evaluations` | List evaluation runs |
| Evaluation | `GET /api/evaluations/{id}` | Read stored aggregate metrics |
| Evaluation | `GET /api/evaluations/{id}/report` | Read report data and artifact paths |
| Experiments | `GET/POST /api/experiments` | List or create experiments |
| Experiments | `GET /api/experiments/{id}` | Read an experiment |
| Experiments | `POST /api/experiments/{id}/run` | Build and evaluate isolated variants |
| Experiments | `GET /api/experiments/{id}/compare` | Read deltas, regressions, and failed cases |
| System | `GET /api/system/health` | Report database, Redis, and Qdrant state |
| System | `GET /api/system/metrics` | Return bounded route/DB latency and operational metrics |
| System | `GET /api/system/alerts` | List persisted alerts |
| System | `POST /api/system/alerts/{id}/acknowledge` | Acknowledge an alert |
| System | `POST /api/system/alerts/{id}/resolve` | Resolve an alert |

## Search and Chat

Search modes are `bm25`, `vector`, `hybrid`, and `hybrid_rerank`. Supported explicit filters are
`document_id`, `source_id`, `region`, `city`, `document_type`, `issuing_authority`,
`publish_date_gte`, `publish_date_lte`, and `document_version`. Unknown filters are rejected.

```json
{
  "query": "软件企业研发投入支持措施",
  "mode": "hybrid_rerank",
  "filters": {"region": "四川省"}
}
```

Chat returns `query_type`, `answer`, `refusal`, evidence decisions, citations, filters, and a
persisted `trace_id`. Every citation is rebuilt from stored document/chunk identities and includes
the title, source, publication date, URL, page when known, and evidence quote. The model cannot
invent citation URLs.

## Pagination and Limits

List endpoints use bounded `limit` query parameters where applicable. Request bodies are validated
with Pydantic length/range constraints. Crawler downloads, redirects, timeouts, and attachment
extensions are configured through `ODIRAG_*` settings. See `.env.example` for the complete runtime
contract and `SECURITY.md` for deployment requirements.

## Autonomous Source Discovery

Source-pool expansion is an administrator-only, auditable workflow. A run first compares the
requested topic/region with enabled sources and approved documents. When a gap exists, the queued
worker calls the configured Brave Search API, validates each candidate homepage against public DNS,
redirect, and trusted official-domain rules, discovers same-site policy columns, performs a bounded
trial crawl, and computes a quality score from stored evidence. A candidate never becomes active
automatically: an administrator must approve it and then call activation.

| Method and path | Purpose |
| --- | --- |
| `POST /api/source-discovery/runs` | Detect a content gap and queue or inline-run discovery |
| `GET /api/source-discovery/runs` | List discovery runs and their durable status |
| `GET /api/source-discovery/runs/{id}` | Inspect gap evidence and counters |
| `GET /api/source-discovery/runs/{id}/candidates` | List candidates and trial quality data |
| `GET /api/source-discovery/runs/{id}/events` | Read append-only stage transition evidence |
| `POST /api/source-discovery/runs/{id}/retry` | Requeue a failed run after fixing its dependency |
| `GET /api/source-discovery/candidates/{id}` | Inspect official validation, columns, and score |
| `POST /api/source-discovery/candidates/{id}/approve` | Record manual approval |
| `POST /api/source-discovery/candidates/{id}/reject` | Record a required rejection reason |
| `POST /api/source-discovery/candidates/{id}/activate` | Materialize approved columns as an enabled source |
| `GET /api/source-discovery/metrics` | Aggregate run, candidate, column, approval, and activation states |

The live provider is `brave` (`ODIRAG_SOURCE_DISCOVERY_PROVIDER=brave`) with
`ODIRAG_SOURCE_DISCOVERY_API_KEY`. Missing credentials return `503 PROVIDER_UNAVAILABLE`; the
development/test deterministic provider is only injectable in tests and is rejected in production.
