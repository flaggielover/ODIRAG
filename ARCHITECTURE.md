# Architecture

ODIRAG is an official-document ingestion, retrieval, grounded-answering, and evaluation platform.
The implemented system uses FastAPI and Vue, PostgreSQL as the business source of truth, Redis for
cache/task infrastructure, Qdrant for vectors, Celery for asynchronous crawling, and Nginx as the
local edge proxy.

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
- API rate limiting returns a unified 429 contract. The current limiter is process-local and must
  be replaced or enforced at ingress for a horizontally scaled deployment.
- Route and SQLAlchemy engine metrics keep bounded samples and report P50/P95/P99 without an
  external metrics store.

## Frontend

`frontend/src/api/` contains the typed HTTP client and schemas. Vue Router and the authenticated
application shell expose dashboard, sources, crawl tasks, documents, review, chat/citations,
evaluations, experiments, monitoring/alerts, and feedback/activity views. Tokens are held in the
frontend auth state; logout calls the revocation endpoint before clearing the session. User-facing
document/chat content is rendered as text, not trusted HTML.

## Deployment Topology

`docker-compose.yml` defines backend, frontend, PostgreSQL, Redis, Qdrant, worker, scheduler, and
Nginx. The backend image runs as UID/GID 10001, owns `/app/data`, and applies Alembic migrations in
the API container entrypoint with retry. Worker and scheduler wait for the healthy API and do not
race migrations. The `app-data` volume persists BM25, evaluation/experiment artifacts, parsed
files, attachments, and scheduler state.

The one-command demo uses deterministic embeddings and reranking with real Qdrant storage. That
mode is explicitly for reproducible local validation; production providers and credentials remain
deployment choices.

## Observability and Evaluation

Every chat answer persists route, filters, retrieval stages, prompt snapshot, model, citations,
latency, tokens, cost, refusal, and result. Lineage traverses citation -> chunk -> document version
-> crawl task -> source and can include evaluation-run linkage. Monitoring aggregates crawler,
knowledge, RAG, dependency, route, database, and cost signals into persisted alerts with
acknowledge/resolve lifecycle.

Evaluation calls the real chat service and writes JSON, CSV, Markdown, and chart-ready artifacts.
Experiments build isolated variants and compare metric direction/tolerance rather than using
hard-coded conclusions.

## Deliberate Limitations

Docker and live PostgreSQL/Redis/Qdrant were not executable on the implementation workstation, so
container runtime claims remain CI/external validation work. Remote LLM, embedding, and rerank
providers require credentials. Application-layer DNS validation still benefits from network-level
egress rules to close DNS rebinding time-of-check/time-of-use risk. See `ROADMAP.md` and
`IMPLEMENTATION_STATUS.md` for the current evidence and remaining production gates.
