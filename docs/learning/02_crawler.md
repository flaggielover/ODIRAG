# 02 来源管理与抓取

## 1. 模块目的

抓取模块把可配置的政府网站栏目转化为可追踪的 `Document`、`Attachment` 和 `DataLineage` 记录。它同时处理任务状态、分页、请求节流、URL 规范化、SSRF 防护、附件落盘、重复 URL 和 worker 丢失恢复。

## 2. 输入与输出

输入包括：

- `config/sites.yaml` 或 `/api/sources` 写入的 `Source`、`SourceColumn`；
- 栏目 URL、CSS selectors、pagination 配置、`max_pages` 和请求间隔；
- `/api/crawl-tasks` 创建的 full/incremental 任务；
- Celery worker 接收的任务 ID。

输出包括：

- `crawl_tasks` 中的状态和 discovered/fetched/success/duplicate/failed 计数；
- `documents` 中的正文、原始 HTML、规范 URL、哈希和来源元数据；
- `attachments` 中的下载状态、文件大小、哈希和本地路径；
- 从 source、crawl task 到 document 的初始 `data_lineage`；
- 失败时明确的任务状态和错误类型。

## 3. 数据流

```text
Source/SourceColumn
  -> POST /api/crawl-tasks
  -> pending CrawlTask
  -> Celery odirag.crawl.execute
  -> CrawlRepository.claim_task() 原子领取
  -> CrawlerAdapterRegistry
  -> GenericCrawler 或 GovCnLatestJsonAdapter
  -> HttpFetcher（逐跳 URL 校验 + 限流读取）
  -> Document/Attachment/DataLineage
  -> completed 或 failed
```

`backend/app/tasks/recovery.py` 每分钟扫描超过 `crawl_stale_after_seconds` 的 running 任务。未超过恢复次数的任务回到 pending 并重新入队，超过上限的任务标记 failed。

## 4. 核心类与文件

- `backend/app/services/sources.py`：来源 CRUD 后的连通性测试，复用安全 `HttpFetcher`。
- `backend/app/services/source_config.py`：严格解析 `config/sites.yaml`。
- `backend/app/services/crawl.py`：创建、执行、重试、取消和附件下载的业务编排。
- `backend/app/crawler/generic.py`：列表发现、分页、详情页和附件发现。
- `backend/app/crawler/adapters.py`：`CrawlerAdapter` 协议与 `GovCnLatestJsonAdapter`。
- `backend/app/crawler/registry.py`：parser_type 到适配器的注册表。
- `backend/app/crawler/fetcher.py`：重试、手动重定向、流式大小限制。
- `backend/app/crawler/urls.py`：URL 规范化、DNS 解析与公网地址校验。
- `backend/app/crawler/storage.py`：安全文件名、扩展名白名单和路径边界。
- `backend/app/crawler/state.py`：任务状态迁移。
- `backend/app/repositories/crawl.py`：原子 claim、过期恢复和数据库写入。
- `backend/app/tasks/crawl.py`、`recovery.py`、`celery_app.py`：异步执行和可靠性配置。
- `backend/tests/integration/test_fixture_crawl.py`、`test_crawl_reliability.py` 和 `backend/tests/unit/test_http_fetcher_security.py`。

## 5. 主要设计决策

1. 抓取适配器遵守统一 `crawl_column()` 协议，通用 HTML 和 gov.cn JSON feed 可并存。
2. `HttpFetcher` 禁止自动重定向，每一跳都重新执行 `validate_public_url()`，防止公网 URL 跳到内网。
3. DNS 结果中只要包含非公网地址就拒绝；禁止 userinfo、localhost、环回、私网、链路本地、保留、组播和未指定地址。
4. 同时检查 `Content-Length` 和流式累计字节数，防止无长度头或伪造长度绕过上限。
5. 文件存储再次检查大小、扩展名和 resolve 后路径，形成第二道防线。
6. `claim_task()` 使用 `UPDATE ... WHERE status='pending'`，同一任务重复投递只有一个执行者能领取。
7. Celery 使用 late ack、worker lost reject、prefetch=1、软硬超时和 visibility timeout。
8. 数据库唯一约束 `(source_column_id, canonical_url)` 是并发条件下 URL 幂等的最终保障。

## 6. 技术选型原因

- httpx async streaming：既支持并发网络 I/O，又能在缓冲前控制响应大小。
- BeautifulSoup + lxml：CSS selector 配置适合结构差异较大的政府站点。
- Celery + Redis：将长抓取从 API 请求生命周期移出，并支持重投递与定时恢复。
- SQL 原子更新：任务锁与业务状态放在同一数据库中，避免仅靠进程锁。
- tenacity：只对连接错误和读取超时做有限退避，不重试安全拒绝和超限响应。
- YAML + Pydantic：站点配置可版本化，同时拒绝未知字段和非法数据。

## 7. 常见故障模式

- `UnsafeUrlError`：域名解析到私网、localhost、云元数据地址或 URL 含账号信息。
- `RedirectLimitError`：重定向循环或超过 `crawler_max_redirects`。
- `ResponseTooLargeError`：声明长度或实际流超过 `max_download_bytes`。
- selector 不匹配：详情页缺少 title/content，`GenericCrawler` 抛出明确错误。
- 附件失败但文档成功：附件记录标为 failed，文档记录保留，这是设计行为。
- 重复任务投递：第二个 worker 得到 `TASK_ALREADY_CLAIMED`，Celery 包装将其当作安全 no-op。
- worker 崩溃：任务保持 running，恢复任务稍后重置；达到最大恢复次数后失败。
- DNS rebinding 时间窗：当前代码在请求前解析和校验，但没有把实际连接固定到已校验 IP；生产还应配合网络出口策略或固定解析传输。

## 8. 调试步骤

1. 调用 `/api/sources/{id}/test`，确认最终 URL、HTTP 状态和延迟。
2. 检查 `SourceColumn.parser_type` 是否在 `CrawlerAdapterRegistry.default()` 注册。
3. 用 fixture 先验证 selectors，再访问真实站点，避免把站点变化误判为队列问题。
4. 查看 crawl task 的 status、started_at、retry_count 和 error_message。
5. 检查 worker 日志中 `odirag.crawl.execute` 是否收到任务。
6. 若任务卡在 running，核对 beat 是否执行 `odirag.crawl.recover` 及 stale 阈值。
7. 附件问题检查 URL 后缀、允许扩展名、字节上限和 `settings.data_dir / "attachments"` 的写权限。
8. 定向运行：`python -m pytest tests/unit/test_http_fetcher_security.py tests/integration/test_fixture_crawl.py tests/integration/test_crawl_reliability.py`。

## 9. 面试问题与参考答案

### 9.1 为什么每个重定向都要做 SSRF 校验？

初始 URL 是公网并不代表最终目标安全。攻击者可让公网地址 302 到 `127.0.0.1` 或 `169.254.169.254`，所以必须禁用自动跳转并逐跳验证。

### 9.2 为什么响应大小要检查两次？

`Content-Length` 可以提前拒绝，但它可能缺失或造假；流式累计检查覆盖真实读取大小。`FileStorage` 再检查一次，防止其他调用方绕过 Fetcher。

### 9.3 如何保证抓取任务只执行一次？

严格说任务系统提供至少一次投递。ODIRAG 通过数据库原子 claim、URL 唯一约束和幂等写入，使重复投递不产生重复业务结果。

### 9.4 为什么附件失败不回滚整个文档？

正文和附件是不同可用性单元。保留文档并记录附件失败，后续可以单独重试，不会因为一个失效链接丢失主文档。

### 9.5 通用爬虫和站点适配器如何取舍？

结构稳定、CSS 可配置的站点用 `GenericCrawler`；特殊 JSON feed 或非标准协议实现 `CrawlerAdapter`，复用同一个 Fetcher 和详情解析器。

## 10. 答辩问题与参考答案

### 10.1 如何证明抓取是幂等的？

fixture 集成测试重复执行同一栏目并检查记录数；数据库还有 `(source_column_id, canonical_url)` 唯一约束，抵御并发竞态。

### 10.2 worker 在写到一半时宕机怎么办？

late ack 使消息可重投递，恢复任务扫描 stale running。文档 URL 唯一约束和任务 claim 避免恢复时重复写入。

### 10.3 为什么错误信息只记录异常类型？

抓取表需要可诊断但不应保存潜在敏感网络响应。详细堆栈在结构化日志，业务记录保存稳定错误类型。

### 10.4 真实站点不可访问时如何验收？

本地 fixture 完整覆盖发现、详情、附件和幂等路径；真实适配器和安全策略仍存在，外部不可达被记录为 blocker，不能伪造十篇成功记录。

### 10.5 现有 SSRF 防护还有什么边界？

应用层已检查每跳 DNS 和 IP，但 DNS 校验与 socket 连接之间仍可能发生 rebinding。生产应在爬虫容器网络或出口代理层禁止内网与元数据网段。

## 11. 代码阅读路线

1. `backend/app/models/source.py`
2. `backend/app/schemas/source.py` 与 `schemas/crawl.py`
3. `backend/app/services/sources.py`
4. `backend/app/crawler/urls.py`、`fetcher.py`
5. `backend/app/crawler/generic.py`、`adapters.py`、`registry.py`
6. `backend/app/services/crawl.py`
7. `backend/app/repositories/crawl.py`
8. `backend/app/tasks/crawl.py`、`recovery.py`、`celery_app.py`
9. fixture、安全和可靠性测试

## 12. 实践修改练习

给 `SourceColumn` 增加可配置的“仅允许与来源域名同域或显式白名单域名”策略。要求列表、详情、翻页、重定向和附件都执行同一策略；保留公网 IP 校验；新增跨域拒绝、白名单通过和相对 URL 通过测试，并说明这与 SSRF 防护解决的是不同问题。
