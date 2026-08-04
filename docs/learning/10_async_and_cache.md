# 10 异步任务与缓存

## 1. 模块目的

异步模块把耗时抓取和周期监控从 API 请求中移出，并在 worker 丢失、消息重复投递时保持业务状态可恢复。缓存模块复用 Embedding 结果，降低远程调用成本和延迟。

## 2. 输入与输出

输入包括 CrawlTask ID、Celery broker 消息、Beat 定时事件、Redis 连接、Embedding 文本、Provider/模型/版本和缓存 TTL。

输出包括：

- Celery task result 和数据库中的 crawl task 状态；
- stale running 任务的 recovered/exhausted/queued 计数；
- 定时刷新的持久化告警；
- 命中或新生成的向量；
- `EmbeddingBatchResult` 的 cache_hits、embedded_count、input_chars 和 estimated_cost。

## 3. 数据流

```text
POST /api/crawl-tasks
  -> 数据库写 pending
  -> celery_app.send_task()
  -> Redis DB 1 broker
  -> worker execute_crawl_task
  -> PostgreSQL 原子 claim
  -> CrawlService
  -> 数据库 completed/failed

Celery Beat
  -> 每 60 秒 recover crawl tasks
  -> 每 300 秒 refresh monitoring alerts

IndexingService
  -> EmbeddingBatcher
  -> Redis/Memory cache
  -> 缺失项分批调用 Provider
  -> 写回 cache
```

Redis DB 0 用于应用缓存，DB 1 默认作为 Celery broker，DB 2 作为 result backend，避免键空间混用。

## 4. 核心类与文件

- `backend/app/tasks/celery_app.py`：Celery 配置、任务注册和 Beat schedule。
- `backend/app/tasks/crawl.py`：同步 Celery task 包装异步抓取执行。
- `backend/app/tasks/recovery.py`：stale 任务恢复与 pending 重排队。
- `backend/app/tasks/monitoring.py`：指标、健康和告警刷新。
- `backend/app/api/routes/crawl_tasks.py`：创建/retry 后入队以及 inline 测试路径。
- `backend/app/repositories/crawl.py`：原子 claim、stale recovery 和 pending 查询。
- `backend/app/crawler/state.py`：任务状态机。
- `backend/app/cache/embedding.py`：`EmbeddingCache`、内存和 Redis 实现。
- `backend/app/embedding/batcher.py`：cache key、批次、重试、节流与成本。
- `backend/app/config.py`：broker/result URL、TTL、soft/hard limit、visibility timeout。
- `backend/tests/unit/test_tasks.py`、`test_indexing_components.py` 与 `backend/tests/integration/test_crawl_reliability.py`。

## 5. 主要设计决策

1. Celery 使用 `task_acks_late=True` 和 `task_reject_on_worker_lost=True`，worker 完成前不会永久确认任务。
2. `worker_prefetch_multiplier=1` 避免单 worker 抢占过多长任务。
3. soft time limit 必须小于 hard time limit，Settings 在启动时校验。
4. Redis visibility timeout 与任务重投递配合，数据库 claim 决定业务上谁能执行。
5. 抓取互斥不依赖 Redis 锁，而用 `UPDATE ... WHERE status='pending'` 的数据库原子性；重复 delivery 是预期场景。
6. recovery 先把 stale running 恢复为 pending，超过最大次数则 failed，再把 pending IDs 重新发送。
7. Beat 只应运行一个 scheduler 实例，Compose 用独立 scheduler service 表达这一点。
8. Embedding cache key 包含 Provider、模型、版本和文本摘要，避免跨模型污染。
9. 当前 Redis cache 每次 get/set 创建并关闭 client，简单可靠但高吞吐下可改为连接复用。

## 6. 技术选型原因

- Celery：成熟的 Redis broker 支持重试、late ack、Beat 和 worker 监控。
- PostgreSQL 原子 claim：任务业务状态和互斥条件在同一事实库，避免分布式锁过期与状态脱节。
- Redis 分库：broker、result 和 cache 运维边界更清楚。
- Async service + sync task wrapper：Celery task 入口同步，但可通过 `asyncio.run()` 复用现有异步 Service。
- 版本化 Embedding cache：成本最高的确定性派生结果最适合缓存。
- 定时 recovery：弥补 worker 在更新 running 后异常退出的状态悬挂。

## 7. 常见故障模式

- API 已创建 pending 但 worker 不执行：Redis/broker 不通、worker 未启动或任务名未加载。
- task 重复投递：第二次 claim 返回空，Celery 包装读取当前状态后安全返回。
- running 长时间不结束：检查 soft/hard limit、worker 日志和 Beat recovery。
- recovery 不生效：scheduler 未运行、`crawl_stale_after_seconds` 太大或 task started_at 为空。
- 任务反复恢复：外部站点持续失败或 worker 每次崩溃；达到 max recovery 后会 failed。
- cache 总 miss：模型名、embedding version、Provider 或文本发生变化。
- Redis cache 不可用：生产配置不会静默写内存；明确 demo/test 才选择 memory provider。
- 多个 scheduler：同一定时任务可能重复触发，虽有数据库幂等仍会制造噪声。
- 解析、索引和评估当前主要由 API 同步执行，并非所有重任务都已队列化。

## 8. 调试步骤

1. 检查 `Settings.effective_celery_broker_url` 与 result backend 是否落在预期 Redis DB。
2. 执行 `celery -A app.tasks.celery_app:celery_app inspect ping` 检查 worker。
3. 查看 registered tasks 是否包含 crawl、recovery、monitoring。
4. 查询 CrawlTask 的 status、started_at、retry_count 和 error_message。
5. 手工调用 recovery task，检查 recovered/exhausted/queued 计数。
6. 对 cache 问题记录同一文本两次 `EmbeddingBatchResult`，第二次应出现 cache hit。
7. 检查 Redis key TTL 和 key 中模型/版本是否符合预期，禁止打印凭据。
8. 定向运行：`python -m pytest tests/unit/test_tasks.py tests/unit/test_indexing_components.py tests/integration/test_crawl_reliability.py`。

## 9. 面试问题与参考答案

### 9.1 late ack 是否保证 exactly once？

不能。worker 宕机时消息会重投，系统是至少一次交付。业务 exactly-once 效果来自数据库原子 claim、唯一约束和幂等写入。

### 9.2 为什么不用 Redis 分布式锁领取抓取任务？

状态本来就在 PostgreSQL。条件 UPDATE 同时完成互斥和状态迁移，避免锁成功但数据库更新失败，或锁过期而任务仍运行。

### 9.3 visibility timeout 的作用是什么？

消息被 worker 取走但未确认超过该时间后可重新可见。它必须大于正常任务时长，并与 hard time limit、恢复阈值协调。

### 9.4 缓存 key 为什么不能只用文本哈希？

同一文本用不同模型或版本会得到不同向量。只用文本会错误复用，导致检索维度或语义不一致。

### 9.5 soft limit 与 hard limit 有什么区别？

soft limit 允许任务捕获超时并清理；hard limit 由 worker 强制终止。ODIRAG 校验 soft 小于 hard，stale recovery 负责异常终止后的状态收敛。

## 10. 答辩问题与参考答案

### 10.1 worker 被杀后任务会丢吗？

late ack 使 broker 可重投，数据库中的 running 任务还会被周期 recovery 识别。重复执行由原子 claim 和唯一约束控制。

### 10.2 Redis 在系统中具体承担什么职责？

DB 0 用于 Embedding cache，DB 1 是 Celery broker，DB 2 是 result backend。当前抓取互斥由 PostgreSQL，不应夸大为 Redis 分布式锁。

### 10.3 如何证明缓存真实生效？

单元测试第一次调用 flaky Provider 经重试生成向量，第二次同模型/版本/文本 `cache_hits=2`、`embedded_count=0`。

### 10.4 scheduler 为什么独立成服务？

Beat 应保持单实例；若嵌进每个 worker，多副本会重复定时触发。独立 service 更容易设置健康检查和副本数。

### 10.5 当前异步化还有哪些不足？

解析、索引、评估和实验仍主要在 API 请求中执行；高负载生产环境应把这些变成可追踪任务，并复用同样的幂等和恢复策略。

## 11. 代码阅读路线

1. `backend/app/config.py` 的 Celery/Redis 字段
2. `backend/app/tasks/celery_app.py`
3. `backend/app/api/routes/crawl_tasks.py`
4. `backend/app/tasks/crawl.py`
5. `backend/app/repositories/crawl.py`
6. `backend/app/tasks/recovery.py`、`monitoring.py`
7. `backend/app/cache/embedding.py`
8. `backend/app/embedding/batcher.py`
9. 任务、缓存和恢复测试

## 12. 实践修改练习

把文档 reindex 改造成可恢复 Celery 任务。要求数据库保存 task 状态、文档版本和进度；同一 document/version 只能有一个运行任务；失败后可重试；旧版本任务不得覆盖新版本索引；API 返回任务 ID，并补充 worker 丢失恢复测试。
