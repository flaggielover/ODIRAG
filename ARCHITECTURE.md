# Architecture

ODIRAG is an official-document ingestion, retrieval, grounded-answering, and evaluation platform.
The implemented system uses FastAPI and Vue, PostgreSQL as the business source of truth, Redis for
cache/task/rate-limit infrastructure, Qdrant for vectors, Celery for asynchronous crawling, and
Nginx for development ingress and the accepted production TLS/proxy chain.

## Current Production Status

The current accepted deployment is release `v0.1.0-r6` at
<https://rag.suzheodirag.top/>. Phase 1 through Phase 5 and the final production
readiness decision are `PASS-LIVE`; the authoritative evidence is
[`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md).

- Eight application services are healthy behind public HTTPS, while databases, Qdrant,
  backend management ports, monitoring, and exporters remain private.
- PostgreSQL contains 182 documents and 821 chunks. The active and rollback Qdrant
  collections each retain 821 points at 1536 dimensions with exact PostgreSQL/Qdrant
  chunk-ID equality.
- The accepted provider chain uses Bailian `text-embedding-v4` embeddings, hybrid BM25/vector
  retrieval, Cohere `rerank-v3.5`, and DeepSeek `deepseek-v4-flash` grounded
  generation/refusal.
- Prometheus, Grafana, Alertmanager, Blackbox probes, backup/restore drills, immutable
  GHCR image identity, SBOM/provenance, and transactional deploy/rollback are live-verified.

Production engineering acceptance does not imply high availability or a completed answer-quality
program. The service is single-node, and the latest 100-question Gold evaluation remains
`GOLD_EVALUATION_QUALITY=PARTIAL` with `QUALITY_GUARD=FAIL-LIVE-QUALITY`; see
[`EVALUATION.md`](EVALUATION.md).

## End-to-End Flow

```text
official source + attachment
  -> SSRF-protected crawler adapter
  -> parser registry (HTML/PDF/DOCX/XLSX/TXT/ZIP)
  -> cleaning + exact/near deduplication + version snapshot
  -> rules + LLM/manual review + structured knowledge
  -> approved document
  -> heading-aware chunks + embeddings + Qdrant + BM25 snapshot
  -> metadata analysis + BM25/vector + RRF + rerank
  -> SQL / RAG / composite router
  -> evidence sufficiency + conflict/outdated checks
  -> grounded answer with stored citations, or explicit refusal
  -> trace + lineage + feedback + evaluation + experiment + alerts
  -> Vue operations console
```

Source-pool expansion is a separate durable workflow:

```text
content-gap detection
  -> Brave candidate search
  -> SSRF-safe homepage fetch + official-domain validation
  -> same-site policy-column discovery
  -> bounded trial crawl
  -> evidence-based quality score
  -> manual administrator approval
  -> explicit source/column activation
```

`SourceDiscoveryRun`, `SourceCandidate`, `SourceCandidateColumn`, and
`SourceDiscoveryEvent` retain the counters, evidence, transitions, and failure types for every
stage. A failed queue submission is persisted as failed and can be retried; a candidate is never
enabled solely because an external search provider returned it.

## Backend Boundaries

The dependency direction is `API routers -> application services -> repositories/provider
protocols -> infrastructure`.

- `backend/app/api/routes/` owns HTTP schemas, authentication, status codes, and dependency wiring.
- `backend/app/services/` owns workflows such as crawling, parsing, review, indexing, chat,
  feedback, evaluation, experiments, and monitoring.
- `backend/app/repositories/` owns SQLAlchemy persistence and atomic database transitions.
- `backend/app/crawler/`, `parsers/`, `chunking/`, `retrieval/`, `rag/`, `evaluation/`, and
  `experiments/` contain domain logic with deterministic tests.
- `backend/app/source_discovery/providers.py` contains the Brave Search provider contract, while
  `backend/app/services/source_discovery.py` orchestrates gap detection, validation, trial crawl,
  scoring, approval, and activation.
- `backend/app/runtime.py` selects embedding, cache, vector, rerank, and LLM providers from
  settings without changing service contracts.

PostgreSQL owns sources, source-discovery runs/candidates/events, tasks, documents, versions,
reviews, chunks, traces, feedback, evaluation runs, experiments, lineage, alerts, and users. Qdrant stores rebuildable vector points keyed by
stable chunk IDs. Redis is used for embedding cache and Celery broker/result state. The JSON BM25
snapshot is a rebuildable runtime artifact, not business truth.

## Retrieval and Answering

`IndexingService` chunks only approved documents, embeds in batches with cache/retry metadata,
upserts vectors, replaces relational chunks atomically, records lineage, removes stale vector
points, and then marks the document indexed. `BM25RebuildService` rebuilds from relational chunks.

`RetrievalEngine` applies validated filters and can run BM25, vector, hybrid RRF, or hybrid plus
rerank. Debug responses persist/return each stage, timing, warning, and configuration snapshot.
`QueryRouter` selects safe SQLAlchemy count templates, RAG, or a composite path; it never executes
model-generated SQL. `GroundingService` checks evidence amount, official-source status, question
coverage, policy conflicts, and superseded evidence. Citations are rebuilt from stored chunk and
document records, so generated text cannot introduce a new URL.

## Reliability and Security

- Crawler URLs reject credentials, localhost, and non-public IP ranges; every redirect is
  revalidated after DNS resolution. Responses are streamed with declared and cumulative byte
  limits.
- Crawl workers claim tasks with an atomic database update. Late acknowledgements, visibility/time
  limits, uniqueness constraints, stale-task recovery, and scheduled requeueing handle duplicate
  delivery and worker loss.
- Access/refresh tokens include a user token version. Refresh rotates the version; replay and
  logout invalidate older tokens.
- API rate limiting returns a unified 429 contract. Non-test environments use a shared
  Redis fixed-window limiter and fail closed when Redis is unavailable; the in-memory
  implementation is test-only. A future multi-replica deployment must revalidate counter
  capacity, trusted-proxy identity, and the rest of the stateful runtime.
- The application exposes low-cardinality Prometheus metrics for HTTP, database, provider,
  and RAG stages. Persisted operational alerts remain available through the application API,
  while production Prometheus/Grafana/Alertmanager provide scrape, dashboard, and alert lifecycle.

## Frontend

`frontend/src/api/` contains the typed HTTP client and schemas. Vue Router and the authenticated
application shell expose dashboard, sources, crawl tasks, documents, review, chat/citations,
evaluations, experiments, monitoring/alerts, and feedback/activity views. Tokens are held in the
frontend auth state; logout calls the revocation endpoint before clearing the session. User-facing
document/chat content is rendered as text, not trusted HTML.

## Deployment Topology

The root `docker-compose.yml` is the reproducible development/demo topology. It defines backend,
frontend, PostgreSQL, Redis, Qdrant, worker, scheduler, and Nginx. The backend image runs as
UID/GID 10001, owns `/app/data`, and applies Alembic migrations in the API container entrypoint
with retry. Worker and scheduler wait for the healthy API and do not race migrations. The
`app-data` volume persists BM25, evaluation/experiment artifacts, parsed files, attachments, and
scheduler state.

The accepted production topology is defined by `deploy/production/compose.yml` and related
versioned release files. It adds private service networks, resource and process limits, secret-file
injection, Redis authentication, log rotation, persistent data mappings, internal health probes,
host TLS termination, monitoring, and digest-bound release activation. Production release and
rollback operations preserve PostgreSQL, Redis, Qdrant, attachment, and monitoring volumes.

The one-command demo uses deterministic embeddings and reranking with real Qdrant storage. That
mode is explicitly for reproducible local validation. It does not reproduce the production ingress,
provider, monitoring, recovery, or release topology.

## Observability and Evaluation

Every chat answer persists route, filters, retrieval stages, prompt snapshot, model, citations,
latency, tokens, cost, refusal, and result. Lineage traverses citation -> chunk -> document version
-> crawl task -> source and can include evaluation-run linkage. Monitoring aggregates crawler,
knowledge, RAG, dependency, route, database, provider, and cost signals. Production Prometheus,
Grafana, Alertmanager, exporters, and public-path Blackbox probes complement the persisted
acknowledge/resolve alert lifecycle.

Evaluation calls the real chat service and writes JSON, CSV, Markdown, and chart-ready artifacts.
Experiments build isolated variants and compare metric direction/tolerance rather than using
hard-coded conclusions.

## Deliberate Limitations

- Production is a single-node recovery architecture, not a highly available deployment.
- The latest 100-question Gold run still has low exact citation precision/recall and only
  `0.644444` Supported Answer Recall; 32/90 supported questions were refused.
- No paid third-party uptime or paging service is configured. Internal/public-path monitoring and
  independent external verification do not provide an external SLA.
- SSH source-CIDR restriction awaits a stable management CIDR. Qdrant client/server versions also
  remain scheduled for a controlled alignment.
- HSTS is intentionally one day without `includeSubDomains` during the initial observation window.
- Attachment parsing accepted 60 files, but unsupported legacy formats, unavailable source bytes,
  and the absence of a production OCR provider remain explicit boundaries.
- Source-discovery and attachment paths close their application-level validation/connection window
  when trusted DNS and pinned transports are configured. Coverage remains path/configuration
  scoped; network-level egress controls are still desirable for other outbound paths.
- Horizontal API/worker scaling requires new capacity, scheduling, cache/index, and failure-mode
  validation; the accepted evidence is for the current single-node topology.

See [`ROADMAP.md`](ROADMAP.md), [`EVALUATION.md`](EVALUATION.md), and
[`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for current evidence and future work.
