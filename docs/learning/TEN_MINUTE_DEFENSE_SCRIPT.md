# ODIRAG 十分钟答辩稿

这份稿件按当前实现编写。演示前应先确认 `IMPLEMENTATION_STATUS.md` 的最新测试数字、服务 URL 和外部集成状态；答辩时只能陈述实际运行过的结果。

## 0:00-1:00 项目问题与目标

“我的项目叫 ODIRAG，是一个面向政府官方文档的采集、治理、检索增强生成和质量评估平台。它解决的不是简单上传文件聊天，而是完整的数据链问题：来源是否官方、文档是否重复和过时、回答证据是否足够、引用能否追溯、一次改动有没有让效果回归。

系统从网站来源配置开始，经过抓取、解析、版本化、规则与模型审查、人工批准、分块、Embedding、Qdrant 和 BM25 混合检索，再进入 SQL/RAG/组合路由、证据检查、引用或拒答。查询 trace、用户反馈、评估、实验和告警组成质量闭环。”

画面建议：打开 Dashboard 或架构图，不先展示代码。

## 1:00-3:00 数据采集、解析和审查

“来源由 `Source` 和 `SourceColumn` 管理，栏目选择器、分页和请求间隔可配置。抓取任务进入 Celery，但业务互斥不只依赖消息队列：`CrawlRepository.claim_task()` 用数据库条件 UPDATE 原子领取，重复消息不会让两个 worker 同时处理。

网络层禁用自动重定向，每一跳都检查 DNS 和公网 IP，并在读取前检查 Content-Length、读取时检查累计字节。附件还要经过扩展名和路径边界检查。worker 丢失后，Beat 会把 stale running 任务恢复或在超过次数后失败。

解析器统一返回 `ParsedArtifact`。HTML、PDF、DOCX、XLSX、TXT 和 ZIP metadata 都有真实实现。PDF 扫描件目前只标记 `requires_ocr`，我不会声称已经 OCR。内容变化时创建 `DocumentVersion`、记录 changed fields，并把索引标成 stale。

审查先跑可解释规则，再调用 Direct LLM 或 Coze 的严格 JSON adapter。结构化字段必须在白名单中，每个 evidence quote 必须真实出现在正文。模型不可用时文档进入 pending_llm，不会自动批准；边界样本由人工审核。”

画面建议：Sources -> Crawl Tasks -> Document Detail -> Reviews。

## 3:00-5:00 分块、索引和混合检索

“只有 approved 文档可以索引。`HeadingAwareChunker` 优先保持标题和段落边界，附件页码会进入 chunk。Embedding 支持批量、重试、Redis 缓存和模型版本；chunk ID 包含文档版本、页码、模型版本和内容哈希，所以重复 reindex 是幂等的。

PostgreSQL 保存 chunk 和血缘，Qdrant 保存向量与 metadata payload，BM25 从数据库 indexed chunks 重建。PostgreSQL 是真源，向量和 BM25 都可重建。

检索支持 BM25、Vector、Hybrid、Hybrid+Rerank 四种模式。BM25 和向量分数不可直接相加，所以我使用 RRF，按排名累加 `1/(k+rank)`。`/api/search/debug` 会返回 query analysis、两路召回、融合、重排、最终结果和各阶段耗时。”

画面建议：Documents 中触发 reindex，再用 Chat 或 debug 数据展示 citations/trace。

## 5:00-7:00 路由、证据、引用和拒答

“查询路由分三类。纯计数走 SQLAlchemy 白名单模板；语义问题走 RAG；带时间、地区范围的总结走 SQL+RAG。系统从不执行 LLM 生成的任意 SQL。

检索后不是直接让模型回答。`GroundingService` 检查证据数量、最低分、官方来源、问题覆盖、冲突和新旧政策。证据不足就拒答。

每个引用由服务从真实 RetrievalHit 构造，包含 document ID、chunk ID、标题、来源、日期、URL、页码和原文 quote。LLM 只能选择允许的 chunk ID；回答里出现的 URL 也必须在引用集合中。

每次查询保存完整 `QueryTrace`，还可以从引用沿 `Chunk -> DocumentVersion -> CrawlTask -> Source` 做 lineage。缺失环节会明确返回 incomplete，而不是补造。”

现场演示建议依次输入：

1. 一个有证据的政策支持问题，展开 citation 和 trace；
2. 一个数量问题，展示 SQL 路由；
3. 一个无关问题，展示 refusal reasons。

## 7:00-8:00 评估、实验和反馈

“评估题包含预期文档、chunk、答案点、过滤条件和拒答标签。系统实际运行检索和 Chat，再计算 Recall@1/5/10、MRR、nDCG、文档与 chunk hit、答案点覆盖、引用准确率与完整率、拒答准确率、幻觉率、P50/P95、tokens 和 cost。

报告同时生成 JSON、CSV、Markdown 和图表数据。幻觉率只统计 callback 明确评估的 claim；如果 assessed claims 为 0，我不会把 0% 说成没有幻觉。

实验框架对 baseline 和 candidate 分别构建分块、Embedding、top-k、RRF、重排、阈值和 prompt 配置，再输出 metric delta、新回归和失败案例。用户的错误引用、漏文档、回答不完整或拒答错误反馈，可以转换为 verified evaluation question，形成真实回归样本。”

画面建议：Evaluations -> report，Experiments -> compare，Activity -> convert feedback。

## 8:00-9:00 工程、安全和可观测性

“认证使用 access/refresh token，refresh rotation 和 logout 会递增用户 token_version，使旧 token 立即失效。生产配置拒绝默认密钥、明文管理员密码、debug、非 HTTPS CORS 和关闭限流。

监控同时记录路由与数据库 P50/P95/P99、抓取失败、索引失败、RAG 延迟、拒答、token、成本、评估回归和依赖健康。告警持久化并支持 acknowledge/resolve。

当前固定窗口限流和路由指标是单进程内存实现；多副本需要 Redis 或网关方案。应用层 SSRF 仍存在 DNS 校验到 socket 连接的时间窗，生产还要配置容器出口网络策略。这些都在文档中明确记录。”

画面建议：Monitoring 页面，指出 DB P95、依赖状态和告警操作。

## 9:00-10:00 部署、实测与结论

“Compose 定义了 backend、frontend、PostgreSQL、Redis、Qdrant、worker、scheduler 和 Nginx 八个服务。backend 以 UID 10001 非 root 运行，entrypoint 自动执行 Alembic；PowerShell 和 shell 一键脚本会构建、等待健康、seed 并通过真实 API reindex。

CI 运行 Ruff、Black、mypy、迁移升降级、pytest coverage、前端 lint/type/test/build、Compose/Nginx 校验、镜像构建和非 root 登录 smoke。

最新 Phase 14 检查记录为后端 119 tests passed、82.87% coverage，前端 6 tests passed，并通过 type-check、lint 和 production build。一次本地 deterministic demo 负载测试使用每场景 20 请求、并发 4、warmup 2：search P95 29.49ms，chat P95 345.95ms，数据库 P95 183.83ms。它们低于指南工程目标，但只代表本机小样本，不是生产 SLA。

当前机器没有 Docker，因此我不能声称完整 Compose 已在本机运行通过；容器实际验收依赖有 Docker 的环境和 CI。外部 LLM、Embedding、Rerank 凭据也需要部署者提供。我的结论是：项目已经形成可运行、可测试、可追溯的完整工程链，同时保留并公开了尚未完成的生产化边界。”

## 演示失败时的备用说明

### 外部 Provider 不可用

“这不是假数据切换。健康接口和结构化错误会显示 Provider unavailable；当前演示使用配置明确标注的 deterministic Provider，真实 adapter 和合同测试仍在。”

### Redis/Qdrant 临时不可用

“先展示 `/api/system/health` 的 degraded 状态和告警，再说明受影响能力。PostgreSQL 中的业务数据不会因此被伪造或丢弃。”

### Chat 无结果

“我会展开 search debug，判断是 Analyzer、BM25、Vector、RRF、Rerank 还是 Grounding 门导致。无证据时正确行为是拒答。”

### Docker 无法启动

“展示 Compose、entrypoint 和 CI smoke 配置，但明确说本次环境没有完成运行验收。绝不把静态配置校验描述为容器已运行。”

## 高频追问的一句话回答

- 为什么 PostgreSQL 是真源？版本、审查、外键和事务属于业务事实，Qdrant/BM25 可重建。
- 如何防止引用幻觉？服务构造 citation，模型只能选择已检索 chunk ID，URL 也做 allowlist。
- 如何保证抓取幂等？数据库原子 claim、canonical URL 唯一约束和稳定状态机。
- 为什么用 RRF？BM25 与向量分数不可比，排名融合无需分数校准。
- 如何撤销 JWT？refresh/logout 递增 token_version，旧 token 版本不再匹配。
- 如何发现回归？固定评估集、实验 baseline/candidate、失败案例和 feedback 转题。
- 项目最大真实限制？外部服务和完整 Docker 栈尚需目标环境验证，多副本限流/指标仍需共享基础设施。
