# ODIRAG 常见技术问题

以下问答基于当前仓库，不把计划中的能力写成已完成能力。

## 一、架构与数据边界

### 1. 为什么采用 API -> Service -> Repository/Provider 分层？

Route 只负责协议和权限，Service 编排业务状态，Repository/Provider 处理数据库和外部系统。这样抓取、索引、评估可在不启动 HTTP 的情况下测试，也避免前端或路由直接操作基础设施。

### 2. 为什么 PostgreSQL 是业务真源？

来源、文档版本、审查、外键、反馈和血缘需要事务与约束。Qdrant 和 BM25 只保存检索派生状态，可以从 PostgreSQL 的 approved/indexed 数据重建。

### 3. `ApplicationRuntime` 为什么是长生命周期对象？

BM25、Provider、缓存和向量库配置需要在请求间复用。`runtime.retrieval_engine()` 每次创建轻量引擎，但共享底层索引和 Provider。

### 4. 外部服务不可用时为什么不直接关闭整个应用？

系统采用诚实降级。健康接口报告 dependency unavailable，相关接口返回结构化 503，仍可保留登录、数据库查询和诊断能力；不能返回假的成功结果。

### 5. SQLite 在项目中的角色是什么？

主要用于单元/集成测试、容器 smoke 和本地 demo。生产业务数据库目标是 PostgreSQL；SQLAlchemy 与 Alembic 同时覆盖两者的兼容路径。

### 6. 为什么 `auto_create_schema` 默认关闭？

`create_all()` 不能表达可靠升级和降级历史。正式启动通过 Alembic revision 管理，auto create 只适合显式测试/开发。

## 二、抓取与数据治理

### 7. 如何防止重复抓取产生重复文档？

URL 先 canonicalize，Service 查询已存在记录，数据库再以 `(source_column_id, canonical_url)` 唯一约束兜底。重复消息还要经过 CrawlTask 原子 claim。

### 8. 为什么任务系统不是 exactly once？

Celery/Redis 提供至少一次交付；worker 崩溃会重投。ODIRAG 通过原子状态迁移、唯一约束和幂等写入获得业务上的重复安全。

### 9. SSRF 防护包含哪些层？

禁止非 HTTP(S)、userinfo、localhost、私网/环回/链路本地/保留/组播/未指定地址；解析所有 DNS 结果；每个重定向重新校验；响应限流；文件存储做路径和扩展名二次校验。

### 10. SSRF 防护还缺什么？

DNS 校验与真实 socket 连接之间仍有 rebinding 时间窗。生产应让传输固定到已验证 IP，或在爬虫容器/出口代理层阻断内网和元数据网段。

### 11. 为什么附件失败不回滚文档？

主正文仍有价值。附件单独记录 download/parse status，后续可重试；一个失效附件不应导致整篇官方文档丢失。

### 12. worker 丢失后如何恢复？

late ack 让消息可重投；Beat 每分钟扫描 stale running。未达到次数上限的任务重置 pending 并入队，达到上限后 failed，错误码为 worker lost 相关状态。

### 13. SimHash 已经用于自动归并全部近重复吗？

没有。哈希、SimHash、汉明距离和权威来源选择函数已实现并测试，但抓取主链当前主要完成 URL 幂等；完整语义近重复归并仍是明确扩展项。

## 三、解析、审查与索引

### 14. 为什么解析器统一返回 `ParsedArtifact`？

下游需要的不只是 text，还有 section、table、page、metadata 和 OCR 状态。统一协议让清洗、版本和索引不依赖具体文件类型。

### 15. 扫描 PDF 如何处理？

PyMuPDF 提取文本后按每页最低字符判断 `requires_ocr`。当前没有内置 OCR，系统会诚实标记而不是生成虚假文字。

### 16. 内容更新如何触发版本？

新解析文本经 clean 后计算去空白 SHA256；与现有 hash 不同才保存快照、版本加一、更新 SimHash/changed fields，并把索引标 stale。

### 17. LLM 审查如何防止字段幻觉？

严格 `ReviewResult` schema、字段白名单、置信度范围和 evidence quote 原文子串检查。任何失败都作为 Provider invalid response，不写结构知识。

### 18. 为什么 PromptVersion 内容不可修改？

历史审查、评估和 trace 必须可复现。同一 name/version 内容哈希不同会报错，变更只能创建新版本。

### 19. 为什么只有 approved 文档能索引？

未经审查或待人工确认内容不应进入生产检索。`IndexingService` 在入口检查 final status，不由调用者绕过。

### 20. Qdrant 与 PostgreSQL 不能事务一致怎么办？

使用确定性 point ID、状态机、幂等 upsert、切换前后顺序和补偿删除。失败文档标 failed，可重试；业务真源仍在 PostgreSQL。

### 21. 为什么 chunk ID 包含模型和版本？

同一文本换 embedding 模型后向量不同。ID 包含 Provider/model/version 和内容哈希，旧点可被明确识别为 stale。

### 22. BM25 为什么单独重建？

它是从 indexed chunks 生成的派生快照。独立 rebuild 命令便于恢复、发布和实验，也避免把内存索引当业务数据库。

## 四、检索、路由与回答

### 23. 为什么同时使用 BM25 和向量？

BM25 擅长政策编号、机构名和固定术语；向量擅长语义改写。两者互补，单一路径更容易漏召回。

### 24. 为什么用 RRF 而不是分数相加？

BM25 与 cosine 分布不可直接比较。RRF 只使用 rank，减少分数校准依赖，并可稳定合并重复 chunk。

### 25. RRF 的分数为什么看起来很小？

它是多个 `1/(rrf_k+rank)` 的和，不是相关概率。阈值必须基于评估实验，不能按 cosine 的 0.8 直觉解释。

### 26. Metadata filter 在哪里执行？

Analyzer 先产生白名单 filters；BM25、InMemoryVectorStore 和 Qdrant 都在召回阶段应用。SQL count 也用同一 filter 语义。

### 27. 系统会执行 LLM 生成的 SQL 吗？

不会。当前 `QueryRouter` 是确定性规则，SQL 路径只调用 SQLAlchemy 白名单 count 模板。LLM 协议中的 query plan 没有被当作 SQL 文本执行。

### 28. SQL+RAG 为什么要两条路径？

结构 count 必须对完整数据库集合计算；RAG top-k 只用于语义证据。组合路径使用同一 filters，使统计范围与总结范围一致。

### 29. 证据不足如何判断？

GroundingService 检查最低 hit 数/分数、官方来源、query coverage、metadata 冲突和过时政策。任何 required 条件失败都会生成拒答 reason。

### 30. 如何防止模型伪造引用？

Citation 由服务从 RetrievalHit 构造。模型只返回 cited chunk IDs，必须属于 eligible set；回答里的 URL 也必须属于最终 Citation URL 集。

### 31. 如何处理旧政策与新政策同时出现？

按 document_number/policy key/title 分组比较 publish_date，旧 chunk 标 outdated 并从 citation 排除；若状态冲突且配置要求，则拒答。

### 32. Extractive 模式是不是假 LLM？

不是。它明确记录为 `extractive-grounded-v1`，直接组合真实证据 quote，不声称调用生成模型。外部模型不可用也不会返回伪造生成结果。

## 五、评估、实验与可观测性

### 33. Recall、MRR、nDCG 分别看什么？

Recall 看前 k 覆盖相关项的比例；MRR 看首个相关项位置；nDCG 对整个排名位置折损，体现排序质量。

### 34. Citation accuracy 和 completeness 为什么分开？

Accuracy 是 cited 中正确的比例，Completeness 是 expected 中被引用的比例。前者防错误引用，后者防漏引。

### 35. 幻觉率为 0 就能说无幻觉吗？

不能。当前只统计 callback 明确标注的 claim；必须同时报告 assessed claims/questions。分母为 0 时，0 代表未测量而非通过。

### 36. 单题执行异常如何进入报告？

默认不 fail-fast。Runner 标记 error_stage 为 retrieval 或 chat，保留已有数据，用空结果计算该题并继续其他题。

### 37. 实验如何避免污染生产索引？

`ODIRAGVariantEvaluationRunner` 为 baseline/candidate 建独立 in-memory BM25/vector store 和配置，再分别运行真实评估服务，不覆盖 runtime Qdrant。

### 38. 用户反馈如何进入回归？

负反馈类型可生成 verified `EvaluationQuestion`，继承 trace query/filters/citations 和用户指定预期文档；稳定 question ID 保证重复转换幂等。

### 39. QueryTrace 保存什么？

query type、filters、四阶段检索结果、最终上下文、prompt snapshot、model、answer、citations、refusal、latency、token 和 cost。

### 40. 告警是瞬时计算还是持久化？

候选由 MonitoringService 计算，但写入 `Alert` 表。相同 key 更新 occurrence；条件消失自动 resolved；管理员可 acknowledge/resolve。

## 六、安全、前端与部署

### 41. JWT 如何立即撤销？

access/refresh 都带 token version。refresh rotation 和 logout 递增数据库版本，旧 token 与用户当前版本不匹配而 401。

### 42. 当前限流是否支持多副本？

支持代码路径。非 test 环境的 `RedisFixedWindowRateLimiter` 用单 key Lua 脚本原子执行计数和过期，Redis 不可用时返回结构化 503；test 才使用 `InMemoryFixedWindowRateLimiter`。目标环境仍需验证 Redis ACL、故障转移、网关协同和多副本公平性。

### 43. Provider 原始错误为什么不返回前端？

远程错误可能包含 URL、内部响应或敏感细节。服务端结构化日志保留 reason，客户端只得到 provider 名和稳定错误码。

### 44. 前端如何防止并发 refresh 冲突？

`api/client.ts` 用全局 `refreshPromise` single-flight。所有 401 请求等待一次 token rotation，成功后各自只重试一次。

### 45. 前端 Markdown 如何防 XSS？

模型/文档文本先由 marked 转 HTML，再经过 DOMPurify；Nginx 还设置 CSP、frame-ancestors 和 nosniff。

### 46. 当前前端是否使用 Pinia、Axios 和 ECharts？

没有。实际实现是 Vue reactive module、原生 fetch 和定制组件/样式；文档必须如实说明，不能因为指南列出目标栈就声称已使用。

### 47. Compose 为什么使用 profiles？

基础 API 开发只需 backend 与依赖；`ui` 开 frontend 和 nginx，`async` 开 worker 和 scheduler。一键 demo 同时启用两个 profile。

### 48. 谁负责数据库迁移？

backend entrypoint 重试 `alembic upgrade head`；worker/scheduler 设置 `ODIRAG_RUN_MIGRATIONS=false` 并等待 backend healthy，避免并发迁移。

### 49. 如何证明容器是非 root？

Dockerfile 创建 UID/GID 10001 的 `odirag` 用户；CI smoke 运行 `id -u` 断言 10001，并检查 `/app/data` 可写和 SQLite 文件存在。

### 50. 本地性能数字能否当生产 SLA？

不能。仓库同时保留 deterministic demo、Gold 延迟、有界生产观测和故障注入样本；它们
各自证明特定链路，不构成长周期容量或外部 SLA。报告必须给样本量、并发、环境、
Provider 模式和置信度。

## 七、当前最重要的真实限制

### 51. 当前最重要的后端限制有哪些？

生产是单节点而非 HA；OCR Provider 未接入；近重复归并未完全贯通；部分长任务仍在
请求路径；多副本下 BM25/cache/task/连接池和 Redis 公平性尚未验收；通用出站路径仍需
网络层纵深防御。Python 生产与开发依赖已有 lock 文件，不能再列为缺失项。

### 52. 当前最重要的前端限制有哪些？

已有 Vitest、fixture Playwright 和公网 headless Chrome 验收，但大部分页面仍缺独立组件
测试，production-backend E2E 覆盖有限；类型未从 OpenAPI 生成；sessionStorage 不跨标签
页；列表分页和 i18n 不完整；未采用 Pinia/Axios/UI/ECharts。

### 53. 当前最重要的部署限制有哪些？

当前生产已完成 Docker、TLS、受保护 secrets、资源限制、DR、Prometheus/Grafana、
不可变 digest 发布和回滚验收。剩余限制是单节点、无第三方持久 paging/SLA、SSH 稳定
来源 CIDR 未收紧、Qdrant client/server 版本待对齐、HSTS 仍为一天，以及备份调度/保留
删除由 operator 驱动且首个 off-host sink 不是 immutable/object-locked。

### 54. 答辩时最不应该说什么？

不要把 deterministic Provider 说成真实模型，把配置文件存在说成服务已运行，把未测量的幻觉率说成 0%，把本地 P95 说成生产 SLA，或把静态 Docker 校验说成完整栈验收通过。
