# Changelog

All notable implementation changes are recorded here. Immutable production release tags exist
through `v0.1.0-r6`; no stable semantic-version release has been declared. Historical
implementation entries remain under `Unreleased`.

## Unreleased

### Added

- Phase 1-5 production-engineering closure: Redis-backed fail-closed rate limiting, live Bailian /
  Cohere / DeepSeek provider checks, PostgreSQL/Qdrant/Redis/attachment recovery, Prometheus /
  Grafana / Alertmanager, immutable GHCR releases with SPDX SBOM and BuildKit provenance,
  transactional deployment/rollback, and public HTTPS/browser acceptance. Detailed evidence is in
  `PRODUCTION_READINESS_REPORT.md`; the Gold quality gate remains partial.
- Phase 16 content-gap driven source-pool expansion with a Brave Search provider, official-domain
  validation, same-site column discovery, bounded trial crawling, evidence-based scoring, manual
  approval, explicit activation, durable events, retry-safe candidates, queue-failure compensation,
  monitoring metrics, migration `0004_source_discovery`, and API/integration tests.
- Phase 0 repository audit and continuous implementation status tracking.
- Phase 1 backend packaging for Python 3.11+ with FastAPI development tooling.
- Complete SQLAlchemy core schema and Alembic migration for sources, crawling, documents,
  versions, attachments, reviews, knowledge, chunks, prompts, retrieval configuration,
  evaluations, experiments, traces, feedback, lineage, alerts, and users.
- Admin JWT login/refresh/me endpoints, structured error handling, request logging, built-in
  metrics, real dependency health checks, and a Celery worker readiness task.
- Provider contracts and honest remote adapters for LLM, embedding, reranking, and Qdrant,
  plus deterministic providers explicitly scoped to tests and demo mode.
- Heading-aware chunking, BM25, hybrid retrieval, reciprocal-rank fusion, reranking,
  SQL/RAG/composite routing, evidence checks, citation binding, evaluation metrics, and
  experiment comparison primitives with unit coverage.
- Docker Compose topology for PostgreSQL, Redis, Qdrant, the backend, Celery worker and
  scheduler profiles, the future Vue frontend image, and Nginx ingress.
- Non-root backend image, multi-stage frontend image, persistent service volumes, health
  checks, and loopback-only development port bindings.
- Root environment template, Make targets, and GitHub Actions checks for backend linting,
  type checking, tests, coverage, conditional frontend builds, and container builds.
- Initial architecture, deployment, and security documentation.
- Source and column CRUD APIs, real connectivity checks, configurable crawler adapters,
  normalized URLs, task lifecycle controls, Celery dispatch, attachment storage, and
  idempotent repeated crawls.
- Generic HTML fixture crawling and a contract-tested adapter for the public China
  Government latest-policy JSON feed, backed by validated `config/sites.yaml` settings.
- Parser registry covering HTML, PDF, DOCX, XLSX, TXT, and ZIP metadata, including tables,
  headings, hyperlinks, page text, repeated PDF header/footer reduction, and OCR flags.
- Text cleaning, exact hashes, SimHash near-duplicate detection, authoritative duplicate
  selection, document version snapshots, changed-field tracking, stale-index marking, and
  data-lineage persistence.
- Configurable rule filtering, immutable prompt versions, strict Direct/Coze LLM review,
  retry and raw-response persistence, manual review states, and evidence-bound structured
  policy knowledge extraction.
- Configurable heading-aware chunking with semantic fallback, parsed attachment and PDF page
  indexing, stable versioned chunk identities, embedding batching/cache/retry/rate and cost
  metadata, and retryable cross-store index state transitions.
- Qdrant collection creation, dimension checks, payload indexes and filtered queries, plus
  idempotent vector replacement, chunk/vector lineage, JSON BM25 snapshots, and a real BM25
  rebuild command.
- Shared application retrieval runtime, normalized BM25 scoring, query/filter analysis,
  BM25/vector/hybrid/hybrid-rerank modes, bounded RRF, validated rerank responses, score
  thresholds, final context selection, stage timings, and provider-degradation warnings.
- Authenticated search, admin retrieval-debug, document reindex, and chunk inspection APIs
  backed by the same live BM25 and vector indexes.
- Safe SQLAlchemy-only document-count routing, deterministic SQL/RAG/composite query
  classification, and authenticated chat execution with persisted traces.
- Official-source, evidence-coverage, contradiction and newer-policy checks; explicit refusal
  rules; extractive grounded answers; optional Direct/Coze answer generation; and citations
  rebuilt exclusively from stored document and chunk identities, dates, URLs, pages, and quotes.
- Verified evaluation question persistence, real retrieval/chat benchmark execution, complete
  retrieval/answer/citation/refusal/latency/token/cost metrics, and atomic JSON, CSV, Markdown,
  and chart-ready evaluation reports exposed through authenticated APIs.
- A strict experiment framework that rebuilds isolated chunking, embedding, BM25, and vector
  indexes per variant; applies retrieval, filter, rerank, threshold, and prompt settings; links
  evaluation runs; and reports metric regressions, failed cases, and conclusions.
- A repository-local deterministic policy benchmark and runnable
  `scripts/run_experiment.py --config data/experiments/chunk_600_vs_800.yaml` workflow that
  produces measured comparison artifacts without Docker or external credentials.
- Complete stored query traces including the exact prompt snapshot, plus authenticated lineage
  traversal from an answer citation through chunk, document version, crawl task, and source.
- Crawl, indexing, and evaluation-run lineage propagation so retrieved benchmark evidence remains
  connected to its persisted source, document, attachment, chunk, and vector point identities.
- Operational crawler, knowledge, RAG, dependency, latency, evaluation-regression, and cost metrics,
  with persistent alerts, acknowledge/resolve lifecycle APIs, and scheduled alert refreshes.
- A responsive Vue 3 management console with typed API integration for content operations,
  grounded chat, evaluations, experiments, monitoring, feedback, and authenticated sessions.
- Feedback persistence and conversion of actionable negative feedback into verified evaluation
  questions, with conflict handling for positive feedback and token-revoking logout.
- Process-local fixed-window API rate limiting, refresh-token rotation and replay prevention,
  access-token revocation, production configuration validation, and sanitized provider failures.
- SSRF-resistant crawler and source connectivity checks with DNS/IP policy enforcement,
  redirect-by-redirect validation, streamed size limits, and bounded retries.
- Atomic crawl-task claims, stale-task recovery and requeueing, Celery late acknowledgements,
  visibility/time limits, and database-enforced canonical URL uniqueness.
- Bounded route and database latency percentiles, an authenticated async load-test runner, and
  monitoring UI support for DB P95 and per-route P95 values.
- Git ignore coverage for generated BM25 snapshots and load-test reports while preserving
  directory markers for reproducible local workflows.
- Honest demo seed lifecycle: nested SQLite parent creation, idempotent base records, pending
  index/experiment states, and optional real indexing/evaluation instead of hard-coded metrics or
  fabricated traces/alerts.
- Compose handoff hardening: Alembic entrypoint retries, non-root writable `/app/data`, persistent
  app volume, healthy service dependencies, worker/scheduler ordering, real API demo initializer,
  and cross-platform one-command startup scripts.
- Phase 15 documentation handoff: API, evaluation, experiments, contribution, roadmap, MIT license,
  refreshed architecture/security/deployment/README, and 16 implementation-specific learning and
  defense documents.
- CI migration, frontend test, non-root image, writable-volume, health, and administrator-login
  smoke checks.

### Historical Verification Checkpoint

The following bullets record the Phase 15 checkpoint and are intentionally retained as historical
evidence. Current production acceptance is in `PRODUCTION_READINESS_REPORT.md`, and the latest Gold
quality result is in `EVALUATION.md`.

- Final backend checkpoint: 120 tests passed with 82.89% coverage; Ruff, Black, and mypy passed.
- Final frontend checkpoint: 5 test files / 6 tests passed; lint, type-check, and production build
  passed.
- Final local deterministic demo evaluation measured one RAG question over six chunks with
  Recall@1/5/10, MRR, nDCG@10, answer coverage, citation accuracy/completeness, and refusal
  accuracy all at 1.0, and P95 latency of 4 ms.
- Docker Compose runtime remains an external validation item because Docker is unavailable on the
  implementation workstation.
