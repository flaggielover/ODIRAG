# ODIRAG

## 中文简介

ODIRAG（Official Document Intelligence and Retrieval-Augmented Generation，官方文档智能与检索增强生成平台）是一套面向政府公文、产业政策和企业知识库等高可信知识场景的企业级 RAG 系统。它将来源管理、网页采集、附件处理、内容解析、人工审核、版本治理、索引构建、混合检索、生成回答、证据校验和引用溯源整合为一条完整、可审计的生产流程。

项目强调“有证据才回答”。系统通过 BM25 与向量检索召回候选内容，经过融合和重排序后判断证据是否充分：证据足够时生成带引用的回答，证据不足或问题超出知识库范围时安全拒答，避免将模型推测包装成事实。对于 RAG 问答，系统可以追踪检索候选、最终证据、引用来源和各处理阶段，便于审核、评测与故障定位。

### 核心能力

- 官方信息源管理、自动采集、附件下载审计，以及面向 SSRF、DNS 和重定向风险的安全控制。
- HTML、PDF、DOCX、XLSX、TXT 与 ZIP 元数据解析，支持清洗、去重、版本快照和内容血缘追踪。
- BM25、向量检索、混合召回、RRF 融合与远程重排序，并保留完整检索 Trace。
- 基于证据充分性的 Grounded RAG、证据绑定引用、安全拒答、反馈闭环和人工评测。
- FastAPI、Celery、PostgreSQL、Redis、Qdrant、Vue 3 与 Nginx 组成的完整应用栈。
- 可观测性、告警、备份恢复、不可变发布、事务恢复、可验证回滚、CI、SBOM 和供应链验证。

项目已经完成从基础设施、灾难恢复、监控告警、发布回滚到公网 HTTPS 验收的完整生产工程流程。各阶段均以真实执行证据记录，当前生产就绪结论及边界见 [`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md)。

## English Overview

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

The one-command workflow has been exercised on the implementation workstation. The last complete
local acceptance used the previous base images; the hardened Python 3.12 Alpine and Nginx 1.30.4
images still require a clean rebuild after the workstation's Docker Desktop WSL data-disk mount
failure. CI performs image, backend non-root, writable-volume, migration, health, and login smoke checks.

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
- Token rotation/revocation, shared Redis fixed-window rate limiting (memory only in tests), structured errors, production config
  validation, a non-root backend container, migrations, CI, and one-command demo startup.

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

When its live preflight passes, the command queues a real 5-article/1-page batch task through the API
and prints only a redacted count summary. `batch_workflow_not_published` exits before task creation
and is an explicit unverified state, not a successful integration result. Full node construction instructions are in
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

The local Docker/Qdrant/PostgreSQL/Redis development stack was verified with the previous base
images; the current hardened images remain unverified until Docker Desktop recovers and rebuilds
them. Target production TLS, ACLs, backup/restore, and failure drills remain pending. Live government-site access and
remote LLM/embedding/rerank providers require network approval and credentials. Redis-backed
rate limiting is the non-test default and fails closed when Redis is unavailable; OCR execution
is not bundled, and application URL checks should be paired with network egress controls. See
`ROADMAP.md` for release gates.

## License

MIT. See [`LICENSE`](LICENSE).
