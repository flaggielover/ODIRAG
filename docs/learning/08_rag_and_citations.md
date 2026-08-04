# 08 RAG、证据、引用与拒答

## 1. 模块目的

RAG 模块把路由、检索结果和证据规则组合成可追溯回答。它的核心目标不是“总能回答”，而是只在已有官方证据覆盖问题时作答，引用必须绑定真实 chunk，冲突或证据不足时拒答。

## 2. 输入与输出

输入包括用户 query、route filters、`RetrievalTrace.final_results`、grounding 阈值、官方来源要求、冲突策略，以及可选 LLM Orchestrator 和版本化 grounded prompt。

输出 `ChatAnswer`：query type、answer、refusal、拒答原因、冲突、过时记录、citations、filters、structured_count 和 retrieval trace。持久化输出是完整 `QueryTrace`，引用还可通过 lineage API 追溯到文档版本、抓取任务和来源。

## 3. 数据流

```text
ChatRequest
  -> QueryRouter
  -> SQL count（需要时）
  -> RetrievalEngine（RAG/组合）
  -> GroundingService.assess()
     - 数量/分数
     - 官方来源
     - 问题覆盖
     - 冲突
     - 新旧政策
  -> 不充分：拒答
  -> 充分：extractive answer 或 LLM answer
  -> 校验 cited_chunk_ids 和 URL
  -> QueryTrace
  -> Citation lineage
```

Extractive 模式从最多三个已验证 Citation 组成回答。LLM 模式只接收 eligible hits，返回的 chunk ID 必须属于候选，回答中出现的 URL 必须属于最终 citations。

## 4. 核心类与文件

- `backend/app/rag/grounding.py`：`Citation`、`EvidenceDecision`、`GroundingService`。
- `backend/app/services/chat.py`：路由、检索、回答、拒答、引用验证和 trace 持久化。
- `backend/app/router/query_router.py`：SQL/RAG/组合路由。
- `backend/app/repositories/chat.py`：结构计数和 QueryTrace。
- `backend/app/models/observability.py`：`QueryTrace`、`DataLineage`。
- `backend/app/services/observability.py`：`LineageService.answer_lineage()`。
- `backend/app/repositories/observability.py`：从 chunk 查询完整 lineage context。
- `backend/app/llm/protocols.py`、`adapters.py`：`AnswerResult` 和远程模型调用。
- `config/prompts/grounded_answer_v1.txt`：回答提示词。
- `backend/app/api/routes/chat.py`：chat、trace 列表/详情和 lineage API。
- `backend/tests/unit/test_chat_grounding.py` 与 `backend/tests/integration/test_search_api.py`。

## 5. 主要设计决策

1. 先执行确定性 `GroundingService.assess()`，再决定是否调用回答模型。
2. eligible hit 必须有正文且达到 minimum score；数量不足触发拒答。
3. 默认至少存在一个 official source，否则 `official_source_required`。
4. 问题覆盖用英文 token 和中文双字片段与证据正文重叠判断。
5. 冲突依赖同一 policy key 下不同 `policy_status`；配置为冲突即拒答。
6. 同 document_number/policy key/title 的较早发布日期被标记 outdated，并从 citations 排除。
7. Citation 的 document/chunk/title/URL/page/quote 全部由 RetrievalHit 构造，LLM 不能创建 URL。
8. LLM 必须返回至少一个合法 cited chunk ID；未知 ID 或未知 URL 使整个响应失败。
9. QueryTrace 保存 BM25、vector、fusion、rerank、最终上下文、prompt 快照、模型、回答、引用和性能数据。

## 6. 技术选型原因

- 确定性证据门：比只靠 prompt 说“不要幻觉”更可测试。
- Extractive fallback：没有模型凭据时仍可从真实证据作答，但不伪装成生成模型能力。
- chunk ID 引用：比让模型输出自由文本来源更容易验证和追踪。
- URL allowlist：阻断模型在答案中植入未检索链接。
- PostgreSQL QueryTrace：完整过程可审计、可反馈、可评估。
- DataLineage：把回答证据追溯到 source 和 crawl task，适合官方文档场景。

## 7. 常见故障模式

- `insufficient_retrieved_evidence`：最终 hit 数少于配置。
- `official_source_required`：只有非官方来源。
- `question_not_covered`：检索结果存在，但与 query 的词/双字片段无重叠。
- `conflicting_evidence`：同一政策 metadata 状态不一致。
- 引用为空或未知 chunk：远程回答被 `ProviderResponseError('grounded_answer')` 拒绝。
- 回答出现新 URL：即使文本看似合理，也会被拒绝。
- 过时文档仍被召回：会进入 `outdated` 消息，但不会成为 citation。
- lineage 不完整：旧数据缺少 document version、crawl task 或 source，API 明确返回 `complete=false` 和 missing_steps。
- 当前冲突/覆盖规则依赖 metadata 和字面重叠，不能替代复杂语义事实核验。

## 8. 调试步骤

1. 先调用 `/api/search/debug`，确认最终 context 是否包含预期 chunk 和 metadata。
2. 单独运行 `GroundingService.assess()`，检查 reasons、conflicts、outdated 和 citations。
3. 核对 official_status、policy_status、document_number、publish_date 和 page_number payload。
4. LLM 回答失败时检查 cited_chunk_ids 是否都在 eligible citations。
5. 提取回答中的 URL，与 citations URL 集合比较。
6. 查询 `/api/chat/traces/{trace_id}`，逐阶段核对上下文和 prompt snapshot。
7. 查询 `/api/chat/traces/{trace_id}/lineage`，查看 missing_steps。
8. 定向运行：`python -m pytest tests/unit/test_chat_grounding.py tests/integration/test_search_api.py tests/integration/test_read_support_api.py`。

## 9. 面试问题与参考答案

### 9.1 为什么 citation 由服务构造而不是模型直接生成？

服务拥有真实 RetrievalHit 和存储 ID，可确定 title、URL、page 和 quote。模型只选择允许的 chunk ID，不能发明文档或链接。

### 9.2 拒答规则为什么放在模型调用前？

证据不足时不应把无关上下文交给模型碰运气。确定性前置门减少幻觉、延迟和成本，并可独立测试。

### 9.3 如何检测过时政策？

按 document_number、policy_key 或 title 分组，解析 publish_date，保留最新日期，将更早 chunk 标为 outdated 并从 citations 排除。

### 9.4 URL 校验能防止什么？

即便模型返回合法 chunk ID，也可能在正文中加入其他 URL。服务解析回答 URL，要求它们属于最终引用集合。

### 9.5 trace 为什么要保存 prompt snapshot 而不只保存版本？

版本可定位配置，snapshot 可直接复现实次回答，即使文件后来迁移或配置改变仍保留实际输入。

## 10. 答辩问题与参考答案

### 10.1 如何证明引用是真实的？

Citation 取自检索 hit，包含 chunk/document ID；lineage API 再查询 PostgreSQL 的 Chunk、DocumentVersion、CrawlTask、Source 和 DataLineage，集成测试断言链完整。

### 10.2 没有 LLM key 时 Chat 是假结果吗？

不是。`answer_provider=extractive` 明确选择基于证据 quote 的确定性回答，模型名记录为 `extractive-grounded-v1`；不会声称使用远程模型。

### 10.3 为什么 SQL count 回答不带引用？

当前聚合来自数据库模板而非某个 chunk。系统诚实返回无 citation；若要审计聚合，应新增结果集合摘要和查询 trace，而不是随意绑定一篇文档。

### 10.4 冲突检测是否已经理解政策语义？

没有。当前依据结构 metadata 的 policy key/status，是可解释基线。复杂条款冲突需要结构化字段比较或专门模型，并必须增加评估集。

### 10.5 用户指出错误引用后如何闭环？

Feedback 保存 trace 和预期文档；可转换类型生成 verified `EvaluationQuestion`，后续评估/实验会把该真实失败固定为回归样本。

## 11. 代码阅读路线

1. `backend/app/rag/grounding.py`
2. `backend/app/router/query_router.py`
3. `backend/app/services/chat.py`
4. `backend/app/repositories/chat.py`
5. `backend/app/models/observability.py`
6. `backend/app/repositories/observability.py`
7. `backend/app/services/observability.py` 的 LineageService
8. Chat API、单元测试和端到端集成测试

## 12. 实践修改练习

为回答增加 claim-level citation map：每个回答要点必须绑定至少一个 chunk ID。要求 LLM schema 严格校验、所有 claim 引用均在 eligible set、无引用 claim 导致拒答或 Provider 错误，并把映射写入 QueryTrace 和评估报告。
