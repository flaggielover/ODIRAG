# 13 自主来源发现与来源池扩展

## 1. 模块目的

Phase 16 解决的不是“配置一个已知网站”，而是当知识库出现内容缺口时，安全地提出新的官方来源候选，并让人工决定是否纳入来源池。完整链路是：内容缺口检测 -> 候选官网发现 -> 官方身份校验 -> 栏目发现 -> 试抓取 -> 质量评分 -> 人工审批 -> 来源激活。

该模块不会把搜索引擎结果直接写成可抓取来源。外部搜索只提供候选线索，数据库证据、受限网络访问、质量门槛和人工审批共同决定是否激活。

## 2. 输入与输出

输入包括：主题、地区、机构层级、最低来源数、最低匹配文档数、最大候选数，以及 Brave Search 凭据和官方域名后缀策略。

输出包括：

- `SourceDiscoveryRun`：一次缺口检测和自动阶段的状态、计数与错误；
- `SourceCandidate`：候选主页、搜索排名、官方校验证据、试抓统计和总质量分；
- `SourceCandidateColumn`：发现的同站栏目、选择器、试抓结果和栏目质量分；
- `SourceDiscoveryEvent`：每个阶段的追加式审计事件；
- 人工批准后创建的 `Source` 和 `SourceColumn`；
- `/api/source-discovery/metrics` 返回的真实数据库聚合指标。

## 3. 数据流

```text
POST /api/source-discovery/runs
  -> PostgreSQL 统计现有 enabled sources 与 approved documents
  -> 无缺口：no_gap，停止
  -> 有缺口：pending，发送 odirag.source_discovery.run
  -> Brave Search API 返回候选 URL
  -> HttpFetcher 校验 DNS/IP/重定向/响应大小
  -> 校验 trusted suffix、HTTPS、同站跳转和页面标识
  -> BeautifulSoup 发现政策/通知/公开栏目
  -> 每栏最多抓取配置数量的详情页
  -> 计算官方性、栏目覆盖、成功率、文本丰富度
  -> pending_approval
  -> 管理员 approve
  -> 管理员 activate
  -> 创建 enabled Source + SourceColumn
```

如果 Celery 入队失败，API 先把运行改为 `failed` 并写 `queue_failure` 事件，再返回 503。重试复用候选审计记录、删除旧的试抓栏目并重新执行，避免 `(run_id, homepage_url)` 唯一约束造成永久空跑。

## 4. 核心类与文件

- `backend/app/models/source_discovery.py`：四张 Phase 16 业务表。
- `backend/alembic/versions/0004_source_discovery.py`：建表、约束和索引迁移。
- `backend/app/source_discovery/providers.py`：Brave Search 协议、错误转换和响应解析。
- `backend/app/repositories/source_discovery.py`：缺口查询、原子 claim、状态聚合和重试重置。
- `backend/app/services/source_discovery.py`：完整业务编排、质量公式、审批和激活。
- `backend/app/api/routes/source_discovery.py`：管理员 API 与队列失败补偿。
- `backend/app/tasks/source_discovery.py`：Celery 同步入口复用异步 Service。
- `backend/app/schemas/source_discovery.py`：请求、响应、事件和指标契约。
- `backend/tests/integration/test_source_discovery_api.py`：从缺口到激活的 API 回归。

## 5. 主要设计决策

1. 搜索 Provider 只发现候选，不负责判定官方身份。
2. 内容缺口来自数据库实时计数，不使用硬编码仪表盘数字。
3. 官网和试抓页面复用抓取器的 SSRF、DNS、重定向和流式大小限制。
4. 官方状态必须保存具体证据；后缀规则是可配置政策，不是法律证明。
5. 质量分由四个可检查分量组成：`0.35*官方性 + 0.15*栏目覆盖 + 0.25*试抓成功率 + 0.25*文本丰富度`。
6. 达到分数线只进入 `pending_approval`，不能自动激活。
7. 审批与激活分成两个 API，便于职责分离和操作审计。
8. 运行和候选由数据库条件更新 claim，避免重复 worker 同时推进。
9. 搜索凭据缺失时明确返回 503，不回退到测试数据。
10. production/staging 禁止 deterministic source discovery，以及 deterministic embedding/rerank、memory vector/cache。

## 6. 技术选型原因

- Brave Search API：提供仍可用的正式 Web Search JSON API；代码不依赖已退役的 Bing Search v7。
- PostgreSQL：状态、审批、唯一约束和事件需要可事务化的业务真相。
- Celery：网络发现和试抓属于长任务，不能阻塞普通 API 请求。
- BeautifulSoup/lxml：适合从未知官网首页提取同站栏目候选。
- 复用 `HttpFetcher`：新功能不应绕过既有 SSRF 和响应大小控制。
- Pydantic：限制主题、计数和决策原因，并生成一致 OpenAPI。

## 7. 常见故障模式

- `PROVIDER_UNAVAILABLE`：Brave key 未配置、网络失败或服务端 5xx；运行会持久化为 failed。
- `validation_failed`：候选不在官方后缀策略内、跳转跨站或页面抓取失败。
- `NO_POLICY_COLUMNS_DISCOVERED`：主页可达但没有匹配政策/通知/公开关键词的同站链接。
- `NO_QUALITY_DOCUMENTS`：栏目详情文本过短或试抓全部失败。
- `QUALITY_SCORE_BELOW_THRESHOLD`：证据存在但综合质量未达配置门槛。
- `queue_failure`：Redis/Celery 不可用；运行必须可 retry，不能停留 pending。
- 重试候选重复：应复用原 candidate ID 并清理旧 column，不应新增重复候选。
- 错误审批：候选只有在 `pending_approval` 才能 approve，只有 `approved` 才能 activate。
- 指标无告警：当前聚合 metrics 已实现，但尚未接入全局 Alert 规则。

## 8. 调试步骤

1. 检查 `/api/source-discovery/metrics` 的 run/candidate/column 状态计数。
2. 读取 `/api/source-discovery/runs/{id}/events`，确认最后成功阶段。
3. 检查 worker 注册任务是否包含 `odirag.source_discovery.run`。
4. 校验 `ODIRAG_SOURCE_DISCOVERY_PROVIDER=brave` 和密钥是否由后端 secret 注入。
5. 对 `validation_failed` 查看 `official_evidence_json` 的 host、suffix、HTTPS 和 same_site。
6. 对低分候选查看 `quality_breakdown_json` 和各栏目试抓计数。
7. 模拟 broker 失败，确认 run 为 failed、存在 queue_failure 事件且 retry 可用。
8. 运行 `pytest tests/unit/test_source_discovery.py tests/integration/test_source_discovery_api.py`。
9. 运行 Alembic `upgrade head -> downgrade 0003 -> upgrade head` 往返测试。

## 9. 面试问题与参考答案

### 9.1 为什么不能把搜索结果直接变成 Source？

搜索排名不是官方身份或内容质量证明。直接激活会把 SEO 页面、镜像站甚至恶意站点带入抓取系统，因此还需要安全抓取、官方域名证据、试抓质量和人工审批。

### 9.2 内容缺口如何计算？

Repository 按主题和地区统计启用来源与已批准文档，和请求中的最低来源数、最低文档数比较。任一不足就产生 gap；计算参数和结果同时写入 `gap_evidence_json`。

### 9.3 为什么审批和激活要分开？

审批表示人确认候选可信，激活表示把配置投入生产抓取。分开后可以实施双人复核、变更窗口或审批后延迟启用，也让审计语义更清楚。

### 9.4 如何保证重试不会产生重复候选？

数据库有 `(run_id, canonical_homepage_url)` 唯一约束。重试查找并复用旧 candidate，清理旧试抓 columns、重置派生字段，再追加新的事件；不会创建第二条候选记录。

### 9.5 质量分为什么仍不能替代人工审批？

质量分只量化可观察的技术信号，例如域名、栏目数、成功率和文本长度，不能理解机构授权、转载关系、政策有效性或地区治理规则，所以只能作为排序和门槛。

## 10. 答辩问题与参考答案

### 10.1 你是否真的调用过 Brave 线上接口？

当前本地验证是 HTTP 协议契约测试，没有配置真实 Brave key，因此不能宣称线上成功。真实 API 缺凭据会返回 503；生产验收清单要求在获批网络和凭据下补证据。

### 10.2 Phase 16 哪些部分已经真实实现？

数据库模型、迁移、API、Celery 任务、缺口查询、官网安全校验、栏目解析、试抓、评分、审批、激活、事件和指标都是真实代码；外部搜索和真实官网只做了可替换的 HTTP 契约/fixture 验证。

### 10.3 如何证明人工门禁有效？

集成测试先对 `pending_approval` 候选调用 activate，得到 409；approve 后再次 activate 才创建 Source，并验证 created source 和 column 均 enabled。

### 10.4 队列宕机时会不会出现孤儿任务？

不会保持不可重试的 pending。API 捕获 send_task 异常后调用事务补偿，将 run 写为 failed、记录错误类型和 queue_failure 事件，然后返回 503；修复 broker 后可调用 retry。

### 10.5 当前监控还缺什么？

已有持久事件和聚合 metrics API，前端可以展示 pending、failed、activated 等状态；尚未把审批积压和连续 provider 失败接入全局 Alert 规则，也未验证 Prometheus/集中告警链路。

## 11. 代码阅读路线

1. `backend/app/schemas/source_discovery.py`
2. `backend/app/models/source_discovery.py`
3. `backend/alembic/versions/0004_source_discovery.py`
4. `backend/app/repositories/source_discovery.py`
5. `backend/app/source_discovery/providers.py`
6. `backend/app/services/source_discovery.py` 的 `create`、`execute`、`_validate_official_status`
7. 同文件的 `_discover_columns`、`_trial_crawl_column`、`_score_candidate`
8. 同文件的 `approve`、`activate`、`retry`、`mark_queue_failure`
9. `backend/app/api/routes/source_discovery.py`
10. `backend/app/tasks/source_discovery.py`
11. Phase 16 单元和集成测试

## 12. 实践修改练习

为不同地区增加“官方身份策略”配置表，而不是只使用全局后缀列表。要求：策略按地区版本化；每条规则记录生效时间、允许后缀和人工说明；一次 discovery run 必须保存使用的策略版本快照；旧运行回放时不得读取新规则；迁移支持 PostgreSQL 和 SQLite；API 提供只读策略与管理员发布接口；测试覆盖规则变更、并发发布、旧快照回放和无匹配策略时的安全拒绝。

