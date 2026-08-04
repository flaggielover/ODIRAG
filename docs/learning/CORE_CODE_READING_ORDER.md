# ODIRAG 核心代码阅读顺序

目标不是按目录字母顺序读完所有文件，而是先建立运行主线，再沿一个真实请求逐层深入。每个实现文件都应配对阅读对应测试；看到状态或数据字段时回到模型和迁移确认约束。

## 1. 阅读前准备

先看以下四个文件，了解项目承诺与当前状态：

1. `README.md`
2. `ARCHITECTURE.md`
3. `IMPLEMENTATION_STATUS.md`
4. `ODIRAG_CODEX_MASTER_EXECUTION_GUIDE.md`

然后确认后端测试 fixture：

- `backend/tests/conftest.py` 使用内存 SQLite、deterministic embedding、memory cache/vector store 和 deterministic rerank。
- 测试 Provider 是明确 test mode，不代表生产外部集成已验证。

## 2. 第一轮：30 分钟理解应用骨架

### 2.1 配置与启动

依次阅读：

1. `backend/app/config.py`
2. `backend/app/main.py`
3. `backend/app/database/session.py`
4. `backend/app/runtime.py`
5. `backend/app/api/router.py`
6. `backend/app/dependencies.py`
7. `backend/app/errors.py`

需要回答：

- 环境变量怎样进入 `Settings`？
- staging/production 有哪些强制安全校验？
- Database、Metrics、RateLimiter 和 Runtime 在哪里创建？
- 请求如何获得 AsyncSession 和当前用户？
- Provider 不可用如何变成安全的 HTTP 错误？

配对测试：`test_config.py`、`test_core_api.py`、`test_models.py`。

### 2.2 认证与横切能力

1. `backend/app/security.py`
2. `backend/app/services/auth.py`
3. `backend/app/repositories/users.py`
4. `backend/app/rate_limit.py`
5. `backend/app/logging.py`
6. `backend/app/metrics.py`

需要回答：token version 如何撤销旧 access/refresh？限流为何只在单进程内有效？路由和数据库延迟怎样采样？

配对测试：`test_security.py`、`test_rate_limit.py`、`test_metrics.py`。

## 3. 第二轮：60 分钟跟踪一篇文档

### 3.1 来源和抓取

阅读顺序：

1. `backend/app/models/source.py`
2. `backend/app/schemas/source.py`、`schemas/crawl.py`
3. `backend/app/api/routes/sources.py`、`crawl_tasks.py`
4. `backend/app/services/sources.py`
5. `backend/app/crawler/urls.py`
6. `backend/app/crawler/fetcher.py`
7. `backend/app/crawler/generic.py`
8. `backend/app/crawler/adapters.py`、`registry.py`
9. `backend/app/services/crawl.py`
10. `backend/app/repositories/crawl.py`
11. `backend/app/tasks/crawl.py`、`recovery.py`、`celery_app.py`

重点跟踪一个 `task_id`：API 创建 pending -> Celery 入队 -> 原子 claim -> 抓取 -> Document/Attachment/Lineage -> completed/failed。

配对测试：`test_sources_and_crawler.py`、`test_http_fetcher_security.py`、`test_fixture_crawl.py`、`test_crawl_reliability.py`。

### 3.2 解析和版本

1. `backend/app/parsers/base.py`
2. `backend/app/parsers/registry.py`
3. 六个具体 parser
4. `backend/app/cleaners/text.py`
5. `backend/app/deduplication/core.py`
6. `backend/app/services/parsing.py`
7. `backend/app/services/versioning.py`
8. `backend/app/repositories/documents.py`

重点跟踪 `ParsedArtifact` 如何变成新 `DocumentVersion`，以及为什么 `index_status` 变为 stale。

配对测试：`test_parsers_cleaning_dedup.py`、`test_versioning_lineage.py`。

### 3.3 审查和知识

1. `config/filters.yaml`
2. `backend/app/filters/rules.py`
3. `backend/app/llm/protocols.py`
4. `backend/app/llm/adapters.py`
5. `backend/app/services/prompts.py`
6. `backend/app/services/review.py`
7. `backend/app/repositories/reviews.py`
8. `backend/app/api/routes/reviews.py`

重点跟踪 rule review、LLM review 和 manual review 为什么是三条记录；检查 evidence quote 的原文绑定。

配对测试：`test_filters_prompts_llm.py`、`test_review_pipeline.py`。

## 4. 第三轮：60 分钟跟踪一次索引与检索

### 4.1 分块、Embedding 和向量

1. `config/chunking.yaml`
2. `backend/app/chunking/heading.py`
3. `backend/app/embedding/providers.py`
4. `backend/app/cache/embedding.py`
5. `backend/app/embedding/batcher.py`
6. `backend/app/vector_store/store.py`
7. `backend/app/services/indexing.py`
8. `backend/app/repositories/indexing.py`

重点跟踪稳定 chunk ID 的输入、Qdrant upsert、数据库切换、stale 点删除和失败补偿。

配对测试：`test_indexing_components.py`、`test_indexing_pipeline.py`。

### 4.2 BM25 与混合检索

1. `backend/app/bm25/index.py`
2. `backend/app/services/bm25.py`
3. `backend/app/retrieval/models.py`
4. `backend/app/retrieval/analysis.py`
5. `backend/app/retrieval/rrf.py`
6. `backend/app/rerank/providers.py`
7. `backend/app/retrieval/engine.py`
8. `backend/app/api/routes/search.py`

重点跟踪同一 query 在 BM25、vector、RRF、rerank 和 final threshold 中的 rank/score 变化。

配对测试：`test_retrieval_phase6.py`、`test_providers_and_retrieval.py`、`test_search_api.py`。

## 5. 第四轮：45 分钟跟踪一次 Chat

1. `backend/app/router/query_router.py`
2. `backend/app/repositories/chat.py`
3. `backend/app/rag/grounding.py`
4. `backend/app/services/chat.py`
5. `backend/app/models/observability.py`
6. `backend/app/repositories/observability.py`
7. `backend/app/services/observability.py` 中 `LineageService`
8. `backend/app/api/routes/chat.py`

使用三个问题建立心智模型：

- 数量问题如何只走安全 SQL count？
- 政策总结如何走 RAG 并产生真实 citation？
- 无关问题如何被 GroundingService 拒答？

最后从 `QueryTrace` 的 citation chunk ID 追到 DocumentVersion、CrawlTask 和 Source。

配对测试：`test_chat_grounding.py`、`test_search_api.py`、`test_read_support_api.py`。

## 6. 第五轮：45 分钟理解质量闭环

### 6.1 评估

1. `backend/app/evaluation/metrics.py`
2. `backend/app/evaluation/runner.py`
3. `backend/app/evaluation/reports.py`
4. `backend/app/services/evaluation.py`
5. `backend/app/repositories/evaluation.py`
6. `backend/app/api/routes/evaluations.py`

先手算一个 Recall/MRR/Citation precision/recall 样本，再对照代码；特别检查 hallucination denominator。

### 6.2 实验

1. `backend/app/experiments/config.py`
2. `backend/app/experiments/service.py`
3. `backend/app/experiments/comparison.py`
4. `backend/app/experiments/odirag.py`
5. `backend/app/experiments/reports.py`
6. `backend/app/services/experiments.py`
7. `scripts/run_experiment.py`

重点跟踪 baseline/candidate 如何构建隔离 runtime、怎样识别 metric regression 和 new failed case。

### 6.3 反馈

1. `backend/app/services/feedback.py`
2. `backend/app/repositories/feedback.py`
3. `backend/app/api/routes/feedback.py`

重点看不同 feedback_type 如何决定 expected document/chunk、答案点和 should_refuse。

配对测试：`test_evaluation_phase9.py`、`test_evaluation_api.py`、`test_experiments_phase10.py`、`test_experiment_api.py`、`test_feedback_api.py`。

## 7. 第六轮：30 分钟理解监控与性能

1. `backend/app/services/health.py`
2. `backend/app/metrics.py`
3. `backend/app/repositories/observability.py`
4. `backend/app/services/observability.py` 中 `MonitoringService`
5. `backend/app/tasks/monitoring.py`
6. `backend/app/api/routes/system.py`
7. `backend/app/performance.py`
8. `scripts/load_test.py`

需要区分三类数据：进程内路由/DB latency、数据库业务聚合、持久化 alerts。确认本地 load test goal 与生产 SLA 的区别。

配对测试：`test_metrics.py`、`test_performance.py`、`test_monitoring_alerts.py`。

## 8. 第七轮：45 分钟阅读前端

1. `frontend/src/main.ts`
2. `frontend/src/router/index.ts`
3. `frontend/src/api/client.ts`
4. `frontend/src/auth/state.ts`
5. `frontend/src/api/types.ts`
6. `frontend/src/api/resources.ts`
7. `frontend/src/layouts/AppShell.vue`
8. `frontend/src/components/AsyncState.vue`
9. `frontend/src/components/MarkdownContent.vue`
10. views 按 Dashboard -> Sources -> Documents -> Reviews -> Chat -> Evaluations -> Experiments -> Monitoring -> Activity
11. `frontend/src/styles/main.css`

重点跟踪 401 single-flight refresh、结构化 ApiError、Markdown 清洗、移动导航和健康轮询。

配对测试：`client.spec.ts`、`state.spec.ts`、`MarkdownContent.spec.ts`、`StatusBadge.spec.ts`、`ActivityView.spec.ts`。

## 9. 第八轮：30 分钟阅读部署

1. `.env.example`
2. `docker-compose.yml`
3. `Dockerfile.backend`
4. `deployment/container-entrypoint.sh`
5. `Dockerfile.frontend`
6. `deployment/frontend.nginx.conf`
7. `deployment/nginx.conf`
8. `scripts/start_demo.sh`、`scripts/start_demo.ps1`
9. `deployment/initialize-demo.sh`
10. `scripts/seed_demo.py`
11. `.github/workflows/ci.yml`

重点回答：谁执行迁移、谁等待谁、数据写到哪个 volume、demo 是否真实写 Qdrant、CI 是否以非 root 启动镜像。

## 10. 按问题反查代码

| 问题 | 首先阅读 |
| --- | --- |
| 为什么请求返回 401？ | `dependencies.py`、`security.py`、`services/auth.py` |
| 为什么 crawl 卡住？ | `repositories/crawl.py`、`tasks/recovery.py`、`celery_app.py` |
| 为什么 URL 被拒绝？ | `crawler/urls.py`、`crawler/fetcher.py` |
| 为什么文档没有新版本？ | `services/versioning.py`、`deduplication/core.py` |
| 为什么文档不能索引？ | `services/indexing.py`、Document final/index status |
| 为什么 BM25 有结果、vector 没有？ | `runtime.py`、`vector_store/store.py`、`retrieval/engine.py` |
| 为什么 Chat 拒答？ | `rag/grounding.py`、`services/chat.py` |
| 为什么 citation 不完整？ | `repositories/observability.py`、`services/observability.py` |
| 为什么指标下降？ | evaluation report -> `metrics.py` -> experiment compare |
| 为什么页面被登出？ | `frontend/src/api/client.ts`、`auth/state.ts` |
| 为什么容器迁移失败？ | entrypoint、Alembic、Compose database URL |

## 11. 建议的两小时最短路线

时间不足时按以下顺序：

1. `config.py`、`main.py`、`runtime.py`（15 分钟）
2. `services/crawl.py` + `crawler/fetcher.py`（15 分钟）
3. `services/review.py`（10 分钟）
4. `services/indexing.py`（20 分钟）
5. `retrieval/engine.py` + `rrf.py`（15 分钟）
6. `query_router.py` + `grounding.py` + `services/chat.py`（20 分钟）
7. `evaluation/metrics.py` + `services/evaluation.py`（15 分钟）
8. `frontend/src/api/client.ts` + `ChatView.vue`（5 分钟）
9. `docker-compose.yml` + CI（5 分钟）

## 12. 阅读完成标准

读完后应能不看文档回答：

- 一篇网页如何变成可引用 chunk；
- 一个 Chat 请求如何选择 SQL/RAG/组合；
- 模型为什么不能伪造 URL；
- worker 宕机和重复消息如何收敛；
- 文档更新后为什么不会继续使用旧索引；
- 用户反馈如何成为回归题；
- 本地 deterministic 结果与生产外部 Provider 验收有何区别；
- 当前最重要的未完成边界是什么。
