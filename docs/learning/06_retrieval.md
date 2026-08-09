# 06 混合检索

## 1. 模块目的

检索模块接受自然语言查询和元数据过滤条件，执行 BM25、向量、RRF 融合与可选重排，最终返回可解释的候选结果和完整阶段 trace。它是 Chat、评估和实验共同复用的核心能力。

## 2. 输入与输出

输入包括：

- 查询字符串；
- `bm25`、`vector`、`hybrid`、`hybrid_rerank` 模式；
- document/source/region/city/type/authority/date/version 过滤；
- runtime 中的 BM25Index、EmbeddingProvider、VectorStore、RerankProvider 和 RetrievalConfig。

输出包括 `RetrievalTrace`：标准化查询、推断/应用过滤、BM25 结果、向量结果、融合结果、重排结果、最终结果、各阶段耗时、配置和 warnings。

## 3. 数据流

```text
SearchRequest
  -> RetrievalQueryAnalyzer
  -> BM25 search（按模式）
  -> query embedding + vector search（按模式）
  -> Reciprocal Rank Fusion（混合模式）
  -> RerankProvider（hybrid_rerank 且未禁用）
  -> score_threshold + final_top_k
  -> SearchResponse / SearchDebugResponse
```

例如查询“2025 之后”会推断 `publish_date_gte=2026-01-01`；显式 filter 会覆盖同名推断值。`/api/search/debug` 仅管理员可访问并返回每个阶段的可读结果。

## 4. 核心类与文件

- `backend/app/retrieval/analysis.py`：查询规范化、术语和过滤推断。
- `backend/app/retrieval/models.py`：统一 `RetrievalHit`。
- `backend/app/retrieval/rrf.py`：`reciprocal_rank_fusion()`。
- `backend/app/retrieval/engine.py`：四种模式与完整 `RetrievalTrace`。
- `backend/app/bm25/index.py`：词法召回和过滤。
- `backend/app/vector_store/store.py`：向量召回及内存/Qdrant 过滤映射。
- `backend/app/rerank/providers.py`：disabled、deterministic、remote 重排。
- `backend/app/runtime.py`：运行时检索配置和对象组装。
- `backend/app/api/routes/search.py`、`backend/app/schemas/search.py`：普通与 debug API。
- `backend/tests/unit/test_retrieval_phase6.py`、`test_providers_and_retrieval.py` 和 `backend/tests/integration/test_search_api.py`。

## 5. 主要设计决策

1. BM25 和向量返回同一 `RetrievalHit`，融合层不依赖底层实现。
2. RRF 使用排名而非直接比较两种不可同比的原始分数，公式为每个列表累加 `1/(rrf_k + rank)`。
3. 相同列表中的重复 chunk 只计一次，最终以 score 降序、chunk ID 作为稳定 tie-break。
4. 过滤字段使用白名单，未知字段在 API 转为 `INVALID_SEARCH_REQUEST` 422。
5. 日期过滤在 BM25、内存向量和 Qdrant 映射中保持 `_gte/_lte` 语义。
6. Remote rerank 输出必须索引合法、无重复且分数在 0..1，否则拒绝整个响应。
7. 禁用重排时保留 hybrid 结果并附 `rerank_provider_disabled` warning，不假装执行了重排。
8. 每个阶段独立计时，debug trace 保存原始阶段结果，不只暴露最终 top-k。

## 6. 技术选型原因

- BM25：政策编号、机构名和固定术语适合精确词法匹配。
- 向量检索：可召回表达不同但语义相近的支持措施或申请条件。
- RRF：不需要校准 BM25 与 cosine 分数分布，且对单一路径异常更稳健。
- 可插拔重排：在 top candidate 上使用更强模型，控制延迟和成本。
- Metadata filter：先缩小地域、时间、文种等业务范围，提高相关性。
- Debug API：检索质量问题需要看到分析、召回、融合和重排各阶段，而不是只看答案。

## 6.1 Phase B: rerank execution contract and evaluation matrix

`hybrid_rerank` is an optional final ordering stage, not a reason to make an otherwise
working BM25 plus vector retrieval unavailable. Each retrieval trace records a structured
`rerank_metadata` object with `applied`, provider/model, failure policy, candidate and
reranked counts, latency, safe numeric usage, cost measurement, and a redacted error code.
The public search response also exposes `rerank_applied` so a client cannot mistake a
fallback fusion result for a remote rerank result.

`ODIRAG_RERANK_FAILURE_POLICY=open` is the default. When a remote provider times out,
rejects a request, or returns an invalid response, the engine retains the original fusion
order, marks rerank as not applied, and adds a stable warning. `closed` instead propagates
the provider error. Neither mode stores provider bodies, authorization values, or raw errors.

Evaluation must execute rather than label retrieval variants. The evaluation run accepts an
actual retrieval mode and top-k; the matrix endpoint resolves one verified question snapshot
once and runs BM25, Vector, Hybrid, and Hybrid+Rerank against that same snapshot. A metric
with zero assessed samples is not evidence of quality. In particular, use the explicit
citation, grounding, and unsupported-answer denominators in the report before comparing modes.

Remote rerank quality, latency, and billing are live claims only after a configured endpoint
and credential have been used successfully. Deterministic rerank, MockTransport response
tests, and in-memory evaluation runs remain fixture or contract evidence.

## 7. 常见故障模式

- 空查询：Analyzer 抛 `query must not be empty`，API 返回 422。
- 未知过滤字段：被 `_ALLOWED_FILTERS` 拒绝。
- BM25 无结果：快照为空、未重建、查询没有词项交集或 metadata 不匹配。
- 向量无结果：文档未索引、Qdrant collection/维度错误或过滤过严。
- 远程 Embedding/Rerank 缺凭据：结构化 Provider unavailable。
- 重排索引重复或越界：`ProviderResponseError('rerank')`。
- hybrid 分数很小：RRF 分数本来是倒数排名累加，不能按 cosine 阈值直觉解释。
- 中文检索粒度较粗：当前 tokenizer 是汉字级，不含 jieba 等词典分词。
- 运行时 BM25 旧：快照更新后已启动进程需要同步替换 runtime index 或重启加载。

## 8. 调试步骤

1. 调用 `/api/search/debug`，先看 analysis.normalized_query 和 applied_filters。
2. 分别以 `bm25`、`vector` 模式运行，定位是哪一路召回为空。
3. 检查 BM25 snapshot 的 document_count 和目标 chunk metadata。
4. 用同一 query 调用 EmbeddingProvider，核对维度与 Qdrant collection。
5. 比较 bm25_results/vector_results 与 fusion_results 的 rank 来源。
6. 查看 rerank_results 的 index 顺序和 0..1 分数。
7. 暂时把 score_threshold 设为 0 判断是否被最终阈值过滤。
8. 定向运行：`python -m pytest tests/unit/test_retrieval_phase6.py tests/unit/test_providers_and_retrieval.py tests/integration/test_search_api.py`。

## 9. 面试问题与参考答案

### 9.1 为什么不直接把 BM25 分数和 cosine 相加？

两者尺度和分布不同，直接相加需要校准。RRF 只使用排名，可稳定融合异构召回器。

### 9.2 RRF 的 `rrf_k` 有什么作用？

它平滑头部排名差异。k 越小，第一名优势越大；k 越大，各名次贡献更接近。ODIRAG 默认 60，并允许实验调整。

### 9.3 metadata filter 应在融合前还是融合后做？

当前在 BM25 和向量召回阶段都应用，避免无关候选占用 top-k。只在融合后过滤可能让目标范围内没有足够候选。

### 9.4 如何验证远程重排结果可信？

校验返回 index 在候选范围内、不可重复、score 在 0..1，然后用原候选内容重建 `RetrievalHit`，不接受 Provider 重新提供正文或 URL。

### 9.5 debug trace 对调优有什么价值？

它能区分“查询分析错、BM25 漏召回、向量漏召回、RRF 排序或 rerank 降级”，避免只根据最终答案盲调参数。

## 10. 答辩问题与参考答案

### 10.1 如何证明四种模式都是真实执行？

单元测试分别构建 BM25 和内存向量库，检查各模式的阶段结果；搜索集成测试 reindex 后调用 debug API，断言 BM25、vector、fusion、rerank 均有真实 hit。

### 10.2 为什么 deterministic reranker 不是生产假数据？

它只用于 test/明确 demo 配置，并根据 query/document token overlap 实际排序；生产可配置 remote 或 none，系统不会把 deterministic 结果冒充远程模型。

### 10.3 “2025 之后”为什么从 2026-01-01 开始？

Analyzer 把“之后”解释为严格晚于该年份，因此生成下一年元旦；“since/以来”目前也走相同规则，这是需在产品语义中明确的实现细节。

### 10.4 score threshold 应如何设定？

必须基于固定评估集实验，不应凭经验硬编码。尤其 RRF 与 rerank 分数语义不同，阈值要和最终候选来源一起版本化。

### 10.5 检索服务失效时 Chat 会编答案吗？

不会。检索异常向上传递；检索为空或证据不足时 GroundingService 触发拒答，引用也只能来自真实 hit。

## 11. 代码阅读路线

1. `backend/app/retrieval/models.py`
2. `backend/app/retrieval/analysis.py`
3. `backend/app/bm25/index.py`
4. `backend/app/vector_store/store.py`
5. `backend/app/retrieval/rrf.py`
6. `backend/app/rerank/providers.py`
7. `backend/app/retrieval/engine.py`
8. `backend/app/api/routes/search.py`
9. 检索单元与 API 集成测试

## 12. 实践修改练习

新增 `issuing_authority` 的模糊匹配模式，同时保持默认精确匹配。要求请求 schema 显式选择 match mode，BM25、InMemoryVectorStore、Qdrant filter 和 SQL 结构查询语义一致；未知模式返回 422，并用固定数据验证不会扩大其他字段的匹配范围。
