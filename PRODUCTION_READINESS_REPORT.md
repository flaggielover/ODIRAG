# ODIRAG Production Readiness Report

审计日期：2026-08-06
审计基准：ODIRAG_CODEX_MASTER_EXECUTION_GUIDE.md（Phase 0-15；新增 Phase 16）  
结论：**NOT PRODUCTION ACCEPTED / 需要外部验收**

代码层面的 Phase 0-15 主流程和新增 Phase 16 已形成可运行实现，未发现 runtime TODO、FIXME、空函数、硬编码检索结果、硬编码仪表盘指标或伪造评估指标。本机 Docker WSL 数据已无损迁移到 D 盘，最终 application 镜像下八个服务全部 healthy；隔离 PostgreSQL migration round-trip/备份恢复、Redis、Qdrant health、worker、scheduler、8080/Nginx/frontend/API 均完成真实本地检查。pydantic-settings 2.14 的 CSV/JSON 兼容已在代码和容器中修复；Alembic 已约束并锁定为 1.18.5；Playwright high finding 已通过 1.55.1 的非破坏性升级修复；npm 两种 audit 均为 0，最终 backend/frontend Docker Scout 均为 0 vulnerabilities。自动化集成测试仍主要使用 SQLite、内存 cache/vector store 和确定性 embedding/rerank，外部 provider 只做协议级 test double 验证；Qdrant 当前仍是 0 collection/0 points。因此本报告不能把生产部署、Brave、Coze、远程 embedding/rerank、Direct LLM 或 cited-answer workflow 标为生产通过。

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

1. **当前本机 final runtime、migration 和本地供应链门禁通过。** backend/frontend fresh runtime 已构建，最终 backend/runtime 和 builder 已重新生成；八服务 healthy，worker、scheduler 和 Nginx/API 均通过。CSV/JSON trusted-proxy 输入在 pydantic-settings 2.14.2 容器中通过；fresh builder 实装 Alembic 1.18.5 且 `pip check` 通过；fresh PostgreSQL upgrade/downgrade/upgrade 和既有库 `check` 均通过；npm audit 为 0；最终 backend/frontend Scout 为 0 vulnerabilities。Phase 16 的自动缺口扫描已实现为默认关闭的 Beat 任务，并有去重与人工审批边界。生产 registry provenance、签名和 CI green 仍未完成。
2. **测试真实性边界清晰但很窄。** backend/tests/conftest.py 统一使用 SQLite memory、InMemoryEmbeddingCache、InMemoryVectorStore、DeterministicEmbeddingProvider 和 DeterministicRerankProvider。
3. **远程模型均未 live 验证。** Direct LLM、Coze、remote embedding、remote rerank 和 Brave Search 使用 MockTransport/fixture 验证；没有真实 token、配额、延迟、限流或计费证据。
4. **LLM token/cost 已支持真实响应透传，但仍需 live 验收。** Direct/Coze 适配器现在读取响应中的 usage/cost（若 provider 返回），Chat trace 持久化规范化 token 字段；缺失 usage 或价格时明确标记 `not_available`，cost 保持 0 作为 schema 兼容的“未知”值。真实 provider 方言、价格字段、计费和异步语义仍未验收。
5. **Coze 存在高风险契约假设。** CozeAdapter 假设 POST /v3/chat 的同步响应直接包含 answer messages；真实 Chat v3 可能需要轮询会话和单独读取消息，必须 live 验证后才能接受。
6. **共享限流代码已完成，目标环境仍未验收。** 非 test 环境默认使用 RedisFixedWindowRateLimiter；Redis 故障 fail-closed 返回结构化 503，不能静默退回进程内计数；Redis 连接/读写有依赖超时。限流身份只使用 IP，伪造 Bearer 不能分裂桶；只有显式可信代理 CIDR 才读取单跳 `X-Forwarded-For`。本地 Compose 已观察到真实 `odirag:ratelimit:*` key 和限流响应头，但 Redis ACL、故障转移、ingress 策略和多副本公平性仍需目标环境验证。
7. **分布式锁为部分满足。** crawl/source-discovery 通过数据库条件 UPDATE、唯一约束和恢复任务避免重复 claim，但没有通用 Redis distributed lock；worker 文档保存阶段另有条件状态推进，避免并发取消覆盖终态。
8. **前端功能成立，但偏离指定依赖栈。** Vue 3/TypeScript/Vite/Vue Router、安全 Markdown 已实现；package.json 未使用指南列出的 Pinia、Axios、Element Plus/Naive UI、ECharts。现有 typed fetch/custom components 能工作，但属于架构偏差。backend 明确以 UID 10001 运行；frontend/reverse-proxy Nginx 当前仍由基础镜像 root master 启动、worker 降权，非 root 容器边界不能扩大表述。
9. **配置文件结构不完全一致。** sites.yaml、filters.yaml、chunking.yaml、prompts 已使用；指南目标中的 knowledge_schema.yaml、retrieval.yaml、rerank.yaml、monitoring.yaml 不存在，相应参数主要通过环境变量/代码 schema 管理。Compose 现在显式透传 provider 配置，并把 canonical Coze token 优先级与 ODIRAG 别名对齐；真实 token 仍不得写入仓库。
10. **真实站点抓取缺证据。** fixture crawl 覆盖分页、详情、附件和幂等；已完成 scsia.org 浏览器级侦察与人工协会来源记录，但 backend DNS 解析到 `198.18.0.208` 后被 SSRF guard 拒绝，0 fetched/0 documents；指南建议的可达真实站点至少 10 篇文章仍未执行。
11. **扫描 PDF 只有 OCR 标志。** requires_ocr 可追踪，但没有 OCR engine；这不违反 Phase 3 的“标志”要求，却限制扫描件生产覆盖。
12. **前端 high 和容器扫描已闭环，但只证明当前本地 digest。** 两个 high 均来自直接 dev dependency `@playwright/test` 经传递依赖 `playwright` 命中 GHSA-7mvr-c777-76hp（受影响 `<1.55.1`）；精确升级至 1.55.1 后全依赖和 production-only audit 都为 0，无 major 升级。最终 backend（133 packages，digest `dd27a657d1bf`）和 frontend（26 packages，digest `2d41a3e3c971`）Scout 均为 0C/0H/0M/0L；SBOM 敏感字段和精确 `.env` 路径检查均为 0。目标 registry digest、CI 复扫和 provenance 仍需发布环境完成。
13. **Git 基线和审计检查点已建立，但还不是正式发布标签。** `85d4bdb feat: complete Coze batch crawl readiness` 是批量抓取实现基线，`14bbf40 docs: record production audit checkpoint` 是审计文档检查点；最终发布仍需干净且经复核的 release checkpoint、签名 tag、CI green、SBOM 和镜像 digest。
14. **本地高优先级竞态与数据边界已回归验证。** Local/Coze worker 在保存前使用条件状态推进，取消或远端失败不会覆盖 `cancelled`；审核提交锁定关联任务并在无 pending 文档时收敛为 `completed`；LLM cost 拒绝非有限/负数/超 Numeric(18,8) 范围值并量化到数据库精度。上述证据仍是 SQLite/fixture 边界，不替代 PostgreSQL 并发演练。

## 3. Phase 0-15 需求到代码追踪矩阵

### Phase 0 - Repository Audit

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| 检查现有文件、识别可复用代码、保留已有工作 | IMPLEMENTATION_STATUS.md；仓库审计日志 | 初始目录/工具链命令记录 | VERIFIED-LOCAL | 审计时目录为空，无法证明历史代码来源 |
| 创建持续更新的状态文档与 phase checklist | IMPLEMENTATION_STATUS.md | 文档结构检查 | VERIFIED-LOCAL | 最终状态须与本报告同步 |
| 记录假设 | IMPLEMENTATION_STATUS.md | 人工审阅 | VERIFIED-LOCAL | 假设需部署负责人确认 |
| 验证 Python、Node、Docker、Git | IMPLEMENTATION_STATUS.md | version 命令；Docker Compose health | VERIFIED-LOCAL | 生产主机版本、镜像 provenance 和发布权限仍需目标环境验收 |
| 每阶段 lint/type/test/checkpoint | IMPLEMENTATION_STATUS.md command log；Git `85d4bdb`、`14bbf40` | 历史命令记录；实现与审计 checkpoint | PARTIAL | 历史阶段没有逐阶段 commit，正式发布仍需 clean review、CI/tag |

### Phase 1 - Infrastructure and Core Backend

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| FastAPI application factory | backend/app/main.py | backend/tests/unit/test_core_api.py | FIXTURE-VERIFIED | 目标 ASGI/进程管理未压测 |
| Pydantic 环境配置与生产安全 gate | backend/app/config.py；.env.example | backend/tests/unit/test_config.py；fresh Compose CSV/JSON/empty container checks | VERIFIED-LOCAL | 外部 secret manager、生产密钥轮换和目标环境注入仍未验收 |
| PostgreSQL + SQLAlchemy async | backend/app/database/*；backend/app/models/* | SQLite integration suite；local Compose PostgreSQL health/identity/count queries | VERIFIED-LOCAL | 生产规模事务、锁竞争、连接池耗尽和恢复未验收 |
| Alembic core migrations | backend/alembic/versions/0001_core_schema.py；backend/requirements.lock；Dockerfile.backend | fresh PostgreSQL upgrade -> downgrade -> upgrade；Alembic 1.18.5 `check`；existing DB `current/heads/check` | VERIFIED-LOCAL | 生产业务库 downgrade 是需审批的破坏性演练；目标数据量、备份保留和恢复窗口仍未验收 |
| Redis abstraction | backend/app/cache/embedding.py；backend/app/tasks/celery_app.py；backend/app/rate_limit.py | local Redis PING/SET/GET/DEL；backend Redis ping；worker task；shared rate-limit key/header | VERIFIED-LOCAL | ACL、持久化、故障转移和跨副本限流未在目标环境验收 |
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
| task state machine + inline/async execution + retry/cancel + provider-aware paths + structured unsafe-URL/queue errors | crawler/state.py；crawler/providers.py；services/crawl.py；repositories/crawl.py；tasks/crawl.py；routes/crawl_tasks.py | test_tasks.py；test_crawl_reliability.py（含 `waiting_review` 不被恢复）；test_fixture_crawl.py（Local Provider/取消竞态/legacy guard）；test_coze_worker_pipeline.py（Coze 取消成功/失败竞态）；queue failure regression（持久化 `provider_error_code`）；test_inline_crawl_unsafe_url_returns_structured_error；local worker ping/task | FIXTURE-VERIFIED | 真实站点仍被 DNS/SSRF 阻断；broker 中断恢复仍需目标环境演练 |
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
| tokens/cost | models/query trace；services/chat.py；llm/adapters.py | adapter MockTransport usage/cost test；chat trace persistence test | PARTIAL | 真实 provider 可能不返回统一 usage/cost；价格配置/计费与 live 响应未验收 |
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
| full query trace through retrieval/prompt/answer/citation/refusal/latency | services/chat.py；models/observability.py；llm/adapters.py | search/chat/lineage tests；usage/cost propagation tests | PARTIAL | 真实 provider usage/cost 方言、价格和异步生命周期未 live 验证 |
| answer→citation→chunk→version→crawl→source traversal | repositories/observability.py；routes/chat.py | test_versioning_lineage.py | FIXTURE-VERIFIED | PostgreSQL join/cascade 未 live 验证 |
| crawler/knowledge/RAG/dependency/cost metrics | metrics.py；services/observability.py | test_metrics.py；monitoring tests | FIXTURE-VERIFIED | 多实例聚合/Prometheus 未实现 |
| 六类 persisted alerts | services/observability.py；tasks/monitoring.py | test_monitoring_alerts.py | FIXTURE-VERIFIED | 样本为 deterministic/synthetic |
| scheduled refresh + lifecycle + opt-in source-gap scan | tasks/celery_app.py；tasks/source_discovery.py；routes/system.py | test_tasks.py；source-discovery task tests；monitoring tests；本地 scheduler 日志 | VERIFIED-LOCAL | 目标环境 beat 长期运行、broker 故障和多副本调度仍未验收；自动扫描默认关闭 |

### Phase 12 - Vue Frontend

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| Dashboard/Sources/Crawl/Documents/Detail/Review/Chat/Evaluation/Experiments/Monitoring/Feedback | frontend/src/views/*；router/index.ts | Vitest + Playwright fixture suite | FIXTURE-VERIFIED | 真实生产栈浏览器未验收 |
| real API-connected pages | frontend/src/api/client.ts；resources.ts；views/CrawlTaskDetailView.vue；views/SourcesView.vue | 本地无拦截 live-stack against SQLite/deterministic；验收摘要与 legacy/batch 状态 Vitest/E2E | FIXTURE-VERIFIED | 不是 PostgreSQL/Qdrant/remote provider |
| no hard-coded metrics | DashboardView.vue；MonitoringView.vue；resources.ts | static audit + fixture contract | VERIFIED-LOCAL | fixture metrics 仅存在 e2e tests |
| typed API clients | frontend/src/api/types.ts；resources.ts | vue-tsc | VERIFIED-LOCAL | 使用 fetch，不是指南指定 Axios |
| loading/error states/accessibility | components/AsyncState.vue；views/* | Playwright critical journeys | FIXTURE-VERIFIED | 完整 WCAG 审计未执行 |
| responsive design | frontend/src/styles/*；layouts/* | 历史 mobile/desktop QA | FIXTURE-VERIFIED | 当前轮未做全页视觉基线 |
| safe Markdown | marked + DOMPurify usage | frontend tests/static audit | VERIFIED-LOCAL | CSP 仍依赖部署入口 |
| 指定 Pinia/Axios/UI kit/ECharts | frontend/package.json | dependency audit | PARTIAL | 四类依赖未采用；属于指南架构偏差 |
| Playwright critical journeys | frontend/e2e/*.spec.ts；playwright.config.ts | 串行 9 passed；live-stack 1 skipped；Coze fixture 2 passed；Vitest 16 passed | FIXTURE-VERIFIED | 真实外部 provider/live-stack gate 待目标环境 |

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
| rate limiting | rate_limit.py；main.py；config.py；docker-compose.yml | test_rate_limit.py（共享计数/故障 fail-closed）；本地 Compose Redis key 与 `X-RateLimit-*` header | VERIFIED-LOCAL | 目标 Redis ACL、故障转移、跨副本公平性和 ingress 限流未验收 |
| file limits/allowlist/path safety | crawler/storage.py；fetcher.py；config.py | HTTP/storage security tests | FIXTURE-VERIFIED | 恶意压缩包资源消耗需额外沙箱 |
| SQL injection protection | safe repository templates | security/router tests | VERIFIED-LOCAL | 新查询需持续审查 |
| XSS/CORS/secrets/error codes | DOMPurify；CORSMiddleware；config.py；errors.py | frontend/static/config/API tests | FIXTURE-VERIFIED | CSP/TLS/secret manager 未 live 验收 |
| retries/timeouts/idempotency | fetcher/services/indexing/crawl | reliability tests | FIXTURE-VERIFIED | 外部故障组合未演练 |
| distributed locks | conditional DB UPDATE；unique constraints | concurrency-oriented SQLite tests | PARTIAL | 无共享 Redis lock；SQLite 不等于 PostgreSQL 并发 |
| cache/batch embedding | cache/embedding.py；embedding/batcher.py | memory cache tests | FIXTURE-VERIFIED | Redis/remote provider 未 live |
| task recovery | tasks/recovery.py；0003 migration | test_crawl_reliability.py | FIXTURE-VERIFIED | worker kill/visibility timeout 未 live 演练 |
| migration/backup documentation | DEPLOYMENT.md；SECURITY.md；PRODUCTION_ACCEPTANCE_CHECKLIST.md | 独立临时 PostgreSQL 容器/卷 restore；9 表 count 对比 | VERIFIED-LOCAL | 当前小型 development 数据通过；目标生产数据量、加密、保留策略和定期调度未验收 |
| lightweight load test + actual metrics | scripts/load_test.py；performance.py | deterministic local run | FIXTURE-VERIFIED | 不是生产容量/SLA；外部依赖为空 |
| search/chat/DB P95 goals | data/load-tests ignored artifacts；IMPLEMENTATION_STATUS.md | 20+20 local deterministic requests | FIXTURE-VERIFIED | 需生产规模重跑 |

### Phase 15 - Docker, CI/CD, Open-source Handoff

| Requirement | Implementation files | Tests / evidence | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| backend/frontend/postgres/redis/qdrant/worker/scheduler/nginx services | docker-compose.yml；Dockerfiles；deployment/*.conf | `docker compose config`、final image `compose ps`、8 个 health checks、Nginx `/healthz`/首页/API/浏览器登录 | VERIFIED-LOCAL | development 栈已恢复；生产 secret/TLS、registry provenance、目标主机持久化和灾备仍未验收 |
| optional prometheus/grafana | 无 | 无 | PARTIAL | 指南允许 if feasible，不是核心 blocker |
| backend lint/type/test/coverage CI | .github/workflows/ci.yml | YAML parse；本地等价命令 | CONTRACT-VERIFIED | GitHub Actions 未实际跑 |
| frontend lint/test/build/Playwright CI | .github/workflows/ci.yml | YAML parse；本地 npm commands | CONTRACT-VERIFIED | Actions/浏览器镜像未实际跑 |
| Docker build CI | .github/workflows/ci.yml；Dockerfile.backend；Dockerfile.frontend | fresh backend/frontend runtime build；fresh builder stages；current Compose health；Docker Scout 0/0 | CONTRACT-VERIFIED | GitHub Actions、签名镜像、registry provenance 和目标 registry 复扫未实际跑 |
| README/architecture/API/eval/experiments/deployment/security/contribution/roadmap/license | 根目录文档 | link/path/structure audit | VERIFIED-LOCAL | 需随最终测试结果同步 |
| honest demo seed | scripts/seed_demo.py；data/evaluation/* | test_demo_seed.py；deterministic pipeline | FIXTURE-VERIFIED | demo URLs/data 不代表真实来源 |
| one-command startup | scripts/start_demo.ps1；scripts/start_demo.sh | 脚本本身有历史 smoke；当前恢复中 `up -d` 被中断，修复依赖网络别名并定向启动后 health 通过 | PARTIAL | 需要在保留数据前提下重新执行 clean startup 验收；fresh build、生产环境变量、备份恢复、发布流程未实测 |
| 12+ learning/defense docs | docs/learning/*；docs/*.md | structure audit | VERIFIED-LOCAL | Phase16 learning doc另行新增 |
| release/checkpoint history | .git | `git log --oneline`；`git diff --check` | PARTIAL | 已有实现基线 `85d4bdb` 和审计检查点 `14bbf40`；尚无经外部门禁确认的签名 release tag/CI/SBOM |

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
- ChatService 在没有 provider usage/cost 时写入 `measurement=not_available` / `cost_measurement=not_available` 与 cost=0；有 provider 响应时持久化规范化 token 和 provider_reported cost。cost=0 不能被解释为真实计费成功。

## 6. 仅在 SQLite / fixture / fake provider 验证的功能

| Boundary | Current evidence | Not proven |
| --- | --- | --- |
| 所有 backend integration tests | SQLite in-memory via backend/tests/conftest.py | PostgreSQL SQL/JSONB/locking/pool behavior |
| embedding | deterministic SHA256 vectors；remote MockTransport | remote auth/quota/dimension/cost/latency |
| rerank | deterministic token overlap；remote MockTransport | remote score contract/rate limits |
| vector store | InMemoryVectorStore；Qdrant FakeClient | real collection/index/persistence/delete/backup |
| cache | InMemoryEmbeddingCache；local Redis connectivity only | Redis-backed cache TTL/ACL/persistence/failure behavior |
| rate limiting | RedisFixedWindowRateLimiter unit contract；local Compose Redis counter and response headers | target Redis ACL/failover, multi-replica fairness, ingress interaction |
| crawling | static fixture site + MockTransport；scsia browser-only inspection + backend SSRF rejection | real DNS/TLS/robots/anti-bot/10-article crawl |
| LLM | Direct/Coze MockTransport | real model JSON stability, Coze async lifecycle, token/cost |
| evaluation/experiments/load | tiny deterministic demo | representative corpus, production latency/cost/quality |
| frontend E2E | Playwright route fixtures；local SQLite/deterministic 无拦截 smoke；Nginx/frontend HTTP smoke | deployed HTTPS、真实内容/引用、remote provider |
| worker/scheduler | Celery task registration/schedule config tests；local worker ping/task and scheduler logs | queued crawl/source-discovery completion、故障恢复和生产 beat 长期运行 |
| containers/CI | 当前 backend/frontend `--pull --no-cache` build；builder stage tag；fresh runtime start/health；worker/scheduler 复用 backend tag；trusted-proxy 容器回归；npm/Scout 均为 0 | GitHub Actions、生产 registry 复扫、镜像签名/provenance；frontend/reverse-proxy root master 仍需目标环境 hardening 评估 |

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
| explicit Local Provider crawl contract | crawler/providers.py；services/crawl.py；crawler/state.py；repositories/crawl.py | test_fixture_crawl.py；test_crawl_reliability.py；provider unit tests；review convergence test | FIXTURE-VERIFIED | 仅确定性 fixture；真实公网 DNS/反爬和附件质量未验证；审核完成后等待任务会收敛为 completed |
| Coze batch invocation/raw response/acceptance summary | crawler/providers.py；services/crawl.py；api/routes/crawl_tasks.py；frontend/src/views/CrawlTaskDetailView.vue | Coze provider/worker fixtures；CrawlTaskDetailView.spec.ts；coze-crawl.spec.ts | CONTRACT-VERIFIED | 新批量 workflow URL/token 尚未配置；不能宣称真实 Coze 结果 |
| quality scoring | services/source_discovery.py；config thresholds | source discovery integration tests | FIXTURE-VERIFIED | 权重是启发式，未用生产标注集校准 |
| manual approve/reject | routes/source_discovery.py；repository atomic update | integration + Playwright tests | FIXTURE-VERIFIED | 只有 admin，没有双人审批 |
| activation to Source/SourceColumn | services/source_discovery.py；models/source.py | integration + Playwright tests；activation compensation test | FIXTURE-VERIFIED | PostgreSQL uniqueness/并发未 live；激活后不自动启动 crawl；异常补偿路径尚未在真实 PostgreSQL 演练 |
| queue/worker/retry | tasks/source_discovery.py；celery_app.py | queue failure + retry reuse tests；local worker ping/task and scheduler logs | FIXTURE-VERIFIED | 真实 source-discovery queued run、故障恢复和长期 beat 仍未验收 |
| database migration | 0004_source_discovery.py；0005_coze_crawl_provider.py；0006_coze_task_operations.py；models/source_discovery.py；models/source.py | SQLite round-trip；专用 PostgreSQL fresh upgrade→downgrade 0003→upgrade；existing DB current/check；隔离 backup/restore | VERIFIED-LOCAL | 未对生产业务库直接 downgrade；目标数据量、锁等待、RPO/RTO 仍未验收 |
| APIs | routes/source_discovery.py；schemas/source_discovery.py | test_source_discovery_api.py | FIXTURE-VERIFIED | production rate/authorization角色有限 |
| frontend | SourceDiscoveryView.vue；typed API/router/nav | source-discovery.spec.ts | FIXTURE-VERIFIED | live Brave workflow浏览器验收缺失 |
| monitoring/audit | source_discovery_events；metrics API/UI | metrics/events integration + Playwright | FIXTURE-VERIFIED | 未接入全局 Alert rule |
| docs/learning | API.md/ARCHITECTURE.md/DEPLOYMENT.md 等；docs/learning/13_source_discovery.md；docs/learning/13_source_discovery_auto_schedule.md | doc structure audit | VERIFIED-LOCAL | 学习材料已生成；仍需将目标环境证据回填 |

Brave 被选为当前 live provider，因为 Microsoft 已宣布 Bing Search APIs 于 2025-08-11 完全退役。实现不再依赖退役 endpoint；Brave 仍只为 contract-verified。参考：[Microsoft Bing Search API retirement](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)、[Brave Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get)。

### 7.1 无人值守调度补充

| Requirement | Implementation files | Tests | Status | Remaining risk |
| --- | --- | --- | --- | --- |
| opt-in topic scheduler, CSV/JSON/empty configuration, minimum interval, active-run/cooldown guard, queue failure audit, no automatic activation | `backend/app/config.py`; `backend/app/repositories/source_discovery.py`; `backend/app/tasks/celery_app.py`; `backend/app/tasks/source_discovery.py`; `.env.example`; `docker-compose.yml`; `DEPLOYMENT.md`; `docs/learning/13_source_discovery.md` | `backend/tests/unit/test_config.py`; `backend/tests/unit/test_tasks.py`; `backend/tests/integration/test_source_discovery_scheduler.py` | FIXTURE/SQLite VERIFIED | Real Celery Beat delivery remains unverified；active/cooldown check is not an atomic cross-Beat lock，production must run a single scheduler；external Brave credentials are required |

The scheduler is intentionally a proposal mechanism. It creates and queues a run only after a
database gap check, skips active or recently-created same-topic runs, and leaves approval/activation
to the existing manual API path.

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
- 生产/staging 默认启用使用单 key Lua 原子脚本的 `RedisFixedWindowRateLimiter`，Redis 不可用时返回 `RATE_LIMIT_BACKEND_UNAVAILABLE` 503，不再静默使用进程内限流；test 环境仍显式使用 memory limiter。
- 限流身份改为 IP-only，伪造 Bearer 不再分裂桶；只有显式可信代理 CIDR 才读取单跳 `X-Forwarded-For`，Redis 连接/读写使用依赖超时。
- 将已有 `LocalCrawlProvider` 接入 `CrawlService.execute(provider=local)` 的完整持久化路径，保留 `pending_review` / `waiting_review` 语义，以 `local_extraction` 保存真实来源，并排除 scheduler stale-worker 误重抓。
- 本地/Coze worker 在启动、远端阶段和进入文档保存前使用条件状态推进；取消请求也按观察到的状态做 CAS，旧请求不能覆盖新 worker 阶段；文档审核完成后关联 `waiting_review` 任务按 lineage 原子收敛。
- LLM provider cost 拒绝非有限、负数和超出 `Numeric(18,8)` 范围的值，并量化到数据库精度；Phase 16 验收清单验证候选事件严格顺序。
- 对栏目任务显式拒绝 `legacy_single_article`，返回 `COZE_LEGACY_SINGLE_ARTICLE_ONLY`；legacy 部署继续用于单篇兼容/连通性回归，避免误把旧工作流当批量任务执行。
- 前端任务详情消费后端验收摘要（数据库文档/分块/Qdrant 点数），来源页分别展示 legacy 与 batch 配置状态；新增 Vitest 与 Playwright fixture 断言。

## 9. 最终本地验证

以下结果已在本次审计结束时重新执行并记录：

| Check | Result | Boundary |
| --- | --- | --- |
| `backend/.venv/Scripts/ruff.exe check app tests` | PASS | 本地源代码/测试静态检查 |
| `backend/.venv/Scripts/black.exe --check app tests alembic` | PASS；206 files unchanged | 本地格式检查 |
| `backend/.venv/Scripts/mypy.exe app` | PASS；154 source files | 本地类型检查 |
| `backend/.venv/Scripts/python.exe -m pytest -q --cov=app --cov-report=term-missing` | PASS；249 passed；总覆盖率 80.52% | SQLite、内存实现、确定性 provider；不替代真实依赖验收 |
| `backend/.venv/Scripts/pytest.exe tests/unit/test_sources_and_crawler.py -q` | PASS；8 passed | fixture；含 unsafe inline crawl 结构化错误 |
| Phase 16/config/API 定向测试 | PASS；28 passed | fixture/contract |
| Alembic fresh upgrade → downgrade → upgrade | PASS-LOCAL；锁定 Alembic 1.18.5；专用 PostgreSQL 从空库升至 `0006`、降至 `0003`、再升至 `0006`，最终 `check` 无漂移 | 未对生产业务库直接 downgrade；目标数据量、锁等待和维护窗口仍未验收 |
| frontend lint/type-check/Vitest/build | PASS；17 Vitest tests，Vite 1850 modules | 本地 Node toolchain（Vitest/build 使用提升权限启动 esbuild） |
| `npm audit` / `npm audit --omit=dev` | PASS；两种模式均为 0 vulnerabilities | 只证明当前 lockfile；目标 CI/registry 仍需复扫 |
| fresh builder `python -m pip check` | PASS；No broken requirements found；Alembic 1.18.5 | 只验证依赖一致性，不是 CVE 扫描 |
| Playwright fixture suite | PASS；串行 9 passed，1 live test skipped | route fixture；live gate 未开启 |
| real Compose `live-stack.spec.ts` | BLOCKED-EXPECTED；登录/来源/文档页面可达，引用问答因 remote embedding 未配置而返回 provider unavailable | 没有真实 provider 与已索引语料；不得算 live pass |
| isolated Uvicorn API smoke | PASS；health/login/Coze status/sources/crawl-tasks 均 HTTP 200；health 为 database healthy、Redis unavailable、Qdrant disabled | 临时 SQLite + deterministic providers；不证明 Docker、PostgreSQL、Redis、Qdrant 或外部 provider |
| current local Docker Compose service/worker/scheduler acceptance | PASS-LOCAL；8 services healthy；worker inspect ping 成功；scheduler PID 存在并发送 recovery/monitoring tasks | development 配置；不证明生产 secret/TLS、容灾或远程 provider |
| current local PostgreSQL Alembic | PASS-LOCAL；Alembic 1.18.5；existing DB 与专用 fresh DB 均为 `0006_coze_task_operations (head)`，`check` 无漂移；专用库 round-trip 通过 | 未对生产业务库直接 downgrade；目标维护窗口未验证 |
| isolated PostgreSQL backup/restore | PASS-LOCAL；156,455-byte custom dump；SHA-256 留档；独立 `--network none` 容器和临时卷恢复；9 表 count 一致；临时资源已清理 | 当前小型 development 数据；未证明生产规模、加密备份、RPO/RTO 和定期调度 |
| current local Nginx/frontend/API/browser smoke | PASS-LOCAL；Nginx 1.30.4 下 `/healthz`、`/`、`/api/system/health` 均 200；API database/redis/qdrant 均 healthy；管理员页面登录成功并渲染仪表盘；浏览器控制台无 warning/error；安全响应头存在 | HTTP development 入口和交互式本地浏览器证据；自动化 live Playwright、HTTPS 和 remote provider 门禁未验证 |
| current Docker/WSL control-plane check | PASS-LOCAL；Docker Desktop 4.85.0、Client/Server 29.6.2、Compose v5.3.1；`docker-desktop` WSL2 running；8080/8000/5433/6379/6333/6334 监听 | 通过停止卡死 Desktop 进程、成功执行 `wsl --shutdown`、重新启动 Desktop 恢复；未删除 VHD、容器、Volume 或数据库 |
| current hardened image build/scan | PASS-LOCAL；backend/frontend `--pull --no-cache`、最新 builder、八服务 healthy；runtime pip 已移除；CSV/JSON/empty 配置通过；npm 两种 audit 为 0；Scout backend/frontend 均 0C/0H/0M/0L | 只证明本地 digests `dd27a657d1bf` / `2d41a3e3c971`；目标 registry、CI、签名和 provenance 未验证 |
| current real Compose Playwright | FAIL-EXPECTED；登录、sources、documents、chat 页面成功；查询返回 `A required provider is unavailable`，引用断言失败 | `embedding_provider=remote` 且无 key，数据库/Qdrant 无已索引文档；不是前端 live acceptance pass |
| authenticated API / acceptance-summary | PASS-LOCAL；login、Coze status、sources、documents、crawl-tasks、acceptance-summary、invocations、failed-urls 均通过 | 现有 3 个 scsia 失败任务均为 0 documents/chunks/Qdrant points；不是成功抓取/索引证据 |
| Qdrant live local state | PASS-LOCAL health；`/healthz` 200；collection count 0 | 服务正常但无已索引文档，collection/schema/point 持久化仍未验收 |
| Coze batch live preflight | PASS-EXPECTED；`GET /api/system/coze/status` 显示 disabled/unconfigured；脚本退出码 2、`batch_workflow_not_published` | 没有批量部署 URL/token；不是 Live 成功 |

### scsia.org 实验记录（非 PASS-LIVE）

该实验明确区分了“浏览器能打开”与“后端能安全抓取”：

- 浏览器只读检查通过：`https://scsia.org/Industry_information/Industry_information_1` 可打开通知列表并观察到 69 条记录，详情路由可定位；详情正文主要是上传图片，HTML 文本为空，因此不能把页面可视化内容直接当作已解析文本。
- 本地 API 创建了显式协会实验来源（`source_id=1`、`column_id=1`、`official_status=association`），没有绕过 Phase 16 的官方来源校验，也没有把协会域名标记为政府官方站点。
- `POST /api/sources/1/test` 返回 `reachable=false`、`error_type=UnsafeUrlError`；本机 DNS 将 `scsia.org` 解析为 `198.18.0.208`，属于代理/拦截地址，后端 SSRF 防护按设计拒绝。
- 内联任务最新为 `3`（此前任务 `1/2` 同样失败），持久化为 `failed`，抓取计数为零，文档数为零；刷新后的接口实际返回 `422`、错误码 `CRAWL_SOURCE_UNSAFE`、任务 ID 和 request ID。这个结果是安全边界验证，不是 live crawl 成功。

必须在具备正常公网 DNS/出口（或经安全审查的代理解析方案）的目标主机上重新执行真实抓取；对该站点的图片型正文还需要 selector 校准和 OCR/图片抽取，才能进入可检索内容质量验收。

本机 PostgreSQL 服务、隔离迁移 round-trip/备份恢复、Redis、Qdrant health、fresh worker/scheduler、Nginx、frontend、锁定的 Alembic 1.18.5、npm audit 和本地镜像 Scout 均已通过 development 栈验证。外部 live 项目仍必须按 `PRODUCTION_ACCEPTANCE_CHECKLIST.md` 在目标环境执行。在 Brave、Coze/Direct LLM、embedding、rerank、至少 10 篇代表性官方内容、真实索引/Qdrant points、生产 TLS/secret、CI/registry provenance 和 cited-answer live Playwright 证据完成前，发布结论保持 **NOT PRODUCTION ACCEPTED**。

### 9.1 本轮调度回归补充

`backend/.venv/Scripts/pytest.exe -q --cov=app --cov-report=term-missing` completed with
`249 passed` and `80.52%` total coverage. The added scheduler coverage includes disabled/no-topic
short-circuiting, CSV/JSON/empty environment parsing, same-topic active-run skipping, minimum-interval
cooldown, successful enqueue, queue failure persistence, and redacted error observability. Ruff,
Black (206 files), and mypy (154 source files) pass. Frontend lint/type-check/build pass,
Vitest reports 17 passed tests, and fixture Playwright reports 9 passed plus 1 explicit live skip.

## 10. 发布门禁

生产发布至少还需要：

1. 在目标 Docker/Kubernetes/VM 环境完成 PostgreSQL、Redis、Qdrant、worker、scheduler、Nginx、Alembic 与 live Playwright。
2. 对实际选择的 Brave、Coze/Direct LLM、embedding 和 rerank provider 完成凭据、限流、错误、计费和数据保留验收。
3. 补真实官方站点至少 10 篇抓取，并审核 robots/条款、selector、幂等和内容质量。
4. 用代表性数据重跑 evaluation、experiment 和 load test；保存真实 token/cost/latency。
5. 在目标环境验证共享 Redis/ingress 限流的 ACL、故障转移、跨副本公平性和恢复行为；代码已默认使用 Redis，不能以单副本作为未验证的替代结论。
6. 在目标 registry/CI 对已发布 digest 重新执行 `docker scout cves ... --exit-code`，保存 SBOM、签名和 provenance。本机 fresh rebuild、npm audit 和本地 Scout 已通过，但不能替代目标发布链证据。
7. 建立 Git commit/tag、CI green 证据、SBOM/镜像 digest、备份恢复演练和发布审批记录。
