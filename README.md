# ODIRAG

ODIRAG is an Official Document Intelligence and Retrieval-Augmented Generation platform. It
implements the complete path from source management and crawling through parsing, review,
versioning, indexing, hybrid retrieval, grounded answers, citations, feedback, evaluation,
experiments, observability, and a Vue management console.

The implementation and verification record is maintained in
[`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md). Unavailable Docker/provider checks are
reported as blockers rather than represented by fake success responses.

## One-Command Demo

Prerequisite: Docker Engine with Docker Compose v2.

```powershell
.\scripts\start_demo.ps1
```

```bash
sh scripts/start_demo.sh
```

The command builds and starts PostgreSQL, Redis, Qdrant, the FastAPI backend, Celery worker and
scheduler, the Vue frontend, and Nginx. The API container applies Alembic migrations, then the demo
initializer seeds records and reindexes approved demo documents through the authenticated live
API. Demo retrieval uses deterministic embeddings and reranking with real Qdrant storage.

Default development login: `admin` / `development-only-admin-password`. Override
`ODIRAG_ADMIN_PASSWORD` before startup whenever the stack is reachable by anyone else.

- UI: `http://127.0.0.1:8080`
- API docs: `http://127.0.0.1:8000/api/docs`
- Health: `http://127.0.0.1:8000/api/system/health`

The one-command workflow was statically and logically validated, but the implementation workstation
did not have Docker installed. CI performs image, non-root, writable-volume, migration, health, and
login smoke checks.

## Implemented Capabilities

- YAML source definitions, CRUD/connectivity APIs, adapter registry, pagination, attachments, and
  idempotent crawl persistence.
- Content-gap driven source-pool expansion: Brave candidate discovery, official-domain validation,
  same-site column discovery, bounded trial crawl, quality scoring, manual approval, explicit
  activation, durable stage events, retry compensation, and discovery metrics.
- SSRF-resistant URL/DNS/redirect policy, streamed download limits, atomic task claims, worker-loss
  recovery, Celery late acknowledgements, and scheduled stale-task requeueing.
- HTML, PDF, DOCX, XLSX, TXT, and ZIP metadata parsing; cleaning, exact/SimHash deduplication,
  version snapshots, changed fields, and lineage.
- Rule filtering, versioned prompts, Direct/Coze adapters, strict structured review, manual review,
  and evidence-bound structured knowledge.
- Heading-aware chunks, deterministic/remote embeddings, Redis/memory cache, Qdrant/memory vector
  stores, BM25 snapshots, stable point IDs, stale-vector cleanup, and reindexing.
- BM25/vector/hybrid/hybrid-rerank retrieval, metadata filters, RRF, debug traces, SQL/RAG/composite
  routing, evidence/conflict/outdated checks, stored citations, and refusal.
- Feedback conversion, verified evaluation datasets, real JSON/CSV/Markdown/chart reports,
  isolated experiments, regression comparison, complete trace/lineage, metrics, and alerts.
- Vue 3/TypeScript operations console for sources, crawling, documents, review, chat, evaluation,
  experiments, monitoring, feedback, and authenticated session management.
- Token rotation/revocation, process-local rate limiting, structured errors, production config
  validation, non-root containers, migrations, CI, and one-command demo startup.

## Host Development

Backend:

```bash
cd backend
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Place host-specific `ODIRAG_*` values in `backend/.env` or export them. Compose service names such
as `postgres`, `redis`, and `qdrant` do not resolve from a host process; use `localhost` overrides.
Deterministic local providers are explicitly test/demo implementations, not substitutes for a
configured production model.

The synchronous Coze crawl integration uses the unprefixed deployment variables
`COZE_ENABLED`, `COZE_LEGACY_API_URL`, `COZE_BATCH_API_URL`, `COZE_API_TOKEN`,
`COZE_DEFAULT_CONTRACT`, `COZE_TIMEOUT_SECONDS`, and `COZE_MAX_RETRIES`. Existing
`ODIRAG_COZE_*` aliases remain accepted for compatibility. Do not configure a workflow ID or a
remote polling interval for the current `coze.site/run` contract. After publishing the separate
batch deployment, run the bounded authenticated acceptance check:

```powershell
python scripts/live_accept_coze_batch.py --source-column-id <column_id>
```

The command always queues a real 5-article/1-page batch task through the API and prints only a
redacted count summary. `batch_workflow_not_published` is an explicit unverified state, not a
successful integration result. Full node construction instructions are in
[`docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md`](docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md).

Autonomous source discovery uses Brave Search when `ODIRAG_SOURCE_DISCOVERY_PROVIDER=brave` and
`ODIRAG_SOURCE_DISCOVERY_API_KEY` is configured. The API returns a structured unavailable error
when the credential is absent; it does not fall back to fixture candidates. Production settings
reject deterministic embeddings/reranking, memory caches/vector stores, and deterministic source
discovery.

## Quality Checks

```bash
cd backend
python -m ruff check app tests
python -m black --check app tests
python -m mypy app
python -m pytest --cov=app --cov-report=term-missing

cd ../frontend
npm run lint
npm run type-check
npm test
npm run build
```

The lightweight authenticated load test is `scripts/load_test.py`. Performance goals are search
P95 below 1.5 s, chat P95 below 5 s, and DB P95 below 300 ms, but they are goals only. Actual local
measurements are recorded in `IMPLEMENTATION_STATUS.md` and must not be treated as production SLA
evidence.

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md): boundaries, runtime flow, reliability, and data ownership.
- [`API.md`](API.md): authentication, errors, routes, filters, search, and chat contracts.
- [`EVALUATION.md`](EVALUATION.md): datasets, metrics, artifacts, and measured demo result.
- [`EXPERIMENTS.md`](EXPERIMENTS.md): isolated variants and regression workflow.
- [`DEPLOYMENT.md`](DEPLOYMENT.md): Compose, migrations, data, backup, and production gate.
- [`SECURITY.md`](SECURITY.md): implemented controls, residual risks, and secret handling.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): development and verification rules.
- [`ROADMAP.md`](ROADMAP.md): production validation and scale hardening.
- [`docs/learning/`](docs/learning/): module learning routes and defense material.

## Repository Map

```text
backend/              FastAPI app, Alembic migrations, domain modules, tests
frontend/             Vue 3 + TypeScript operations console
config/               crawler, filter, prompt, and chunking configuration
data/                 curated demo inputs and ignored generated artifacts
deployment/           container entrypoint, demo initializer, Nginx configuration
docs/learning/        implementation-specific learning and defense material
scripts/              startup, seed, experiment, BM25, and load-test commands
.github/workflows/    CI quality, migration, frontend, and container checks
```

## Known Limits

Docker/Qdrant/PostgreSQL/Redis runtime verification remains pending on a Docker-capable host. Live
government-site access and remote LLM/embedding/rerank providers require network approval and
credentials. The rate limiter is process-local, OCR execution is not bundled, and application URL
checks should be paired with network egress controls. See `ROADMAP.md` for release gates.

## License

MIT. See [`LICENSE`](LICENSE).
