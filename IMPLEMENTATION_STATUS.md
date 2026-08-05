# ODIRAG Implementation Status

Last updated: 2026-08-05

## Current Phase

- Phase: Phase 16 - Production readiness audit and autonomous source discovery
- Status: Local production-readiness fixes and fixture verification complete; external production acceptance pending
- Next Action: Recover the workstation Docker Desktop WSL data-disk mount, rebuild and scan the hardened local images, then attach target-environment evidence for real providers, representative source crawling, backup/restore, and production security configuration.

## Latest Verification Checkpoint

- 2026-08-05：Coze 批量抓取实现、数据库迁移 `0006_coze_task_operations`、失败 URL 重试、调用原始/规范化响应持久化、验收摘要 API 和前端任务详情已完成；本轮补齐共享 Redis 限流、显式 Local Provider worker 路径、可信代理边界、取消竞态保护、审核后 `waiting_review` 收敛、供应商 cost 防护、严格 Phase 16 事件顺序和镜像/SBOM 验收命令。
- 后端：`python -m pytest -q` 为 `210 passed`；Ruff、Black、mypy（154 个源码文件）通过；SQLite `0001 -> 0006 -> 0004 -> 0006` round-trip 和本地 PostgreSQL `alembic check` 通过。
- 前端：lint、type-check、Vitest `16/16`、Vite build（1850 modules）通过；Playwright 串行 `9 passed + 1 skipped`，跳过项仅为显式 `live-stack` 门禁。
- 依赖：`npm audit` 与 `npm audit --omit=dev` 均为 0 vulnerabilities，`npm ls --all` 无 invalid/extraneous 必需依赖；`pip --python backend/.venv check` 为 `No broken requirements found`。旧 backend 镜像扫描发现 2 critical/4 high，旧 frontend 镜像发现 6 critical/27 high；代码已改用 `python:3.12-alpine3.24` 与 `nginx:1.30.4-alpine` 并移除 runtime pip，但新镜像因 Docker Desktop WSL 数据盘挂载故障尚未完成重建/扫描，不能标为通过。
- 历史本地 Compose（旧基础镜像、当前应用代码）：PostgreSQL、Redis、Qdrant、backend、worker、scheduler、frontend、Nginx 曾全部 healthy；PostgreSQL head 为 `0006_coze_task_operations`，Redis PONG 且应用限流 key 写入共享 Redis，Qdrant health 200 但 collection 数为 0，数据库文档/分块/Coze invocation 数为 0。当前加固镜像的 Compose 状态为 UNVERIFIED。
- Coze live preflight：`/api/system/coze/status` 显示 disabled、token 未配置、batch workflow 未配置；`scripts/live_accept_coze_batch.py` 按设计退出码 `2`，状态 `batch_workflow_not_published`。没有伪造 live 成功。

## Assumptions

- The empty `D:\RAG` directory is the intended repository root.
- A repository-local Python 3.14.6 environment is used for checks; the package supports Python 3.11+.
- PostgreSQL remains the production business database; SQLite is permitted only for deterministic local tests and degraded development startup.
- External LLM, embedding, rerank, Qdrant, Redis, and live-site integrations must report unavailable until configured and must never return fabricated production results.
- The supplied master execution guide is the approved product design and phase plan.
- The required open-source license was selected as MIT because the guide mandates a LICENSE but does not prescribe a license family; this choice is recorded in `LICENSE` and can be changed before publication.

## Environment Audit

| Tool | Result |
| --- | --- |
| Repository contents | Empty at audit time |
| Python | 3.14.6 |
| Node.js | 24.18.0 |
| npm | 12.0.0 |
| Git | 2.52.0; initialized after audit, but sandboxed `.git` writes require elevation |
| Docker | Docker Compose v5.3.1; prior-image development stack was healthy; current engine is blocked by `WSL_E_USER_VHD_ALREADY_ATTACHED` and hardened images are unverified |
| ripgrep | 15.2.0 |

## Phase Checklist

| Phase | Status | Implemented Features | Commands Run | Test Results | Coverage | Known Issues | Blocked External Integrations | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Repository Audit | Complete | Empty-workspace audit; Git initialization; toolchain verification; assumptions recorded | `Get-ChildItem -Force`; version checks; `git init` | Audit complete | N/A | Production credentials/config and `.git` checkpoint writes remain restricted | Production runtime evidence | Preserve baseline |
| 1 - Infrastructure and Core Backend | Complete | FastAPI factory; settings; SQLAlchemy async database; all required core models; Alembic migration; JWT admin auth; structured errors/logging; metrics; dependency health; Celery bootstrap; Docker/CI/deployment baseline | Ruff; Black; mypy; pytest with coverage; SQLite migration; local PostgreSQL `alembic current/heads/check`; Uvicorn health smoke | 32 unit tests passed; migration passed; smoke endpoint passed; lint/type checks passed | 81.76% | Production secret manager, backup/restore, and production topology remain unverified | Production credentials and release environment | Implement Phase 2 vertical slice |
| 2 - Source Management and Crawling | Complete | YAML source configuration; source CRUD/test; adapter registry; generic HTML and gov.cn JSON adapters; URL normalization; retries/timeouts/rate control; task state machine; Celery dispatch; fixture pagination/detail/attachment path; idempotent document persistence | Ruff; Black; mypy; unit/integration tests; fixture smoke | 41 tests passed; lint/type checks passed; fixture end-to-end crawl passed | 80.48% | Live gov.cn page and JSON endpoint were identified, but the 10-article run was blocked by external approval quota | Live 10-article verification | Implement Phase 3 parsing pipeline |
| 3 - Parsing, Cleaning, Deduplication, Versioning | Complete | HTML structure/table extraction; PDF pages/header-footer reduction/OCR flag; DOCX headings/tables/hyperlinks; XLSX sheets/Markdown/JSON rows; TXT decoding; ZIP metadata/path flags; cleaning; SHA256; SimHash; authoritative duplicate selection; document snapshots; changed fields; stale indexes; lineage | Ruff; Black; mypy; unit/integration tests | 50 tests passed; parser samples and version/lineage integration passed | 80.64% | OCR execution is not bundled; documents are flagged for OCR | OCR engine | Implement Phase 4 review pipeline |
| 4 - Filtering, LLM Review, Structured Knowledge | Complete | Configurable hard/soft filtering and reason codes; prompt immutability/versioning; Direct and Coze adapters; strict JSON; three-attempt retry; raw responses; manual review; 12 allowed structured fields; evidence-quote binding; provenance metadata | Ruff; Black; mypy; unit/integration tests | 56 tests passed; retry/raw response/evidence/manual review integration passed | 82.88% | Live LLM calls not verified without credentials | Coze/direct LLM credentials | Implement Phase 5 indexing pipeline |
| 5 - Chunking, Embedding, Indexing | Complete | YAML-configured heading/paragraph/list/table-aware chunking with semantic fallback; document and parsed-attachment/page chunks; stable versioned UUID point IDs; batching, cache, retry, rate/cost metadata; Redis cache adapter; Qdrant collection creation, dimension validation, payload indexes, filters, idempotent upsert/deletion and retryable cross-store cleanup; chunk/vector lineage; JSON BM25 snapshots and rebuild command | Ruff; Black; mypy across 108 source files; unit/integration tests; SQLite Alembic smoke; `scripts/rebuild_bm25.py` smoke | 62 tests passed; cache/retry, attachment pages, idempotent reindex, failed cleanup recovery, Qdrant collection contract, BM25 round-trip and rebuild passed | 82.82% | Live Qdrant collection creation and remote embedding calls cannot run without services/credentials | Remote embeddings, Redis, Qdrant | Implement Phase 6 retrieval engine |
| 6 - Retrieval Engine | Complete | Shared provider runtime; BM25 snapshot loading; query normalization, term analysis and inferred/explicit metadata filters; BM25/vector/hybrid/hybrid+rerank modes; normalized BM25 scores; Qdrant and in-memory filter parity; bounded RRF; validated rerank outputs; thresholds/final context selection; stage timings, warnings and config snapshots; authenticated search and admin debug APIs; document reindex/chunk APIs connected to shared live indexes | Ruff; Black; mypy across 114 source files; unit/integration/API tests | 68 tests passed; all four retrieval modes, query analysis, filter validation, Qdrant upsert/query/delete/dimension contracts, reindex-to-search API flow and readable debug trace passed | 85.02% | Live remote rerank, embeddings and Qdrant execution require services/credentials | Remote embeddings, rerank, Redis, Qdrant | Implement Phase 7-8 routing and grounded answers |
| 7 - SQL / RAG / Composite Router | Complete | Deterministic query classification; inferred and explicit validated filters; SQLAlchemy-only approved-document count templates; no generated SQL; RAG and SQL+RAG execution; authenticated chat API | Ruff; Black; mypy; unit/integration/API tests | SQL, RAG, and composite routes passed including date/region filters and injection-resistant whitelist behavior | 85.11% shared checkpoint | Structured SQL support currently covers approved-document counts required by the guide example | None | Extend analytics only when verified use cases require it |
| 8 - Grounded Answering and Citations | Complete | Official-source requirement; question coverage; minimum evidence/score; policy-status conflict detection; newer-policy detection and outdated citation removal; refusal rules; extractive grounded answers; optional Direct/Coze generation; stored chunk-ID and URL validation; complete citation fields; persisted chat traces and trace API | Ruff; Black; mypy across 118 source files; unit/integration/API tests | 72 tests passed; refusals, conflicts, outdated evidence, exact citations, unknown chunk/URL rejection, SQL+RAG answer and trace persistence passed | 85.11% | Live Direct/Coze answer generation not run without credentials; extractive mode is fully operational | Direct/Coze credentials | Implement Phase 9 evaluation |
| 9 - Evaluation and Benchmark | Complete | Persisted manually verified questions; real ChatService-backed benchmark runner; document/chunk hit rate, Recall@1/5/10, MRR, nDCG@10, answer-point coverage, citation accuracy/completeness, refusal accuracy, explicitly scoped hallucination rate, P50/P95 latency, token and cost metrics; per-question errors; atomic JSON/CSV/Markdown/chart-ready reports; authenticated run/list/detail/report APIs; fixed local demo benchmark | Ruff; Black; mypy across 132 source files; full unit/integration suite; real reindex -> evaluation API integration | 83 tests passed; verified metrics and all four report artifacts generated from actual traces; no hard-coded metric values | 83.43% shared checkpoint | Hallucination measurement is explicitly limited to citation claims validated against stored chunk quotes; the demo benchmark uses document/answer-point relevance while chunk-specific relevance is covered by indexed API tests | Live LLM token/cost and provider behavior require configured credentials | Implement Phase 10 experiments |
| 10 - Experiments and Regression | Complete | Strict YAML experiment configuration; independent per-variant chunking, overlap, embedding, BM25/vector indexes, top-k, RRF, metadata filters, rerank, score threshold and prompt-version application; baseline/candidate evaluation runs linked to experiments; metric deltas, regression gates, failed cases and conclusions; atomic JSON/Markdown/chart reports; create/list/detail/run/compare APIs; trusted runner plugin loading; executable local demo runner | `python scripts/run_experiment.py --config data/experiments/chunk_600_vs_800.yaml`; Ruff; Black; mypy; unit/integration/API tests | Guide example command completed and produced real comparison artifacts; API regression test detected an intentionally degraded metadata-filter candidate | 83.43% shared checkpoint | Remote model variants fail honestly when credentials/providers are unavailable; generated experiment run artifacts are ignored by Git | Remote embedding, rerank and LLM credentials | Implement Phase 11 observability |
| 11 - Trace, Lineage, Monitoring, Alerts | Complete | Full query trace including prompt snapshots; answer-to-citation-to-chunk-to-document-version-to-crawl-task-to-source traversal; crawl and index lineage propagation; evaluation-run lineage for retrieved chunks; crawler, knowledge, RAG, dependency and cost metrics; persisted alerts for crawl failure, index failure, unavailable services, latency regression, evaluation regression and abnormal cost; acknowledge/resolve lifecycle; scheduled alert refresh | Ruff; Black; mypy across 136 source files; targeted observability/evaluation integration tests; full unit/integration suite; `alembic upgrade head` fresh-database smoke through `0002_observability_alerts` | 85 tests passed; lineage traversal, prompt snapshots, operational metrics, all six alert types, lifecycle transitions and evaluation-run lineage verified | 82.98% | Repeated refresh intentionally reopens an active condition after manual resolution; alert thresholds are environment-configurable | Live dependency availability and provider cost telemetry require configured services/credentials | Build Phase 12 Vue console |
| 12 - Vue Frontend | Complete | Vue 3 + TypeScript management console; typed API client; auth/session handling; dashboard, sources, crawl tasks, documents, review, chat/citations, evaluations, experiments, monitoring, activity, and source-discovery views; task acceptance summary and independent legacy/batch status rendering | npm lint; type-check; Vitest; production build; fixture Playwright; explicit live-stack gate | 16 Vitest tests passed; 9 fixture Playwright tests passed; 1 live-stack test explicitly skipped without `E2E_LIVE=1`; Vite build passed | N/A | Browser tests use deterministic local providers or route fixtures; live deployed stack remains unverified | Live external providers and container services | Run the live Playwright gate after external acceptance |
| 13 - Feedback Loop | Complete | Helpful/not-helpful feedback API; validation; feedback-to-verified-evaluation conversion; helpful feedback conflict guard; frontend feedback controls and activity integration; logout token revocation | Backend unit/integration suite; frontend Vitest; real browser feedback flow | Feedback persistence and conversion passed; positive-feedback conversion rejected with 409; logout behavior covered | 82.87% shared checkpoint | Positive feedback is intentionally not convertible to a regression case | None | Preserve feedback regression tests |
| 14 - Security, Reliability, Performance | Complete | Shared Redis fixed-window rate limiting with Lua-atomic counter/expiry and fail-closed 503; bounded Redis connect/read timeouts; IP-only identity with explicit trusted-proxy CIDRs; unified 429 responses; JWT token-version rotation/revocation; production configuration checks; SSRF-safe DNS and redirect validation; streamed response limits; atomic crawl task claims and stale recovery that excludes manual `waiting_review`; atomic local/Coze cancellation guards with CAS on both worker stages and cancel requests; Celery late-ack/recovery settings; crawl uniqueness migration; bounded route/DB latency metrics; authenticated load-test reports; frontend DB P95 and route latency views | Ruff; Black; mypy; 210-test full suite; rate-limit tests with fake Redis/proxy cases; migration smoke; frontend lint/type/test/build; authenticated async load test; mobile/desktop browser QA; local Compose Redis key/header check | 210-test full backend suite passed; Redis limiter contract, timeout propagation, forged-token resistance, trusted-proxy handling and fail-closed behavior passed; local and Coze cancellation race regressions passed, including stale-cancel CAS; waiting-review recovery and review convergence passed | Coverage baseline remains historical; live Redis ACL/failover and multi-instance fairness remain unverified | Production Redis ACL, failover, ingress policy and remote model providers remain unverified; generic distributed locks are still DB-based | Run target Redis failure/ACL/failover and multi-replica tests |
| 15 - Docker, CI/CD, Handoff | Complete in code; current hardened image verification blocked | Auto-migration/non-root writable backend image; persistent Compose dependencies; shared Redis rate-limit configuration; worker/scheduler health and migration ordering; real API demo initializer; startup scripts; CI/deployment/docs handoff; honest demo seed; Python 3.12 Alpine/Nginx 1.30.4 base-image hardening; runtime pip removal; builder/runtime SBOM and CVE checklist | `docker compose config`; historical prior-image Compose health; PostgreSQL/Redis/Qdrant checks; worker ping/task; scheduler logs; Nginx/frontend smoke; current full regression; shell LF attributes | `210` backend tests; `16` Vitest tests; `9` fixture Playwright passed and `1` live gate skipped; prior-image local Compose was healthy; hardened image rebuild/scan UNVERIFIED | Coverage baseline remains historical; this checkpoint did not regenerate coverage report | Docker Desktop currently fails with `WSL_E_USER_VHD_ALREADY_ATTACHED`; current image startup, critical/high CVE scan, production profile, persistence recovery, backup/restore, release provenance, signed tag and CI result remain unverified | Workstation WSL recovery; production credentials, target host, backup/restore, remote providers | Recover Docker without deleting the VHD, serially rebuild backend/frontend and builder stages, run Scout/SBOM with `local://` and `--exit-code`, then execute remaining live gates |
| 16 - Production Readiness and Autonomous Source Discovery | Complete in code; external acceptance pending | Content-gap detection; Brave official-site candidate discovery; HTTPS/official validation; column discovery; bounded trial crawl; quality scoring; manual approval/rejection; source activation; durable audit events; retry/queue failure compensation; Coze batch contract, raw/normalized invocation audit, failed URL retry, acceptance summary, explicit Local Provider worker path, atomic provider cancellation on both worker and API CAS paths, review-task convergence, accurate provider provenance, legacy boundary, finite/quantized LLM usage/cost propagation, Phase 16 APIs, frontend, migration, monitoring, docs, and learning material | Ruff; Black; mypy; 210 pytest tests; SQLite and PostgreSQL Alembic checks; historical prior-image local Compose health; frontend lint/type/Vitest/build; serial fixture Playwright; npm audit; pip dependency check | 210 backend tests passed; Local Provider and Coze cancellation regressions, stale-cancel CAS, waiting-review convergence, legacy-contract guard, Direct/Coze usage propagation and chat trace persistence passed; npm audit 0 vulnerabilities and pip dependency graph valid; prior-image local Compose services were healthy; Coze live preflight correctly returned exit 2 because no batch deployment/token is configured; scsia inline API remains structured 422 with failed task and 0 documents | Coverage report not regenerated in this checkpoint; remote providers and current hardened images remain unverified | Real Brave/Coze workflow, remote model providers, representative official-site crawl, OCR/image extraction, production Redis ACL/failover, hardened container CVE scan, and backup/restore remain unverified; Qdrant has no collection/points because no accepted document was indexed | Workstation WSL recovery; production credentials, real official-site crawl, token/cost telemetry, container scanner evidence, Git checkpoint | Rebuild/scan hardened images after WSL recovery, configure/publish the real batch Coze workflow, then execute remaining provider/source/live-browser gates; do not mark production accepted before all PASS-LIVE gates |

## Command Log

- `Get-ChildItem -Force`
- `python --version`
- `py -0p`
- `pip --version`
- `node --version`
- `npm --version`
- `docker --version`
- `docker compose version`
- `git --version`
- `git rev-parse --show-toplevel`
- `rg --version`
- `backend/.venv/Scripts/ruff.exe check app tests`
- `backend/.venv/Scripts/black.exe --check app tests`
- `backend/.venv/Scripts/mypy.exe app`
- `backend/.venv/Scripts/pytest.exe tests/unit -q --cov=app --cov-report=term-missing`
- `ODIRAG_DATABASE_URL=sqlite+aiosqlite:///./phase1-check.db alembic upgrade head`
- Uvicorn process smoke test against `GET /api/system/health`
- Phase 2 Ruff, Black, and mypy checks across 77 source files
- Phase 2 unit/integration suite: 41 passed, 80.48% coverage
- Fixture crawl smoke: list -> details -> attachment -> persistence -> repeated-run deduplication
- Phase 3 parser, cleaning, deduplication, versioning, and lineage suite: 50 passed, 80.64% coverage
- Phase 4 filtering, prompt, LLM review, manual review, and structured knowledge suite: 56 passed, 82.88% coverage
- Phase 5 Ruff and Black checks; mypy across 108 source files
- Phase 5 unit/integration suite: 62 passed, 82.82% coverage
- Phase 5 approved document -> attachment-aware chunks -> embeddings -> vector store -> BM25 snapshot integration
- Phase 5 SQLite migration plus `scripts/rebuild_bm25.py` command smoke
- Phase 6 Ruff and Black checks; mypy across 114 source files
- Phase 6 unit/integration suite: 68 passed, 85.02% coverage
- Phase 6 API smoke: approved document -> reindex -> BM25/vector/RRF/rerank -> debug trace
- Phase 7-8 Ruff and Black checks; mypy across 118 source files
- Phase 7-8 unit/integration suite: 72 passed, 85.11% coverage
- Phase 7-8 API smoke: SQL/RAG/composite chat -> evidence checks -> citations/refusal -> stored trace
- Phase 9-10 Ruff and Black checks across 159 application/test files; script checks passed
- Phase 9-10 mypy across 132 source files
- Phase 9-10 unit/integration suite: 83 passed, 83.43% coverage
- Phase 9 real demo API: approved document -> reindex -> verified questions -> actual chat traces -> JSON/CSV/Markdown/chart reports
- Phase 10 API: independent baseline/candidate indexes -> evaluation runs -> metric deltas -> regressions/failed cases/conclusion
- `backend/.venv/Scripts/python.exe scripts/run_experiment.py --config data/experiments/chunk_600_vs_800.yaml` completed with generated comparison artifacts
- Phase 11 fresh migration smoke: `0001_core_schema -> 0002_observability_alerts`
- Phase 11 targeted integration: prompt snapshot and complete answer lineage; operational metrics and six persistent alert types; evaluation-run-to-retrieved-chunk lineage
- Phase 11 Ruff and Black checks across 167 application/test/migration files; mypy across 136 source files
- Phase 11 unit/integration suite: 85 passed, 82.98% coverage
- Phase 12 frontend: lint, type-check, 6 Vitest tests, production build, and authenticated mobile/desktop browser QA
- Phase 13 feedback: persistence, negative-feedback conversion, helpful-feedback conflict, and logout revocation verification
- Phase 14 fresh migration smoke: `0001_core_schema -> 0002_observability_alerts -> 0003_crawl_reliability`, downgrade to `0002`, then re-upgrade
- Phase 14 backend suite: 119 passed, 82.87% coverage; Ruff/Black passed; mypy passed across 143 source files
- Phase 14 load test: 20 search and 20 chat requests at concurrency 4 with zero errors; search P95 29.49 ms, chat P95 345.95 ms, DB P95 183.83 ms
- Phase 14 monitoring browser QA: DB P95 and route P95 verified at 390x844 and 1280x720 with no horizontal overflow
- Phase 15 documentation audit: 26 required documents present; all 12 numbered learning documents contain the required 12 sections, five interview Q&A, five defense Q&A, code-reading route, and exercise; relative links and referenced project paths resolve
- Phase 15 seed smoke: default nested SQLite parent creation and idempotency passed; no fabricated chunks, traces, alerts, evaluation metrics, or completed experiment conclusions are inserted
- Phase 15 real deterministic demo: two approved documents -> six chunks -> BM25/vector runtime -> RAG chat -> stored citations/trace -> one-question evaluation report; Recall@1/5/10, MRR, nDCG, answer coverage, citation accuracy/completeness, and refusal accuracy all measured at 1.0; P50/P95 4 ms
- Phase 15 final backend regression: 120 passed, 82.89% coverage; frontend 6 tests passed and production build passed
- Phase 15 migration smoke: fresh `0001 -> 0002 -> 0003`, downgrade to `0002`, then re-upgrade to `0003` passed
- Phase 15 static deployment smoke: Compose service set and CI YAML parsed; PowerShell/shell startup and container entrypoint were syntax-checked
- Phase 16 backend static checks: Ruff passed; Black reported 205 files unchanged across app/tests/alembic; mypy passed for 154 source files
- Latest production-readiness full backend regression: 210 passed; coverage was not regenerated in this checkpoint
- Focused crawler/source regression: `tests/unit/test_sources_and_crawler.py`, 8 passed; unsafe inline crawl returns structured 422 and persists a failed task.
- Explicit Local Provider worker-contract fixture and legacy Coze column-task guard: 3 passed.
- Phase 16 targeted source-discovery/config/API checks: 28 passed
- Phase 16 Alembic SQLite round-trip: fresh upgrade to `0006_coze_task_operations`, downgrade to `0004_source_discovery`, re-upgrade to head passed; local PostgreSQL current/head/check is `0006_coze_task_operations (head)` with no drift.
- Phase 16 frontend: lint, type-check, 16 Vitest tests, Vite build (1850 modules) passed; task acceptance summary and independent legacy/batch status assertions included
- Phase 16 Playwright: serial 9 fixture tests passed, 1 live-stack test skipped without `E2E_LIVE=1`; concurrent first run had one worker-resource failure and was not used as the acceptance result.
- Phase 16 historical local Compose acceptance (previous base images): PostgreSQL/Redis/Qdrant/backend/frontend/Nginx/worker/scheduler were all healthy; Redis PONG, backend Redis ping=True, shared `odirag:ratelimit:*` keys, worker inspect ping and real `ping.delay()` passed; scheduler emitted recovery/monitoring tasks; Qdrant health passed but had zero collections; Nginx `/healthz`, `/`, and `/api/system/health` returned 200 with security headers. This evidence does not verify the current hardened images.
- Coze batch preflight: auth and `/api/system/coze/status` passed with all live flags false; `scripts/live_accept_coze_batch.py` returned exit code 2 / `batch_workflow_not_published` without creating a task.
- Phase 16 reports/checklist generated: `PRODUCTION_READINESS_REPORT.md` and `PRODUCTION_ACCEPTANCE_CHECKLIST.md`; production verdict remains NOT ACCEPTED pending live evidence
- scsia.org example: browser read-only inspection reached the notice/detail routes; source `1` and column `1` were created as an explicit association experiment, but backend DNS resolved `scsia.org` to `198.18.0.208`, so SSRF public-network validation rejected connectivity and inline crawl. Latest task `3` remained failed/retryable and no documents were persisted. The refreshed backend returned structured `422 CRAWL_SOURCE_UNSAFE` with a request ID.

## Known Issues

- Docker Desktop currently cannot mount its existing WSL data VHD (`WSL_E_USER_VHD_ALREADY_ATTACHED`). A targeted `wsl --terminate docker-desktop` succeeded, but subsequent WSL list/shutdown calls timed out and the managed environment could not restart `WslService`; destructive reset/prune was not used. The prior-image stack evidence remains historical, while the current hardened images are UNVERIFIED until a host reboot or administrator-controlled WSL service recovery, followed by a serial rebuild, succeeds.
- No external service credentials have been supplied.
- Git history contains implementation baseline `85d4bdb` and audit checkpoint `14bbf40`. A clean reviewed release checkpoint, signed release tag, CI result, SBOM and registry provenance remain release gates.
- The live 10-article gov.cn crawl could not be executed after the external approval service rejected further network access due zero quota; the adapter contract is covered by local tests.
- PDF pages with insufficient extracted text are flagged for OCR; no OCR engine is installed locally.
- Live Coze/direct LLM execution requires credentials; adapters and failure states are contract-tested without fabricated responses.
- Live Qdrant collection/index creation and remote embedding/cache calls remain unverified; historical local Qdrant health passed but no collection/points exist because the scsia crawl produced zero documents.
- Remote embedding, rerank, and LLM experiment variants remain unavailable without credentials; the committed demo benchmark uses deterministic local providers and labels that scope explicitly.
- API rate limiting uses the shared Redis-backed fixed-window limiter by default outside tests and fails closed when Redis is unavailable; target Redis ACL/failover, ingress policy, and multi-instance fairness remain unverified.
- The recorded load-test numbers are deterministic local engineering measurements and are not production capacity or SLA claims.
- The one-command Docker demo and prior-image local Compose health/startup ran on this workstation; worker/scheduler now reuse the single backend image build to avoid concurrent same-tag exports. The current hardened images need rebuild/health/CVE evidence after WSL recovery, and production persistence recovery, worker failure/retry drills, and Nginx TLS/ingress still need target-host evidence.
- A release candidate must be cut from a clean, reviewed checkpoint; create a signed release tag only after the external acceptance gates pass.
- `npm audit` and `npm audit --omit=dev` currently report zero vulnerabilities; this is registry advisory evidence, not a substitute for Python/container SBOM and CVE scanning.
- The local outbound proxy maps `scsia.org` to `198.18.0.208`; the backend intentionally rejects that non-public target. A target host with ordinary DNS or an explicitly approved proxy-aware egress path is required for live crawl acceptance. The detail pages are predominantly image resources, so selectors and OCR/image extraction still require validation.

## Blocked External Integrations

- Real Brave source discovery, Coze/direct LLM, remote embedding, and remote rerank verification require credentials and reachable endpoints.
- A representative real official-site crawl remains blocked by the local outbound proxy DNS mapping `scsia.org` to `198.18.0.208`; browser reachability does not imply backend crawler reachability.

## Reports and Acceptance

- [`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md): requirement-to-code matrix, fixture boundary, risks, and release gates.
- [`PRODUCTION_ACCEPTANCE_CHECKLIST.md`](PRODUCTION_ACCEPTANCE_CHECKLIST.md): exact target-environment commands and expected results.
