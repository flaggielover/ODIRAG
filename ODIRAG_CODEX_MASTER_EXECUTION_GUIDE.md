# ODIRAG Master Execution Guide for Codex
## Build the Production-Grade Official Document Intelligence & RAG Platform

> Project: **ODIRAG — Official Document Intelligence & RAG Platform**  
> Mode: **Autonomous, phased, test-driven implementation**  
> Goal: **Deliver a genuinely runnable enterprise-grade flagship project, not a scaffold or visual demo**  
> Uses: internship defense, postgraduate interview, AI engineering job applications, GitHub open-source portfolio

---

# 0. Your Role

You are the lead software engineer responsible for implementing the entire ODIRAG platform in the current workspace.

You must not deliver only architecture notes, pseudocode, placeholders, disconnected modules, or a frontend mockup. You must inspect the existing repository, reuse working code where appropriate, build the system phase by phase, run tests after every phase, fix failures before continuing, and keep the application runnable throughout development.

Do not ask the user to make routine technical decisions. Infer reasonable defaults, record assumptions, and continue. If an external service is unavailable, implement the real adapter and contract tests, expose the integration as unavailable, and never fabricate a successful result.

---

# 1. Product Mission

Build a production-oriented official-document intelligence platform with this complete workflow:

```text
Official Websites
    ↓
Configurable Crawling and Incremental Updates
    ↓
HTML / PDF / DOCX / XLSX Parsing
    ↓
Cleaning, Deduplication, and Versioning
    ↓
Rule-Based Filtering
    ↓
Coze or Direct LLM Review and Structured Extraction
    ↓
Manual Review
    ↓
PostgreSQL Structured Storage
    ↓
Heading-Aware Chunking
    ↓
Embedding and Qdrant Indexing
    ↓
BM25 + Vector Search + Metadata Filters
    ↓
Reciprocal Rank Fusion
    ↓
Reranking
    ↓
SQL / RAG / SQL+RAG Query Routing
    ↓
Evidence Sufficiency and Conflict Detection
    ↓
Grounded Answer Generation
    ↓
Verified Citations and Refusal
    ↓
Vue Management Console
    ↓
Evaluation, Experiments, Traces, Monitoring, and Feedback
```

The final system must be runnable, testable, extensible, observable, traceable, reproducible, containerized, documented, and suitable for open-source presentation.

---

# 2. Non-Negotiable Engineering Rules

## 2.1 No Fake Implementation

The following are prohibited in required functionality:

- `pass` or empty functions;
- fake service responses;
- hard-coded dashboard metrics;
- hard-coded retrieval results;
- TODO or FIXME instead of implementation;
- “coming soon” placeholders;
- frontend-only mock workflows;
- fabricated evaluation metrics;
- citations that do not come from retrieved evidence;
- silent exception swallowing;
- claiming that unexecuted functionality passed.

Test doubles are allowed only inside tests or clearly labeled demo mode.

## 2.2 Test Before Proceeding

At the end of every phase:

1. run linting;
2. run type checks;
3. run unit tests;
4. run relevant integration tests;
5. run the current end-to-end smoke test;
6. fix failures;
7. update documentation;
8. create a checkpoint commit if Git is available.

Do not continue with a broken main branch.

## 2.3 Preserve Layer Boundaries

Use this structure:

```text
API
→ Services
→ Repositories / Providers
→ Infrastructure
```

Do not put business logic in API routers. Do not access PostgreSQL, Redis, Qdrant, Coze, or model APIs directly from frontend code. Do not use Qdrant as the business database.

## 2.4 Configuration Over Hard-Coding

Make the following configurable:

- website selectors and pagination;
- request interval and timeout;
- filtering thresholds;
- chunk sizes and overlap;
- embedding, rerank, and LLM providers;
- retrieval top-k and RRF settings;
- score thresholds;
- model names;
- prompt versions;
- service URLs and credentials.

Use YAML and environment variables.

## 2.5 Honest Degradation

When an external integration is missing, the application must start where possible, expose dependency health, disable only affected features, return structured errors, and never fabricate data.

---

# 3. Required Technology Stack

## Backend

- Python 3.11+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Redis
- Celery or RQ
- APScheduler or Celery Beat
- httpx
- BeautifulSoup4
- lxml
- PyMuPDF or pdfplumber
- python-docx
- openpyxl
- qdrant-client
- rank-bm25
- tenacity
- pytest, pytest-asyncio, pytest-cov
- Ruff, Black, mypy

## Frontend

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Axios
- Element Plus or Naive UI
- ECharts
- safe Markdown renderer

## Infrastructure

- Docker
- Docker Compose
- Nginx
- GitHub Actions
- PostgreSQL
- Redis
- Qdrant
- worker service
- scheduler service

Implement built-in metrics and health first. Add Prometheus/Grafana configuration if feasible.

---

# 4. Target Repository Structure

```text
official-document-rag/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── security.py
│   │   ├── api/
│   │   ├── schemas/
│   │   ├── models/
│   │   ├── database/
│   │   ├── repositories/
│   │   ├── crawler/
│   │   ├── parsers/
│   │   ├── cleaners/
│   │   ├── filters/
│   │   ├── deduplication/
│   │   ├── knowledge/
│   │   ├── llm/
│   │   ├── chunking/
│   │   ├── embedding/
│   │   ├── vector_store/
│   │   ├── bm25/
│   │   ├── retrieval/
│   │   ├── rerank/
│   │   ├── router/
│   │   ├── rag/
│   │   ├── evaluation/
│   │   ├── experiments/
│   │   ├── tracing/
│   │   ├── lineage/
│   │   ├── monitoring/
│   │   ├── cache/
│   │   ├── tasks/
│   │   ├── services/
│   │   └── utils/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── e2e/
│   │   ├── regression/
│   │   ├── fixtures/
│   │   └── samples/
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── utils/
│   │   └── views/
│   └── package.json
├── config/
│   ├── sites.yaml
│   ├── filters.yaml
│   ├── knowledge_schema.yaml
│   ├── chunking.yaml
│   ├── retrieval.yaml
│   ├── rerank.yaml
│   ├── monitoring.yaml
│   └── prompts/
├── data/
│   ├── raw/
│   ├── parsed/
│   ├── attachments/
│   ├── evaluation/
│   ├── experiments/
│   ├── reports/
│   └── samples/
├── scripts/
├── deployment/
├── .github/workflows/
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── .env.example
├── Makefile
├── README.md
├── ARCHITECTURE.md
├── API.md
├── EVALUATION.md
├── EXPERIMENTS.md
├── DEPLOYMENT.md
├── SECURITY.md
├── CONTRIBUTING.md
├── ROADMAP.md
└── LICENSE
```

Do not reorganize working existing code without a clear migration reason.

---

# 5. Core Data Model

Implement SQLAlchemy models, indexes, constraints, foreign keys, timestamps, and Alembic migrations for these tables.

## sources

`id, source_key, name, domain, region, city, organization_level, organization_type, official_status, homepage_url, enabled, priority, crawl_frequency, last_crawl_time, created_at, updated_at`

## source_columns

`id, source_id, column_key, column_name, column_url, parser_type, enabled, max_pages, request_interval_seconds, selectors_json, pagination_json, created_at, updated_at`

## crawl_tasks

`id, source_column_id, task_type, trigger_type, status, started_at, finished_at, discovered_count, fetched_count, success_count, url_duplicate_count, content_duplicate_count, semantic_duplicate_count, failed_count, retry_count, error_message, created_at`

## documents

`id, document_id, source_id, source_column_id, title, subtitle, source_url, canonical_url, publish_date, author, issuing_authority, document_number, region, city, document_type, content, raw_content, content_hash, simhash, word_count, language, quality_score, rule_filter_status, llm_review_status, manual_review_status, final_status, index_status, version, parent_document_id, duplicate_of_document_id, first_crawl_time, last_crawl_time, created_at, updated_at`

## document_versions

`id, document_id, version, content_hash, content, metadata_json, changed_fields_json, created_at`

## attachments

`id, document_id, attachment_name, source_url, local_path, mime_type, file_extension, file_size, file_hash, download_status, parse_status, parsed_text, page_count, requires_ocr, error_message, created_at, updated_at`

## document_reviews

`id, document_id, review_type, reviewer, decision, quality_score, document_type, topics_json, summary, reasons_json, extracted_fields_json, model_name, prompt_name, prompt_version, raw_response, created_at`

## structured_knowledge

`id, document_id, knowledge_type, field_name, field_value_json, confidence, evidence_chunk_id, extraction_model, prompt_version, verified, created_at, updated_at`

## chunks

`id, chunk_id, document_id, attachment_id, chunk_index, section_path, section_title, page_number, content, content_hash, char_count, token_count, embedding_model, embedding_version, vector_status, created_at, updated_at`

## prompt_versions

`id, prompt_name, version, content_hash, content, change_description, active, created_at`

## retrieval_configs

`id, name, version, vector_top_k, bm25_top_k, fusion_method, rrf_k, rerank_top_k, score_threshold, metadata_rules_json, created_at`

## evaluation_questions

`id, question_id, question, query_type, expected_document_ids, expected_chunk_ids, expected_answer_points, expected_filters, should_refuse, difficulty, category, created_by, verified, created_at, updated_at`

## evaluation_runs

`id, run_name, experiment_id, retrieval_version, prompt_version, embedding_model, rerank_model, top_k, started_at, finished_at, question_count, recall_at_1, recall_at_5, recall_at_10, mrr, ndcg, citation_accuracy, refusal_accuracy, hallucination_rate, average_latency, p95_latency, average_cost, result_path, created_at`

## experiments

`id, experiment_name, experiment_type, baseline_config_json, candidate_config_json, status, started_at, finished_at, conclusion, artifact_path, created_at`

## query_traces

`id, trace_id, user_query, query_type, parsed_filters_json, bm25_results_json, vector_results_json, fusion_results_json, rerank_results_json, final_context_json, prompt_version, model_name, answer, citations_json, refusal, latency_ms, token_usage_json, cost, created_at`

## user_feedback

`id, trace_id, rating, feedback_type, comment, expected_document_id, resolved, converted_to_evaluation, created_at`

## data_lineage

`id, lineage_id, source_id, crawl_task_id, document_id, document_version_id, attachment_id, chunk_id, vector_point_id, evaluation_run_id, created_at`

---

# 6. Provider Interfaces

Define interfaces before provider implementations.

## LLM Orchestrator

```python
class LLMOrchestrator(Protocol):
    async def review_document(...): ...
    async def analyze_query(...): ...
    async def generate_answer(...): ...
    async def check_evidence(...): ...
```

Implement `CozeAdapter` and `DirectLLMAdapter`. Core data, retrieval, evaluation, and citation logic must not depend on Coze.

## Embedding Provider

```python
class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
```

Implement a remote provider and a deterministic test/demo provider.

## Rerank Provider

```python
class RerankProvider(Protocol):
    async def rerank(self, query: str, documents: list[str], top_k: int): ...
```

Implement a remote provider, configurable no-rerank mode, and deterministic test provider.

Abstract file storage, vector storage, BM25 index, cache, and task queue access.

---

# 7. Required API Surface

Use Pydantic request/response schemas and OpenAPI documentation.

## Authentication

```text
POST /api/auth/login
POST /api/auth/refresh
GET  /api/auth/me
```

## Sources

```text
GET    /api/sources
POST   /api/sources
GET    /api/sources/{id}
PUT    /api/sources/{id}
DELETE /api/sources/{id}
POST   /api/sources/{id}/test
```

## Crawling

```text
POST /api/crawl-tasks
GET  /api/crawl-tasks
GET  /api/crawl-tasks/{id}
POST /api/crawl-tasks/{id}/retry
POST /api/crawl-tasks/{id}/cancel
```

## Documents

```text
GET    /api/documents
GET    /api/documents/{id}
PUT    /api/documents/{id}
DELETE /api/documents/{id}
POST   /api/documents/{id}/reparse
POST   /api/documents/{id}/reindex
GET    /api/documents/{id}/chunks
GET    /api/documents/{id}/attachments
GET    /api/documents/{id}/versions
GET    /api/documents/{id}/lineage
```

## Reviews

```text
GET  /api/reviews/pending
POST /api/reviews/{document_id}/approve
POST /api/reviews/{document_id}/reject
POST /api/reviews/{document_id}/manual-review
```

## Search and Chat

```text
POST /api/search
POST /api/search/debug
POST /api/chat
GET  /api/chat/traces/{trace_id}
```

## Evaluation and Experiments

```text
POST /api/evaluations/run
GET  /api/evaluations
GET  /api/evaluations/{id}
GET  /api/evaluations/{id}/report
POST /api/experiments
GET  /api/experiments
GET  /api/experiments/{id}
POST /api/experiments/{id}/run
GET  /api/experiments/{id}/compare
```

## Feedback and System

```text
POST /api/feedback
GET  /api/feedback
POST /api/feedback/{id}/convert-to-evaluation
GET /api/system/health
GET /api/system/metrics
GET /api/system/alerts
```

---

# 8. Implementation Phases

Implement in this order. First establish one complete vertical slice, then continue until all enterprise requirements are finished.

## Phase 0 — Repository Audit

- inspect all existing files;
- identify reusable code;
- preserve existing work;
- create `IMPLEMENTATION_STATUS.md`;
- create a phase checklist;
- record assumptions;
- verify Python, Node, Docker, and Git.

## Phase 1 — Infrastructure and Core Backend

Implement FastAPI application factory, configuration, PostgreSQL, SQLAlchemy, Alembic, Redis, logging, structured errors, health endpoints, admin authentication, Docker Compose for backend dependencies, `.env.example`, Makefile, CI skeleton, and all core models/migrations.

Acceptance:

```bash
docker compose up -d postgres redis qdrant
cd backend
alembic upgrade head
pytest tests/unit
uvicorn app.main:app
```

`GET /api/system/health` must report dependency status.

## Phase 2 — Source Management and Crawling

Implement YAML source configuration, CRUD, generic crawler, adapter registry, retries, timeout, rate control, encoding, pagination, URL normalization, task state machine, async task execution, retry/cancel, raw HTML storage, list/detail parsing, attachment discovery/download, and idempotency.

Required types: HTML, PDF, DOCX, XLSX, TXT, ZIP metadata.

Acceptance: local fixtures complete the full crawl path. Use a real site for at least 10 articles when reachable. Repeated runs do not duplicate records.

## Phase 3 — Parsing, Cleaning, Deduplication, and Versioning

Implement:

- HTML content extraction, headings, paragraphs, lists, tables, boilerplate removal;
- PDF text/page extraction, repeated header/footer reduction, OCR flagging;
- DOCX headings, paragraphs, tables, hyperlinks;
- XLSX sheet names, headers, Markdown/JSON conversion, row splitting;
- canonical URL, SHA256, SimHash near-duplicate detection;
- authoritative source selection;
- content-change detection, document versions, stale indexes, changed-field records;
- lineage records.

## Phase 4 — Filtering, LLM Review, and Structured Knowledge

Implement rule rejection and soft scoring, reason codes, configurable thresholds, versioned prompts, Coze adapter, Direct LLM adapter, strict JSON validation, retries, raw response storage, manual review state, and structured extraction.

Extract issuing authority, document number, policy target, support measures, application conditions, funding amount, deadline, department, region, industry, contact information, and key indicators. Bind every field to evidence and provenance.

## Phase 5 — Chunking, Embedding, and Indexing

Implement heading-aware chunking with paragraphs/lists/tables and recursive fallback. Make target, min, max, and overlap configurable.

Implement embedding batching, caching, retry, rate limiting, provider abstraction, model/version metadata, and cost metadata.

Implement Qdrant collection creation, payload indexes, idempotent upsert, deletion, reindexing, and versioning. Implement BM25 indexing and rebuild command.

## Phase 6 — Retrieval Engine

Implement query analysis, BM25 top-k, vector top-k, metadata filters, Reciprocal Rank Fusion, rerank, score threshold, final context selection, and full debug trace.

Support and test:

```text
BM25 only
Vector only
Hybrid
Hybrid + Rerank
```

`POST /api/search/debug` must return a readable retrieval trace.

## Phase 7 — SQL / RAG / Composite Router

Classify queries as SQL, RAG, or SQL+RAG.

Use safe templates or a validated query builder for SQL. Never execute unrestricted LLM-generated SQL.

Examples:

```text
“How many software policy documents were published in Sichuan after 2025?” → SQL
“What are the common support measures?” → RAG
“Among policies published after 2025, summarize the application requirements.” → SQL + RAG
```

## Phase 8 — Grounded Answering, Conflict, Refusal, and Citations

Implement evidence sufficiency checks, official-source validation, question coverage, contradiction detection, outdated/newer policy detection, refusal rules, and citation construction.

Every citation must include actual stored document/chunk identity, title, source, publication date, URL, page, and evidence quote. The LLM must never create URLs.

## Phase 9 — Evaluation and Benchmark

Support manually verified questions with relevant documents/chunks, expected answer points, filters, refusal label, difficulty, and category.

Calculate:

- Recall@1/5/10;
- MRR;
- nDCG;
- document and chunk hit rate;
- answer point coverage;
- citation accuracy and completeness;
- refusal accuracy;
- hallucination rate;
- P50/P95 latency;
- tokens and cost.

Generate JSON, CSV, Markdown, and chart-ready output. Run a real evaluation on demo data. Do not hard-code metric values.

## Phase 10 — Experiment Framework and Regression

Support experiments for chunk size, overlap, embedding model, top-k, RRF, metadata filters, rerank, score threshold, and prompt version.

Example:

```bash
python scripts/run_experiment.py --config data/experiments/chunk_600_vs_800.yaml
```

Generate comparison reports, regressions, failed cases, and conclusions.

## Phase 11 — Trace, Lineage, Monitoring, and Alerts

Persist the full query trace from query through filters, retrieval, fusion, rerank, context, prompt, answer, citations, refusal, latency, tokens, and cost.

Support lineage traversal from answer → citation → chunk → document version → crawl task → source.

Expose crawler, knowledge, and RAG health metrics. Store alerts for high failure rate, index failures, unavailable services, latency regressions, evaluation regressions, and abnormal cost.

## Phase 12 — Vue Frontend

Build polished, real API-connected pages:

- Dashboard;
- Sources;
- Crawl Tasks;
- Documents;
- Document Detail;
- Manual Review;
- Chat with evidence cards and trace;
- Evaluation;
- Experiments;
- Monitoring;
- Feedback and logs.

No hard-coded metrics. Use typed API clients, loading/error states, responsive design, safe Markdown, and accessible forms.

## Phase 13 — Feedback Loop

Implement helpful/not helpful, incorrect citation, missing document, incomplete answer, should refuse, and should not refuse feedback. Allow verified feedback to become an evaluation question.

## Phase 14 — Security, Reliability, and Performance

Implement authentication, authorization, rate limiting, file limits, file allowlist, path safety, SQL injection protection, XSS protection, CORS, secure secrets, error codes, retries, timeouts, idempotency, distributed locks, cache, batch embedding, task recovery, migration and backup documentation.

Add a lightweight load test. Treat search P95 <1.5s, chat P95 <5s, and DB P95 <300ms as goals only; report actual measurements.

## Phase 15 — Docker, CI/CD, and Open-Source Handoff

Docker Compose services:

- backend;
- frontend;
- postgres;
- redis;
- qdrant;
- worker;
- scheduler;
- nginx;
- optional prometheus/grafana.

GitHub Actions must run backend lint, type checks, tests, coverage, frontend lint/build, and Docker build.

Complete README, architecture, API, evaluation, experiments, deployment, security, contribution, roadmap, demo seed, and one-command startup.

---

# 9. Testing Requirements

## Unit Tests

Cover:

- URL normalization;
- hashing;
- date parsing;
- text cleaning;
- duplicate paragraph removal;
- safe file naming;
- parser behavior;
- deduplication;
- versioning;
- rule filtering;
- chunking;
- metadata filtering;
- RRF;
- rerank handling;
- query routing;
- evidence checks;
- conflict detection;
- refusal;
- citation binding;
- evaluation metrics;
- cache behavior;
- idempotency.

## Integration Tests

Cover:

- HTML to document;
- PDF to document;
- document to PostgreSQL;
- review pipeline;
- document to chunks;
- chunks to embedding;
- embedding to Qdrant;
- BM25 rebuild;
- hybrid search;
- chat answer and citations;
- feedback conversion;
- evaluation report;
- experiment comparison.

## End-to-End Test

```text
Seed Source
→ Crawl Fixture
→ Parse
→ Review
→ Approve
→ Index
→ Search
→ Chat
→ Cite
→ Feedback
→ Evaluate
```

## Regression Test

Use a fixed demo benchmark and run it after changes to prompts, chunking, embeddings, retrieval, rerank, router, evidence, or refusal logic.

---

# 10. Definition of Done

The project is complete only when all applicable conditions below are true.

## Data and Crawling

- at least one real website works when reachable;
- local fixtures cover every parser;
- repeated crawling is idempotent;
- attachment failures do not destroy document records;
- document versions work;
- duplicate handling is explainable;
- data lineage works;
- accepted documents can be indexed;
- stale versions are reindexed correctly.

## Retrieval and RAG

- BM25 works;
- vector retrieval works;
- metadata filtering works;
- RRF works;
- rerank works;
- SQL/RAG/composite routing works;
- evidence checking works;
- conflict detection works;
- refusal works;
- citations map to real chunks;
- trace debugging works.

## Evaluation

- evaluation datasets are supported;
- real metrics are generated;
- experiment framework runs;
- regression reports are generated;
- no metrics are hard-coded;
- failed cases are inspectable.

## Enterprise Engineering

- PostgreSQL is the business database;
- Redis is used for cache/task state/locks where applicable;
- task queue and scheduler work;
- FastAPI and Vue are integrated;
- Qdrant is operational;
- Docker Compose starts the platform;
- CI is present;
- tests and logs are present;
- health, trace, monitoring, and alerts are present;
- secrets are not committed.

## Open-Source Handoff

- clean repository;
- demo data and local fixtures;
- one-command startup;
- architecture and API documentation;
- evaluation documentation;
- known limitations;
- no proprietary credentials or private source data committed.

---

# 11. Mandatory Progress Tracking

Maintain `IMPLEMENTATION_STATUS.md` with this structure:

```text
Phase
Status
Implemented Features
Commands Run
Test Results
Coverage
Known Issues
Blocked External Integrations
Next Action
```

Update it after every phase.

Maintain `CHANGELOG.md` with meaningful implementation changes.

If Git is available, create checkpoint commits after stable phases. Do not create meaningless commits for every tiny edit.

---

# 12. Final Delivery Report

When implementation is complete, provide a final report containing:

1. architecture summary;
2. implemented modules;
3. added files;
4. modified files;
5. migrations;
6. environment variables;
7. startup commands;
8. test commands;
9. test results;
10. coverage;
11. real demo results;
12. real evaluation results;
13. known limitations;
14. verified live integrations;
15. integrations requiring credentials;
16. security notes;
17. actual performance measurements;
18. recommended next improvements.

Do not hide incomplete items.

---

# 13. Learning and Defense Materials

The project owner must fully understand the system before the internship defense.

For every major module, create documentation under `docs/learning/`:

```text
01_infrastructure.md
02_crawler.md
03_parsing_and_deduplication.md
04_review_and_structured_knowledge.md
05_chunking_and_embedding.md
06_retrieval.md
07_query_router.md
08_rag_and_citations.md
09_evaluation.md
10_async_and_cache.md
11_frontend.md
12_deployment.md
```

Each file must include:

1. module purpose;
2. inputs and outputs;
3. data flow;
4. core classes and files;
5. major design decisions;
6. why the selected technologies are used;
7. common failure modes;
8. debugging steps;
9. five interview questions with model answers;
10. five defense questions with model answers;
11. a concise code-reading route;
12. one practical modification exercise.

Also create:

- `docs/learning/SYSTEM_DATA_FLOW.md`;
- `docs/learning/TEN_MINUTE_DEFENSE_SCRIPT.md`;
- `docs/learning/CORE_CODE_READING_ORDER.md`;
- `docs/learning/COMMON_TECHNICAL_QUESTIONS.md`.

These learning documents must describe the actual implemented code, not generic theory.

---

# 14. Resource-Efficient Codex Behavior

The project owner uses ChatGPT Plus Codex allowance, so minimize wasted context and rework.

Follow these rules:

1. Read only relevant directories for each phase after the initial audit.
2. Reuse stable interfaces instead of repeatedly redesigning them.
3. Freeze public API schemas after integration tests pass.
4. Avoid rewriting working modules for stylistic reasons.
5. Use automated formatting and codemods for mechanical edits.
6. Run focused tests during implementation and the full suite at checkpoints.
7. Store decisions in `ARCHITECTURE.md` so they do not need to be rediscovered.
8. Keep prompts concise and versioned.
9. Use smaller/local deterministic test providers where model reasoning is unnecessary.
10. Reserve expensive model calls for review, extraction, query analysis, and answer generation.

---

# 15. Execution Behavior

Follow these instructions while working:

1. Begin with repository inspection.
2. Create `IMPLEMENTATION_STATUS.md` immediately.
3. Do not stop after scaffolding.
4. Do not ask for confirmation after routine phases.
5. Make reasonable assumptions and document them.
6. Keep the system runnable after every phase.
7. Prefer one complete working vertical slice over many disconnected modules.
8. After the vertical slice works, continue until the enterprise feature set is complete.
9. If external credentials are missing, complete the adapter, validation, contract tests, health state, and all surrounding functionality.
10. Record genuine blockers and continue with unblocked work.
11. Never fabricate success.
12. Never report a test as passed unless it was actually run.
13. Never replace a failing integration with a fake production response.
14. Update progress and learning documents continuously.

Begin now by auditing the current repository, preserving useful existing code, creating `IMPLEMENTATION_STATUS.md`, and implementing Phase 1. Continue through the phases in order.
