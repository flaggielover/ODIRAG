# ODIRAG Production Readiness Report

审计日期：2026-08-04  
审计基准：ODIRAG_CODEX_MASTER_EXECUTION_GUIDE.md（Phase 0-15；新增 Phase 16）  
结论：**NOT PRODUCTION ACCEPTED / 需要外部验收**

代码层面的 Phase 0-15 主流程和新增 Phase 16 已形成可运行实现，未发现 runtime TODO、FIXME、空函数、硬编码检索结果、硬编码仪表盘指标或伪造评估指标。本机 Docker Desktop 的开发 Compose 栈已真实启动并通过服务健康、PostgreSQL/Redis/Qdrant、worker、scheduler、Nginx 和 Alembic 检查；但自动化集成测试仍主要使用 SQLite、内存 cache/vector store 和确定性 embedding/rerank，外部 provider 只做协议级 test double 验证。因此本报告不能把生产 PostgreSQL 拓扑、Brave、Coze、远程 embedding/rerank 或 Direct LLM 标为生产通过。

## 1. 状态定义

| 状态 | 含义 |
| --- | --- |
| VERIFIED-LOCAL | 真实本地代码执行通过，不依赖伪造结果；只证明该本地边界 |
| FIXTURE-VERIFIED | SQLite、内存实现、确定性 provider、静态 HTML/文件或 Playwright route fixture 通过 |
| CONTRACT-VERIFIED | 使用 MockTransport/FakeClient 验证请求和响应契约，未连接真实服务 |
| PARTIAL | 核心实现存在，但指南的一部分缺失或只有降级路径 |
| UNVERIFIED-LIVE | 代码存在，但没有目标服务/真实凭据执行证据 |
| FAIL | 已执行且行为不符合要求 |

任何 FIXTURE-VERIFIED、CONTRACT-VERIFIED、PARTIAL 或 UNVERIFIED-LIVE 都不能转换为 PASS-LIVE。

## 2. 关键审计结论

1. **本机开发运行时已验证，生产运行时仍未验收。** `docker compose ps --all` 显示 backend、frontend、postgres、redis、qdrant、worker、scheduler、nginx 全部 healthy；PostgreSQL 查询、Redis PING/临时键、worker ping/task、scheduler 调度日志、Nginx 健康接口均通过。生产 secret、TLS、备份恢复、镜像 provenance 和故障演练仍无证据。
2. **测试真实性边界清晰但很窄。** backend/tests/conftest.py 统一使用 SQLite memory、InMemoryEmbeddingCache、InMemoryVectorStore、DeterministicEmbeddingProvider 和 DeterministicRerankProvider。
3. **远程模型均未 live 验证。** Direct LLM、Coze、remote embedding、remote rerank 和 Brave Search 使用 MockTransport/fixture 验证；没有真实 token、配额、延迟、限流或计费证据。
4. **LLM token/cost 仍为部分实现。** ChatService 将 token_usage_json 写为 measurement=not_available，cost 写为 0；这是诚实降级，不是伪造，但不满足真实 LLM token/cost 遥测验收。
5. **Coze 存在高风险契约假设。** CozeAdapter 假设 POST /v3/chat 的同步响应直接包含 answer messages；真实 Chat v3 可能需要轮询会话和单独读取消息，必须 live 验证后才能接受。
6. **多副本限流未完成。** 当前 InMemoryFixedWindowRateLimiter 只在单进程内原子；横向扩容前需要 Redis/ingress 共享限流。
7. **分布式锁为部分满足。** crawl/source-discovery 通过数据库条件 UPDATE、唯一约束和恢复任务避免重复 claim，但没有通用 Redis distributed lock。
8. **前端功能成立，但偏离指定依赖栈。** Vue 3/TypeScript/Vite/Vue Router、安全 Markdown 已实现；package.json 未使用指南列出的 Pinia、Axios、Element Plus/Naive UI、ECharts。现有 typed fetch/custom components 能工作，但属于架构偏差。
9. **配置文件结构不完全一致。** sites.yaml、filters.yaml、chunking.yaml、prompts 已使用；指南目标中的 knowledge_schema.yaml、retrieval.yaml、rerank.yaml、monitoring.yaml 不存在，相应参数主要通过环境变量/代码 schema 管理。
10. **真实站点抓取缺证据。** fixture crawl 覆盖分页、详情、附件和幂等；已完成 scsia.org 浏览器级侦察与人工协会来源记录，但 backend DNS 解析到 `198.18.0.208` 后被 SSRF guard 拒绝，0 fetched/0 documents；指南建议的可达真实站点至少 10 篇文章仍未执行。
11. **扫描 PDF 只有 OCR 标志。** requires_ocr 可追踪，但没有 OCR engine；这不违反 Phase 3 的“标志”要求，却限制扫描件生产覆盖。
12. **供应链验收未完成。** npm install 报告 2 个 high severity 提示，但 npm audit advisory 查询被网络策略拒绝，不能判定漏洞是否适用。
13. **Git 基线不可审计。** 当前仓库文件均为 untracked，缺少可复现 checkpoint commit/tag；这不影响本地测试，但阻止正式发布和差异追踪。

## 3. Phase 0-15 需求到代码追踪矩阵

### Phase 0 - Repository Audit

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| 检查现有文件、识别可复用代码、保留已有工作 | IMPLEMENTATION_STATUS.md；仓库审计日志 | 初始目录/工具链命令记录 | VERIFIED-LOCAL | 审计时目录为空，无法证明历史代码来源 |
| 创建持续更新的状态文档与 phase checklist | IMPLEMENTATION_STATUS.md | 文档结构检查 | VERIFIED-LOCAL | 最终状态须与本报告同步 |
| 记录假设 | IMPLEMENTATION_STATUS.md | 人工审阅 | VERIFIED-LOCAL | 假设需部署负责人确认 |
| 验证 Python、Node、Docker、Git | IMPLEMENTATION_STATUS.md | version 命令；Docker Compose health | VERIFIED-LOCAL | 生产主机版本、镜像 provenance 和发布权限仍需目标环境验收 |
| 每阶段 lint/type/test/checkpoint | IMPLEMENTATION_STATUS.md command log | 历史命令记录 | PARTIAL | 测试证据存在；没有 Git checkpoint commit |

### Phase 1 - Infrastructure and Core Backend

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| FastAPI application factory | backend/app/main.py | backend/tests/unit/test_core_api.py | FIXTURE-VERIFIED | 目标 ASGI/进程管理未压测 |
| Pydantic 环境配置与生产安全 gate | backend/app/config.py；.env.example | backend/tests/unit/test_config.py | VERIFIED-LOCAL | 外部 secret manager 未接入 |
| PostgreSQL + SQLAlchemy async | backend/app/database/*；backend/app/models/* | SQLite integration suite；local Compose PostgreSQL health/identity/count queries | VERIFIED-LOCAL | 生产规模事务、锁竞争、连接池耗尽和恢复未验收 |
| Alembic core migrations | backend/alembic/versions/0001_core_schema.py | SQLite round-trip；local PostgreSQL current/heads/check | VERIFIED-LOCAL | PostgreSQL 专用 downgrade/backup/restore 未执行 |
| Redis abstraction | backend/app/cache/embedding.py；backend/app/tasks/celery_app.py | local Redis PING/SET/GET/DEL；backend Redis ping；worker task | VERIFIED-LOCAL | ACL、持久化、故障转移和生产限流未验收 |
| 结构化日志与错误 | backend/app/logging.py；backend/app/errors.py | core API tests | FIXTURE-VERIFIED | 集中日志/PII 脱敏未在部署环境验证 |
| dependency health endpoint | backend/app/services/health.py；backend/app/api/routes/system.py | backend/tests/unit/test_core_api.py；`/api/system/health` real Compose response | VERIFIED-LOCAL | 只证明当前开发实例；生产网络/TLS/告警策略未验收 |
| admin auth/refresh/me | backend/app/security.py；services/auth.py；routes/auth.py | security/core API tests | FIXTURE-VERIFIED | 生产 hash、密钥轮换、外部身份源未 live 验证 |
| Compose/.env/Makefile/CI skeleton | docker-compose.yml；Makefile；.github/workflows/ci.yml | `docker compose config --quiet`；local Compose health | VERIFIED-LOCAL | GitHub Actions、生产镜像签名和发布凭证未验收 |
| 所有 Phase 0-15 core models/migrations | backend/app/models/*；0001-0004 migrations | model tests + SQLite migration | FIXTURE-VERIFIED | PostgreSQL constraints/index plans 未验证 |

### Phase 2 - Source Management and Crawling

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| YAML source configuration | config/sites.yaml；services/source_config.py | test_sources_and_crawler.py | FIXTURE-VERIFIED | 只验证样例配置 |
| Source CRUD/test | api/routes/sources.py；services/sources.py；repositories/sources.py | test_sources_and_crawler.py | FIXTURE-VERIFIED | PostgreSQL FK/cascade 未 live 验证 |
| generic crawler + adapter registry | crawler/generic.py；crawler/adapters.py；crawler/registry.py | test_crawler_adapters.py；test_fixture_crawl.py | FIXTURE-VERIFIED | 真实站点 DOM/反爬变化未知 |
| retry/timeout/rate/encoding/pagination/URL normalization | crawler/fetcher.py；crawler/urls.py；crawler/generic.py | crawler/http security tests | FIXTURE-VERIFIED | DNS、代理、TLS、真实限流未验收 |
| task state machine + inline/async execution + retry/cancel + structured unsafe-URL error | crawler/state.py；services/crawl.py；tasks/crawl.py；routes/crawl_tasks.py | test_tasks.py；test_crawl_reliability.py；queue failure regression；test_inline_crawl_unsafe_url_returns_structured_error；local worker ping/task | FIXTURE-VERIFIED | 真实站点仍被 DNS/SSRF 阻断；queued task 只持久化异常类名，尚无独立 error-code 字段 |
| queue failure 可恢复 | services/crawl.py；routes/crawl_tasks.py | test_crawl_queue_failure_is_persisted_and_retryable | FIXTURE-VERIFIED | Redis broker outage live 未演练 |
| raw HTML/list/detail/attachment download | services/crawl.py；crawler/storage.py | test_fixture_crawl.py | FIXTURE-VERIFIED | 仅 fixture 站点；下载存储为本地卷 |
| HTML/PDF/DOCX/XLSX/TXT/ZIP 类型入口 | parsers/*；allowed attachment extensions | parser unit suite | FIXTURE-VERIFIED | full crawl fixture 主要覆盖 HTML/TXT；其他格式单独测试 |
| repeated-run idempotency | repositories/crawl.py；services/crawl.py；0003 migration | test_fixture_crawl.py；test_crawl_reliability.py | FIXTURE-VERIFIED | 多 worker + PostgreSQL 并发未验收 |
| 可达真实站点至少 10 篇 | scsia.org 仅完成浏览器侦察；backend 0 fetched、0 documents | 无成功抓取证据 | UNVERIFIED-LIVE | 上线前必须补 live crawl 报告 |

### Phase 3 - Parsing, Cleaning, Deduplication, Versioning

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| HTML headings/paragraphs/lists/tables/boilerplate | parsers/html.py；cleaners/text.py | test_parsers_cleaning_dedup.py | FIXTURE-VERIFIED | 复杂真实模板未知 |
| PDF pages/header-footer/OCR flag | parsers/pdf.py | parser tests/sample files | FIXTURE-VERIFIED | OCR engine 未实现；扫描件只标记 |
| DOCX headings/tables/hyperlinks | parsers/docx.py | parser tests | FIXTURE-VERIFIED | 大文件/损坏文件未压测 |
| XLSX sheets/headers/Markdown/JSON/row split | parsers/xlsx.py | parser tests | FIXTURE-VERIFIED | 宏、公式、超大 workbook 未覆盖 |
| canonical URL/SHA256/SimHash near dedup | crawler/urls.py；deduplication/core.py；services/versioning.py | algorithms/parser tests | VERIFIED-LOCAL | 中文短文本阈值需真实数据校准 |
| authoritative source selection | deduplication/core.py | test_parsers_cleaning_dedup.py | VERIFIED-LOCAL | 优先级规则需业务复核 |
| change detection/version/stale/changed fields | services/versioning.py；services/document_index.py | test_versioning_lineage.py；test_read_support_api.py | FIXTURE-VERIFIED | Qdrant 删除只在 memory store 通过 |
| lineage records | models/observability.py；services/versioning.py | lineage integration tests | FIXTURE-VERIFIED | PostgreSQL cascade/审计保留期未验证 |

### Phase 4 - Filtering, LLM Review, Structured Knowledge

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| hard reject/soft score/reason codes/thresholds | filters/rules.py；config/filters.yaml | test_filters_prompts_llm.py | VERIFIED-LOCAL | 阈值只在样例数据校准 |
| versioned immutable prompts | services/prompts.py；config/prompts/* | prompt tests | FIXTURE-VERIFIED | 生产 prompt 发布流程未验收 |
| Coze adapter | llm/adapters.py | MockTransport contract tests | CONTRACT-VERIFIED | Chat v3 异步/消息获取未 live 验证 |
| Direct LLM adapter | llm/adapters.py | MockTransport contract tests | CONTRACT-VERIFIED | provider 方言、限流、计费未知 |
| strict JSON/retry/raw response | llm/protocols.py；services/review.py | filter/LLM + review integration tests | FIXTURE-VERIFIED | 真实模型 schema 稳定性未知 |
| manual review state/API | routes/reviews.py；services/review.py | test_review_pipeline.py | FIXTURE-VERIFIED | 操作审计身份仅 admin |
| 12 个结构字段 + evidence/provenance | config/prompts/document_review_v1.txt；models/document.py；services/review.py | review integration tests | FIXTURE-VERIFIED | 真实模型抽取准确率未评估 |

### Phase 5 - Chunking, Embedding, Indexing

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| heading/paragraph/list/table chunking + fallback | chunking/heading.py；config/chunking.yaml | test_indexing_components.py | VERIFIED-LOCAL | token estimator 简化，真实模型窗口需校准 |
| target/min/max/overlap configurable | config/chunking.yaml；app/config.py | chunker/config tests | VERIFIED-LOCAL | 配置热更新未实现 |
| embedding protocol/remote/deterministic | embedding/providers.py | deterministic tests + MockTransport | CONTRACT-VERIFIED | remote provider 未 live 验证 |
| batching/cache/retry/rate/model/version/cost metadata | embedding/batcher.py；cache/embedding.py | indexing/provider tests | FIXTURE-VERIFIED | Redis 和真实 provider cost 未验收；cost 是配置估算 |
| Qdrant collection/index/upsert/delete/reindex/version | vector_store/store.py；services/indexing.py；document_index.py | FakeClient + memory integration | CONTRACT-VERIFIED | 真 Qdrant schema、持久化、删除补偿未验收 |
| BM25 index/rebuild/snapshot | bm25/index.py；services/bm25.py；scripts/rebuild_bm25.py | BM25 round-trip/integration | VERIFIED-LOCAL | snapshot 多实例同步与锁未解决 |

### Phase 6 - Retrieval Engine

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| query analysis + metadata filters | retrieval/analysis.py；router/query_router.py | test_retrieval_phase6.py | VERIFIED-LOCAL | 实体/同义词覆盖有限 |
| BM25 top-k + vector top-k | retrieval/engine.py；bm25/index.py；vector_store/store.py | retrieval/search tests | FIXTURE-VERIFIED | vector 路径为 memory/deterministic |
| RRF | retrieval/rrf.py | algorithm/retrieval tests | VERIFIED-LOCAL | 参数需生产数据校准 |
| rerank + validation | rerank/providers.py；retrieval/engine.py | deterministic + MockTransport tests | CONTRACT-VERIFIED | remote rerank 未 live 验证 |
| score threshold/final context | retrieval/engine.py | retrieval tests | FIXTURE-VERIFIED | 阈值非生产校准 |
| BM25/vector/hybrid/hybrid+rerank 四模式 | schemas/search.py；retrieval/engine.py | test_retrieval_phase6.py；test_search_api.py | FIXTURE-VERIFIED | PostgreSQL/Qdrant provider 组合未跑 |
| readable POST /api/search/debug trace | routes/search.py | test_search_api.py | FIXTURE-VERIFIED | trace 大小/敏感字段生产策略未验证 |

### Phase 7 - SQL/RAG/Composite Router

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| SQL/RAG/SQL+RAG classification | router/query_router.py | test_chat_grounding.py | VERIFIED-LOCAL | 规则分类器覆盖面有限 |
| safe SQL templates/query builder | repositories/chat.py；services/chat.py | search/chat integration tests | FIXTURE-VERIFIED | 目前结构化查询只覆盖 approved document count |
| 禁止 unrestricted LLM SQL | router/repository boundary | injection-related security tests | VERIFIED-LOCAL | 新增 SQL 用例必须继续白名单化 |
| 指南三个示例路由 | router tests + chat API | test_chat_grounding.py；test_search_api.py | FIXTURE-VERIFIED | SQLite 语义，不是 PostgreSQL 验收 |

### Phase 8 - Grounded Answering, Conflict, Refusal, Citations

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| evidence sufficiency/question coverage | rag/grounding.py | test_chat_grounding.py | VERIFIED-LOCAL | coverage heuristic 需真实问答评估 |
| official source validation | rag/grounding.py | grounding tests | FIXTURE-VERIFIED | official_status 数据质量依赖来源治理 |
| contradiction detection | rag/grounding.py | grounding tests | FIXTURE-VERIFIED | 规则级冲突，不是完整语义推理 |
| newer/outdated policy handling | rag/grounding.py | grounding tests | FIXTURE-VERIFIED | 日期缺失和跨来源优先级风险 |
| refusal rules | rag/grounding.py；services/chat.py | grounding/search API tests | FIXTURE-VERIFIED | 真实 LLM 仍需拒答回归 |
| citation stored identity/title/source/date/URL/page/quote | rag/grounding.py；repositories/chat.py | chat/search/lineage tests | FIXTURE-VERIFIED | PostgreSQL/Qdrant 一致性未 live 验证 |
| LLM 不得生成 URL | services/chat.py；rag/grounding.py | unknown chunk/URL rejection tests | FIXTURE-VERIFIED | remote LLM live 未验收 |

### Phase 9 - Evaluation and Benchmark

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| manually verified questions schema | models/evaluation.py；schemas/evaluation.py | evaluation unit/API tests | FIXTURE-VERIFIED | demo question 数量很小 |
| Recall@1/5/10、MRR、nDCG、doc/chunk hit | evaluation/metrics.py | test_evaluation_phase9.py | VERIFIED-LOCAL | 生产数据集未运行 |
| answer coverage/citation accuracy/completeness/refusal | evaluation/metrics.py；runner.py | evaluation tests | FIXTURE-VERIFIED | hallucination 仅验证 citation claims |
| hallucination rate | evaluation/metrics.py | evaluation tests | PARTIAL | 定义范围有限，非自由文本事实核验 |
| P50/P95 latency | evaluation/metrics.py；reports.py | deterministic benchmark | FIXTURE-VERIFIED | 本地毫秒值不是生产容量 |
| tokens/cost | models/query trace；services/chat.py | persistence tests | PARTIAL | LLM usage 固定记录 not_available，cost=0 |
| JSON/CSV/Markdown/chart-ready reports | evaluation/reports.py | evaluation report tests | VERIFIED-LOCAL | artifact store 仅本地文件 |
| demo data real evaluation path | data/evaluation/*；scripts/seed_demo.py | test_evaluation_api.py；test_demo_seed.py | FIXTURE-VERIFIED | demo/确定性 provider，不是 live provider benchmark |
| 禁止硬编码 metric values | evaluation runner/metrics | tests compare calculated outputs | VERIFIED-LOCAL | 需 code review 保持 |

### Phase 10 - Experiment Framework and Regression

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| chunk size/overlap variants | experiments/config.py；experiments/odirag.py | experiment unit/API tests | FIXTURE-VERIFIED | 仅小数据 |
| embedding model/top-k/RRF/filter/rerank/threshold/prompt variants | experiments/*；data/experiments/* | test_experiments_phase10.py | FIXTURE-VERIFIED | remote variants 未 live 执行 |
| executable run_experiment command | scripts/run_experiment.py | historical command + unit tests | VERIFIED-LOCAL | trusted runner plugin 需供应链控制 |
| comparison reports | experiments/reports.py | experiment tests | VERIFIED-LOCAL | artifacts 本地文件 |
| regressions/failed cases/conclusion | experiments/comparison.py | degraded candidate integration test | FIXTURE-VERIFIED | gate 阈值需业务确认 |

### Phase 11 - Trace, Lineage, Monitoring, Alerts

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| full query trace through retrieval/prompt/answer/citation/refusal/latency | services/chat.py；models/observability.py | search/chat/lineage tests | PARTIAL | token/cost 不是真实 provider 遥测 |
| answer→citation→chunk→version→crawl→source traversal | repositories/observability.py；routes/chat.py | test_versioning_lineage.py | FIXTURE-VERIFIED | PostgreSQL join/cascade 未 live 验证 |
| crawler/knowledge/RAG/dependency/cost metrics | metrics.py；services/observability.py | test_metrics.py；monitoring tests | FIXTURE-VERIFIED | 多实例聚合/Prometheus 未实现 |
| 六类 persisted alerts | services/observability.py；tasks/monitoring.py | test_monitoring_alerts.py | FIXTURE-VERIFIED | 样本为 deterministic/synthetic |
| scheduled refresh + lifecycle | tasks/celery_app.py；routes/system.py | test_tasks.py；monitoring tests | CONTRACT-VERIFIED | Celery beat live 未执行 |

### Phase 12 - Vue Frontend

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| Dashboard/Sources/Crawl/Documents/Detail/Review/Chat/Evaluation/Experiments/Monitoring/Feedback | frontend/src/views/*；router/index.ts | Vitest + Playwright fixture suite | FIXTURE-VERIFIED | 真实生产栈浏览器未验收 |
| real API-connected pages | frontend/src/api/client.ts；resources.ts | 本地无拦截 live-stack against SQLite/deterministic | FIXTURE-VERIFIED | 不是 PostgreSQL/Qdrant/remote provider |
| no hard-coded metrics | DashboardView.vue；MonitoringView.vue；resources.ts | static audit + fixture contract | VERIFIED-LOCAL | fixture metrics 仅存在 e2e tests |
| typed API clients | frontend/src/api/types.ts；resources.ts | vue-tsc | VERIFIED-LOCAL | 使用 fetch，不是指南指定 Axios |
| loading/error states/accessibility | components/AsyncState.vue；views/* | Playwright critical journeys | FIXTURE-VERIFIED | 完整 WCAG 审计未执行 |
| responsive design | frontend/src/styles/*；layouts/* | 历史 mobile/desktop QA | FIXTURE-VERIFIED | 当前轮未做全页视觉基线 |
| safe Markdown | marked + DOMPurify usage | frontend tests/static audit | VERIFIED-LOCAL | CSP 仍依赖部署入口 |
| 指定 Pinia/Axios/UI kit/ECharts | frontend/package.json | dependency audit | PARTIAL | 四类依赖未采用；属于指南架构偏差 |
| Playwright critical journeys | frontend/e2e/*.spec.ts；playwright.config.ts | 串行 9 passed；live-stack 1 skipped；Coze fixture 2 passed | FIXTURE-VERIFIED | 真实外部 provider/live-stack gate 待目标环境 |

### Phase 13 - Feedback Loop

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| helpful/not helpful + 五类问题反馈 | schemas/feedback.py；services/feedback.py | test_feedback_api.py；Playwright chat | FIXTURE-VERIFIED | 用户角色只有 admin |
| verified feedback → evaluation question | services/feedback.py；repositories/feedback.py | feedback integration tests | FIXTURE-VERIFIED | “verified”依赖当前管理员操作，无双人复核 |
| frontend feedback/logs | ActivityView.vue；ChatView.vue | Vitest + Playwright | FIXTURE-VERIFIED | 生产事件量分页/性能未验收 |

### Phase 14 - Security, Reliability, Performance

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| authentication/authorization/token revoke | security.py；dependencies.py；services/auth.py | security/auth tests | FIXTURE-VERIFIED | 外部 IdP/RBAC 未实现 |
| rate limiting | rate_limit.py | test_rate_limit.py | PARTIAL | 单进程 limiter，水平扩容不安全 |
| file limits/allowlist/path safety | crawler/storage.py；fetcher.py；config.py | HTTP/storage security tests | FIXTURE-VERIFIED | 恶意压缩包资源消耗需额外沙箱 |
| SQL injection protection | safe repository templates | security/router tests | VERIFIED-LOCAL | 新查询需持续审查 |
| XSS/CORS/secrets/error codes | DOMPurify；CORSMiddleware；config.py；errors.py | frontend/static/config/API tests | FIXTURE-VERIFIED | CSP/TLS/secret manager 未 live 验收 |
| retries/timeouts/idempotency | fetcher/services/indexing/crawl | reliability tests | FIXTURE-VERIFIED | 外部故障组合未演练 |
| distributed locks | conditional DB UPDATE；unique constraints | concurrency-oriented SQLite tests | PARTIAL | 无共享 Redis lock；SQLite 不等于 PostgreSQL 并发 |
| cache/batch embedding | cache/embedding.py；embedding/batcher.py | memory cache tests | FIXTURE-VERIFIED | Redis/remote provider 未 live |
| task recovery | tasks/recovery.py；0003 migration | test_crawl_reliability.py | FIXTURE-VERIFIED | worker kill/visibility timeout 未 live 演练 |
| migration/backup documentation | DEPLOYMENT.md；SECURITY.md | doc audit | VERIFIED-LOCAL | 未执行真实 backup/restore |
| lightweight load test + actual metrics | scripts/load_test.py；performance.py | deterministic local run | FIXTURE-VERIFIED | 不是生产容量/SLA；外部依赖为空 |
| search/chat/DB P95 goals | data/load-tests ignored artifacts；IMPLEMENTATION_STATUS.md | 20+20 local deterministic requests | FIXTURE-VERIFIED | 需生产规模重跑 |

### Phase 15 - Docker, CI/CD, Open-source Handoff

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| backend/frontend/postgres/redis/qdrant/worker/scheduler/nginx services | docker-compose.yml；Dockerfiles；deployment/*.conf | `docker compose ps --all`；health checks；Nginx `/healthz` and frontend HTML | VERIFIED-LOCAL | 当前为 development 配置；生产 TLS、持久化恢复、镜像 digest 和故障演练未验收 |
| optional prometheus/grafana | 无 | 无 | PARTIAL | 指南允许 if feasible，不是核心 blocker |
| backend lint/type/test/coverage CI | .github/workflows/ci.yml | YAML parse；本地等价命令 | CONTRACT-VERIFIED | GitHub Actions 未实际跑 |
| frontend lint/test/build/Playwright CI | .github/workflows/ci.yml | YAML parse；本地 npm commands | CONTRACT-VERIFIED | Actions/浏览器镜像未实际跑 |
| Docker build CI | .github/workflows/ci.yml | static definition | UNVERIFIED-LIVE | 镜像 build 未在本机执行 |
| README/architecture/API/eval/experiments/deployment/security/contribution/roadmap/license | 根目录文档 | link/path/structure audit | VERIFIED-LOCAL | 需随最终测试结果同步 |
| honest demo seed | scripts/seed_demo.py；data/evaluation/* | test_demo_seed.py；deterministic pipeline | FIXTURE-VERIFIED | demo URLs/data 不代表真实来源 |
| one-command startup | scripts/start_demo.ps1；scripts/start_demo.sh | local Compose build/start and health | VERIFIED-LOCAL | 生产环境变量、备份恢复和发布流程未实测 |
| 12+ learning/defense docs | docs/learning/*；docs/*.md | structure audit | VERIFIED-LOCAL | Phase16 learning doc另行新增 |
| release/checkpoint history | .git | git status | FAIL | 所有文件 untracked，无 commit/tag |

## 4. Required API Surface

OpenAPI 生成结果包含指南要求的 auth、sources、crawl-tasks、documents（含 PUT/DELETE/reparse/attachments/versions/lineage）、reviews、search/chat、evaluations/experiments、feedback 和 system endpoints。新增 document mutation 在 services/document_index.py 中同步清理向量和重建 BM25，并由 test_read_support_api.py 覆盖；真实性边界仍是 SQLite + InMemoryVectorStore。

状态：**FIXTURE-VERIFIED**。风险：未在 PostgreSQL/Qdrant 上验证 DELETE/PUT/reparse 的跨存储补偿和事务失败路径。

## 5. 占位、mock、硬编码和 demo 审计

执行了针对 TODO、FIXME、pass、NotImplementedError、placeholder、mock、demo、固定 metrics 和异常吞噬的全仓检索。

- runtime app 目录没有 TODO、FIXME、NotImplementedError 或空 pass。
- Alembic script.py.mako 中的 pass 是“空迁移模板”生成表达式，不是 runtime required functionality。
- Protocol 方法体使用 ...，属于类型接口声明，不是空实现。
- tests 中的 MockTransport、FakeClient、fixture 和 vi.mock 均限定在测试目录。
- DeterministicEmbeddingProvider、DeterministicRerankProvider、InMemoryEmbeddingCache、InMemoryVectorStore 明确为 test/demo；staging/production 配置现在拒绝这些 provider。
- NoRerankProvider 是指南要求的显式 no-rerank mode；检索 trace 会写 rerank_provider_disabled warning。
- DisabledCandidateDiscoveryProvider 显式返回 provider unavailable，不伪造候选。
- scripts/seed_demo.py 使用 demo 数据和 demo URL，只在显式 demo/seed 路径使用；测试确认它不会预填 chunks、trace、alert 或虚假评估结论。
- Dashboard/Monitoring 数据来自 API；硬编码指标只出现在 Playwright fixture 中。
- ChatService 的 token not_available 和 cost=0 是未实现遥测的诚实标识；生产报告将其列 PARTIAL，而不是将零解释为真实计费成功。

## 6. 仅在 SQLite / fixture / fake provider 验证的功能

| Boundary | Current evidence | Not proven |
| --- | --- | --- |
| 所有 backend integration tests | SQLite in-memory via backend/tests/conftest.py | PostgreSQL SQL/JSONB/locking/pool behavior |
| embedding | deterministic SHA256 vectors；remote MockTransport | remote auth/quota/dimension/cost/latency |
| rerank | deterministic token overlap；remote MockTransport | remote score contract/rate limits |
| vector store | InMemoryVectorStore；Qdrant FakeClient | real collection/index/persistence/delete/backup |
| cache | InMemoryEmbeddingCache；local Redis connectivity only | Redis-backed cache TTL/ACL/persistence/failure behavior |
| crawling | static fixture site + MockTransport；scsia browser-only inspection + backend SSRF rejection | real DNS/TLS/robots/anti-bot/10-article crawl |
| LLM | Direct/Coze MockTransport | real model JSON stability, Coze async lifecycle, token/cost |
| evaluation/experiments/load | tiny deterministic demo | representative corpus, production latency/cost/quality |
| frontend E2E | Playwright route fixtures；local SQLite/deterministic 无拦截 smoke；Nginx/frontend HTTP smoke | deployed HTTPS、真实内容/引用、remote provider |
| worker/scheduler | Celery task registration/schedule config tests；local worker ping/task and scheduler logs | queued crawl/source-discovery completion、故障恢复和生产 beat 长期运行 |
| containers/CI | local Docker build/start and health；Compose static checks | GitHub Actions run、生产镜像签名/SBOM和恢复演练 |

## 7. Phase 16 - Autonomous Source Discovery

原仓库缺少完整来源池扩展工作流，因此新增 Phase 16。实现链路严格为：

content gap detection → candidate official-site discovery → official-status validation → column discovery → bounded trial crawl → quality scoring → manual approval → source activation

| Requirement | Implementation files | Tests | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| content gap detection | services/source_discovery.py；repositories/source_discovery.py | test_source_discovery_stops_when_database_coverage_has_no_gap | FIXTURE-VERIFIED | ILIKE topic 匹配较简单，真实语义缺口需校准 |
| candidate official-site discovery | source_discovery/providers.py；config.py | test_source_discovery.py | CONTRACT-VERIFIED | Brave token/配额/真实结果未验证 |
| official validation | services/source_discovery.py；crawler/fetcher.py | unverified-domain integration test | FIXTURE-VERIFIED | suffix/HTTPS/marker policy可能误判；需业务白名单 |
| column discovery | services/source_discovery.py | fixture workflow test | FIXTURE-VERIFIED | selector heuristics对 JS 网站有限 |
| trial crawl | services/source_discovery.py | fixture workflow test | FIXTURE-VERIFIED | 只抓 bounded HTML；真实反爬/附件未验证 |
| quality scoring | services/source_discovery.py；config thresholds | source discovery integration tests | FIXTURE-VERIFIED | 权重是启发式，未用生产标注集校准 |
| manual approve/reject | routes/source_discovery.py；repository atomic update | integration + Playwright tests | FIXTURE-VERIFIED | 只有 admin，没有双人审批 |
| activation to Source/SourceColumn | services/source_discovery.py；models/source.py | integration + Playwright tests；activation compensation test | FIXTURE-VERIFIED | PostgreSQL uniqueness/并发未 live；激活后不自动启动 crawl；异常补偿路径尚未在真实 PostgreSQL 演练 |
| queue/worker/retry | tasks/source_discovery.py；celery_app.py | queue failure + retry reuse tests；local worker ping/task and scheduler logs | FIXTURE-VERIFIED | 真实 source-discovery queued run、故障恢复和长期 beat 仍未验收 |
| database migration | 0004_source_discovery.py；0005_coze_crawl_provider.py；0006_coze_task_operations.py；models/source_discovery.py；models/source.py | SQLite 0001→0006 upgrade/downgrade/re-upgrade；local PostgreSQL current/heads/check | VERIFIED-LOCAL | PostgreSQL 专用 downgrade/backup/restore 未执行 |
| APIs | routes/source_discovery.py；schemas/source_discovery.py | test_source_discovery_api.py | FIXTURE-VERIFIED | production rate/authorization角色有限 |
| frontend | SourceDiscoveryView.vue；typed API/router/nav | source-discovery.spec.ts | FIXTURE-VERIFIED | live Brave workflow浏览器验收缺失 |
| monitoring/audit | source_discovery_events；metrics API/UI | metrics/events integration + Playwright | FIXTURE-VERIFIED | 未接入全局 Alert rule |
| docs/learning | API.md/ARCHITECTURE.md/DEPLOYMENT.md 等；docs/learning/13_source_discovery.md | doc structure audit | VERIFIED-LOCAL | 学习材料已生成；仍需将目标环境证据回填 |

Brave 被选为当前 live provider，因为 Microsoft 已宣布 Bing Search APIs 于 2025-08-11 完全退役。实现不再依赖退役 endpoint；Brave 仍只为 contract-verified。参考：[Microsoft Bing Search API retirement](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)、[Brave Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get)。

## 8. 修复内容

本轮审计中修复了以下生产缺陷，而非增加无关功能：

- 补齐指南要求但缺失的 document PUT、DELETE、reparse、attachments、versions、lineage API。
- document PUT/reparse/delete 清理历史 Qdrant point IDs、标 stale 并重建/原子保存 BM25；PUT 创建不可变版本/lineage，拒绝未知字段。
- crawl task 入队失败不再永久 pending，改为持久 failed、记录 error type 并允许 retry。
- production Compose 的空 optional secret 可规范化为 None，同时仍拒绝非空明文 admin password。
- staging/production 拒绝 deterministic embedding/rerank、memory cache/vector store 和 deterministic source discovery。
- Phase16 retry 复用并重置同一候选，避免 unique constraint 造成重试死路。
- Phase16 activation 异常或 IntegrityError 会回滚并将候选置为 failed，写入 `source_activation_failure` 审计事件，避免永久停留在 activating。
- production Brave source-discovery endpoint 限制为官方 `https://api.search.brave.com` host，避免把 API key 发送到任意配置地址。
- Bing provider 被替换为仍可用的 Brave Search API。
- 新增 fixture-backed Playwright 和显式 E2E_LIVE live gate，并接入 CI。
- inline crawl 的 `UnsafeUrlError` 现在映射为 `422 CRAWL_SOURCE_UNSAFE` 并返回 task ID/error type，底层任务保持 failed/retryable；未知异常仍交由全局 `500 INTERNAL_ERROR` 处理，避免把数据库故障或程序缺陷误分类为上游服务故障。
- 对齐 `QueryTrace.prompt_snapshot_json` 与 `Alert.details_json` 的 ORM `server_default` 和 `0002` 迁移定义，修复 PostgreSQL `alembic check` 检出的 default drift。

## 9. 最终本地验证

以下结果已在本次审计结束时重新执行并记录：

| Check | Result | Boundary |
| --- | --- | --- |
| `backend/.venv/Scripts/ruff.exe check app tests` | PASS | 本地源代码/测试静态检查 |
| `backend/.venv/Scripts/black.exe --check app tests` | PASS；190 files unchanged | 本地格式检查 |
| `backend/.venv/Scripts/mypy.exe app` | PASS；152 source files | 本地类型检查 |
| `backend/.venv/Scripts/python.exe -m pytest -q` | PASS；183 passed | SQLite、内存实现、确定性 provider；覆盖率本轮未重新生成报告 |
| `backend/.venv/Scripts/pytest.exe tests/unit/test_sources_and_crawler.py -q` | PASS；8 passed | fixture；含 unsafe inline crawl 结构化错误 |
| Phase 16/config/API 定向测试 | PASS；28 passed | fixture/contract |
| Alembic fresh upgrade → downgrade → upgrade | PASS；最终 `0006_coze_task_operations (head)`；SQLite 和本地 PostgreSQL `check` 均无 drift | SQLite/PostgreSQL round-trip；未做生产 backup/restore |
| frontend lint/type-check/Vitest/build | PASS；13 Vitest tests，Vite 1850 modules | 本地 Node toolchain |
| Playwright fixture suite | PASS；串行 9 passed，1 live test skipped | route fixture；live gate 未开启 |
| local no-intercept `live-stack.spec.ts` | PASS；1 passed | 本地 SQLite + deterministic providers，不是生产验收 |
| local Docker Compose service/worker/scheduler acceptance | PASS；8 services healthy；worker ping/task 成功；scheduler 发送 recovery/monitoring tasks | development Compose；不等于生产发布验收 |
| local PostgreSQL `alembic current/heads/check` | PASS；`0006_coze_task_operations (head)`；No new upgrade operations detected | 当前开发数据库；未做生产 downgrade/backup/restore |
| Coze batch live preflight | PASS-EXPECTED；`GET /api/system/coze/status` 显示 disabled/unconfigured；脚本退出码 2、`batch_workflow_not_published` | 没有批量部署 URL/token；不是 Live 成功 |

### scsia.org 实验记录（非 PASS-LIVE）

该实验明确区分了“浏览器能打开”与“后端能安全抓取”：

- 浏览器只读检查通过：`https://scsia.org/Industry_information/Industry_information_1` 可打开通知列表并观察到 69 条记录，详情路由可定位；详情正文主要是上传图片，HTML 文本为空，因此不能把页面可视化内容直接当作已解析文本。
- 本地 API 创建了显式协会实验来源（`source_id=1`、`column_id=1`、`official_status=association`），没有绕过 Phase 16 的官方来源校验，也没有把协会域名标记为政府官方站点。
- `POST /api/sources/1/test` 返回 `reachable=false`、`error_type=UnsafeUrlError`；本机 DNS 将 `scsia.org` 解析为 `198.18.0.208`，属于代理/拦截地址，后端 SSRF 防护按设计拒绝。
- 内联任务最新为 `3`（此前任务 `1/2` 同样失败），持久化为 `failed`，抓取计数为零，文档数为零；刷新后的接口实际返回 `422`、错误码 `CRAWL_SOURCE_UNSAFE`、任务 ID 和 request ID。这个结果是安全边界验证，不是 live crawl 成功。

必须在具备正常公网 DNS/出口（或经安全审查的代理解析方案）的目标主机上重新执行真实抓取；对该站点的图片型正文还需要 selector 校准和 OCR/图片抽取，才能进入可检索内容质量验收。

外部 live 项目必须按 `PRODUCTION_ACCEPTANCE_CHECKLIST.md` 在目标环境执行；在 PostgreSQL、Redis、Qdrant、worker、scheduler、Nginx、Alembic、Brave、Coze/Direct LLM、embedding、rerank 和 live Playwright 证据完成前，发布结论保持 **NOT PRODUCTION ACCEPTED**。

## 10. 发布门禁

生产发布至少还需要：

1. 在目标 Docker/Kubernetes/VM 环境完成 PostgreSQL、Redis、Qdrant、worker、scheduler、Nginx、Alembic 与 live Playwright。
2. 对实际选择的 Brave、Coze/Direct LLM、embedding 和 rerank provider 完成凭据、限流、错误、计费和数据保留验收。
3. 补真实官方站点至少 10 篇抓取，并审核 robots/条款、selector、幂等和内容质量。
4. 用代表性数据重跑 evaluation、experiment 和 load test；保存真实 token/cost/latency。
5. 将 rate limiter 改为共享 Redis/ingress，或正式限制为单 backend replica。
6. 处理 npm high severity advisory 并完成 Python/容器依赖扫描。
7. 建立 Git commit/tag、CI green 证据、SBOM/镜像 digest、备份恢复演练和发布审批记录。
