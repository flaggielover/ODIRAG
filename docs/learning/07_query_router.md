# 07 查询路由

## 1. 模块目的

查询路由负责判断用户问题应走结构化统计、语义检索，还是先用结构化条件圈定范围再做语义总结。当前实现是确定性基线，不接收或执行 LLM 生成的任意 SQL。

## 2. 输入与输出

输入是用户查询字符串和可选显式 metadata filters。

输出是 `QueryAnalysis`：

- `query_type`：`sql`、`rag` 或 `sql+rag`；
- `filters`：经 `RetrievalQueryAnalyzer` 推断并与显式值合并的白名单过滤；
- `reason`：本次分类原因。

SQL 路径的业务输出是符合过滤条件且 `final_status=approved` 的文档数量；RAG/组合路径继续产生检索结果、回答和引用。

## 3. 数据流

```text
ChatRequest(query, filters)
  -> QueryRouter.analyze()
  -> aggregate terms? semantic terms? metadata filters?
  -> SQL：ChatRepository.count_approved_documents()
  -> RAG：RetrievalEngine.search()
  -> SQL+RAG：先 count，再用同一 filters 检索和总结
  -> ChatAnswer + QueryTrace
```

`ChatRepository._apply_document_filters()` 只把白名单字段映射为 SQLAlchemy 表达式。查询文本不会被拼接到 SQL，也不存在 `text(llm_output)` 之类执行路径。

## 4. 核心类与文件

- `backend/app/router/query_router.py`：`QueryType`、`QueryAnalysis`、`QueryRouter`。
- `backend/app/retrieval/analysis.py`：日期、地域和显式过滤解析。
- `backend/app/services/chat.py`：按路由分支执行 SQL、RAG 或组合流程。
- `backend/app/repositories/chat.py`：批准文档计数和安全过滤模板。
- `backend/app/schemas/chat.py`：Chat 请求/响应契约。
- `backend/app/api/routes/chat.py`：Chat API、trace 和 lineage 路由。
- `backend/tests/unit/test_chat_grounding.py`：路由、证据和拒答单元行为。
- `backend/tests/integration/test_search_api.py`：真实索引后的 SQL、RAG 和组合 API 路径。

## 5. 主要设计决策

1. 分类基线使用 aggregate/semantic 关键词和过滤条件，行为可复现、可测试。
2. 只有聚合意图且没有语义意图时走 SQL；语义意图叠加结构过滤或聚合词时走 SQL+RAG；其余走 RAG。
3. SQL 路径目前只提供已批准文档 count，范围小而安全，不假装支持任意分析语句。
4. 结构化与检索路径复用同一 `RetrievalQueryAnalyzer` 和 filters，避免“统计范围”和“总结范围”不一致。
5. 显式 filter 覆盖推断 filter，调用者可以纠正自然语言推断。
6. 所有字段经白名单转为 SQLAlchemy 条件，日期使用 `date.fromisoformat()`，数字字段显式转换。
7. 路由结果和过滤条件写入 `QueryTrace`，便于发现误分类。

## 6. 技术选型原因

- 确定性路由：当前业务类型有限，规则方案比调用模型更便宜、更容易回归。
- SQLAlchemy query builder：使用列对象和绑定参数，避免字符串拼接与 SQL 注入。
- 共享 Analyzer：自然语言日期/地域解释在搜索和统计中保持一致。
- 组合路由：政策问题常同时包含“某时间/地区范围”和“总结措施”，单一路径难以完整回答。
- 白名单能力演进：每新增统计意图都需要明确模板和测试，而不是开放数据库给模型。

## 7. 常见故障模式

- “有多少”被识别为 SQL，但用户还要求原因说明：若没有命中 semantic terms，可能误分类。
- 同义词未覆盖：规则词表之外的表达会默认 RAG。
- 日期语义争议：当前“2025 之后/以来/since”实现为从 2026-01-01 开始，需要产品定义一致。
- 显式过滤格式错误：未知字段或非法日期会返回 422，而不是生成 SQL。
- SQL count 为 0、RAG 有结果：检查两端 metadata 是否一致，尤其 region 和 document_type。
- 组合回答中的 count 与 citations 范围不同：应检查是否所有 Vector/BM25 Provider 都应用了 route.filters。
- 当前 SQL 路径没有文档列表或分组统计，只能回答总数。

## 8. 调试步骤

1. 直接调用 `QueryRouter.analyze(query, filters)`，查看 query_type、reason 和 filters。
2. 调用 `/api/search/debug` 对照同一 query 的 inferred/applied filters。
3. 对 SQL 路径在数据库中手工使用相同白名单条件计数。
4. 对组合路径比较 `structured_count` 与 citations 的 region/date/type metadata。
5. 检查 aggregate/semantic 正则是否覆盖目标中英文表达。
6. 给误分类语句先补单元测试，再调整规则，防止旧类型回归。
7. 确认 Repository 没有执行原始 query 文本。
8. 定向运行：`python -m pytest tests/unit/test_chat_grounding.py tests/integration/test_search_api.py`。

## 9. 面试问题与参考答案

### 9.1 为什么不直接让 LLM 生成 SQL？

数据库包含生产业务数据，任意 SQL 难以安全限制表、列、连接、成本和写操作。ODIRAG 使用白名单模板，只暴露经过验证的统计能力。

### 9.2 SQL+RAG 与先 RAG 再数结果有什么区别？

检索 top-k 不是完整数据集，不能用于精确计数。组合路由从 PostgreSQL 得到完整结构计数，再在同一过滤范围内检索证据用于总结。

### 9.3 路由规则如何回归？

维护固定 query fixture，断言 query_type、filters 和 reason；任何关键词或 Analyzer 改动都运行这些样本以及最终 Chat 集成测试。

### 9.4 显式 filter 为什么要覆盖推断值？

自然语言推断可能歧义，API 调用方的结构化选择更明确。覆盖规则也让前端筛选器能精确控制范围。

### 9.5 当前路由的主要扩展点是什么？

增加新的安全 query intent 和对应 Repository 模板，例如按地区分组、按年份趋势、列表查询；模型只能选择模板和参数，不能提供 SQL 文本。

## 10. 答辩问题与参考答案

### 10.1 如何证明系统没有执行 LLM SQL？

代码路径中 `QueryRouter` 是确定性规则，`ChatRepository` 只构造 SQLAlchemy count 和白名单条件；`LLMOrchestrator.analyze_query()` 协议存在，但当前 Chat 主链没有把其输出当 SQL 执行。

### 10.2 组合查询的 count 是否来自检索结果数量？

不是。`count_approved_documents()` 对 PostgreSQL 中全部批准文档计数，检索 top-k 仅用于证据和语义回答。

### 10.3 路由错误会造成什么后果？

可能只返回计数、缺少证据总结，或走 RAG 得不到精确统计。因此 trace 保存 query_type/reason/filters，并通过反馈转评估形成回归样本。

### 10.4 为什么 SQL 答案没有 citation？

当前 SQL 路径只返回聚合 count，没有为聚合结果构建来源列表，这是诚实限制。若业务要求引用，应新增可审计的集合摘要而不是伪造单文档引用。

### 10.5 未来接入 LLM 路由时如何保持安全？

让模型只能输出严格 `QueryPlan` 中的 intent 和白名单 filters，再由服务映射到固定模板；拒绝未知 intent、字段和类型，仍不接受 SQL 字符串。

## 11. 代码阅读路线

1. `backend/app/router/query_router.py`
2. `backend/app/retrieval/analysis.py`
3. `backend/app/repositories/chat.py`
4. `backend/app/services/chat.py` 的 route 分支
5. `backend/app/schemas/chat.py`
6. `backend/app/api/routes/chat.py`
7. 路由单元测试与 Search/Chat 集成测试

## 12. 实践修改练习

新增“按地区分组统计已批准政策数量”意图。模型仍不得生成 SQL；实现固定 SQLAlchemy `GROUP BY region` 模板、严格响应 schema、空 region 处理、最多返回项限制，并加入中英文路由样本和 SQL 注入字符串测试。
