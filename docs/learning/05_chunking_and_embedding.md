# 05 分块、Embedding 与索引

## 1. 模块目的

索引模块把已批准文档及已解析附件切成可引用 chunk，批量生成向量，写入 Qdrant，同时在 PostgreSQL 保存 chunk 与血缘，并可从数据库重建 BM25 快照。它负责派生索引的一致性、幂等和失败补偿。

## 2. 输入与输出

输入包括 `final_status=approved` 的 `Document`、已完成解析的附件、`config/chunking.yaml`、Embedding Provider、Embedding Cache 和 VectorStore。

输出包括：

- `chunks` 表中的稳定 chunk ID、section path、页码、内容哈希、模型和版本；
- Qdrant/InMemoryVectorStore 中的向量点和 metadata payload；
- 从 source/crawl/document version/attachment/chunk/vector point 组成的 `DataLineage`；
- 文档与 chunk 的 indexed/failed 状态；
- cache hit、实际 embedding 数、估算成本和 vector point IDs；
- `data/indexes/bm25.json` 等可重载 BM25 快照。

## 3. 数据流

```text
Approved Document + parsed attachments
  -> HeadingAwareChunker
  -> EmbeddingBatcher（cache -> batch -> retry）
  -> VectorStore.ensure_collection()
  -> VectorStore.upsert()
  -> PostgreSQL replace_chunks + DataLineage
  -> 删除 stale vector points
  -> chunk/document status=indexed
  -> BM25RebuildService 从 indexed chunks 重建快照
```

文档正文先分块；附件按 `\f` 页分割，chunk 保存 attachment_id 和 page_number。向量点先写入，数据库切换失败时会删除仅新建的点作为补偿。

## 4. 核心类与文件

- `backend/app/chunking/heading.py`：`ChunkingConfig`、`ChunkDraft`、`HeadingAwareChunker`。
- `backend/app/chunking/config.py` 与 `config/chunking.yaml`：参数加载。
- `backend/app/embedding/providers.py`：远程和 deterministic Embedding Provider。
- `backend/app/embedding/batcher.py`：版本化 cache、批处理、节流、重试和成本。
- `backend/app/cache/embedding.py`：内存与 Redis cache。
- `backend/app/vector_store/store.py`：`VectorStore`、内存实现和 Qdrant 实现。
- `backend/app/bm25/index.py`：索引构建、过滤、搜索和快照。
- `backend/app/services/indexing.py`：完整索引事务与补偿。
- `backend/app/services/bm25.py`：从数据库构建 BM25。
- `backend/app/repositories/indexing.py`：chunk、版本和血缘数据库操作。
- `scripts/rebuild_bm25.py`：命令行重建入口。
- `backend/tests/integration/test_indexing_pipeline.py` 与 `backend/tests/unit/test_indexing_components.py`。

## 5. 主要设计决策

1. 分块优先识别 Markdown/中文编号标题，再按段落组合，最后按语义分隔符和严格字符上限递归回退。
2. 配置必须满足 `min <= target <= max` 且 overlap 小于 target。
3. chunk ID 用 UUID5 生成，输入包含文档公共 ID、版本、附件、页码、位置、模型、embedding 版本和内容哈希，因此相同输入可幂等重建。
4. Cache key 同时包含 Provider、模型、版本和文本摘要，避免模型升级误用旧向量。
5. Qdrant collection 已存在时验证向量维度，并创建 document_id、source_id、region、publish_date 等 payload index。
6. 只有 approved 文档可索引；内容变化后先 stale，再显式 reindex。
7. PostgreSQL 是 chunk 与血缘事实来源，Qdrant 和 BM25 是可重建的派生索引。
8. VectorStore 与 PostgreSQL 无法共享事务，服务通过状态、确定性 ID 和补偿删除降低不一致风险。

## 6. 技术选型原因

- Heading-aware chunking：政策标题层级和条款边界比固定字符窗口更有语义。
- Redis cache：远程 Embedding 成本较高，内容/模型版本相同即可复用。
- Deterministic provider：测试和明确 demo 模式可重复，不伪装成生产语义模型。
- Qdrant：支持向量相似度、payload filter 和可管理 collection。
- rank-bm25：保留精确术语检索，与向量语义召回互补。
- UUID5：稳定、可重算，便于发现 stale 点和重复执行。
- 关系库血缘：向量库不承担业务版本与审计职责。

## 7. 常见故障模式

- `Only approved documents can be indexed`：最终审查尚未批准。
- 没有 chunk：正文和可索引附件均为空或清洗后为空。
- 向量维度不一致：Provider 返回长度与 `embedding_dimensions` 或现有 Qdrant collection 不符。
- Redis 不可用：使用 Redis cache 的生产配置会报告 Provider/缓存失败；明确 demo 可选 memory。
- Qdrant upsert 成功但数据库失败：服务尝试删除新点并把文档标 failed；补偿失败会写错误日志。
- stale 点删除失败：本次索引失败，重试会使用确定性 ID 再收敛。
- BM25 搜索没有新文档：BM25 是快照/进程内对象，需要 reindex 路径更新或执行 rebuild 命令并重启加载。
- 中文召回不理想：当前 BM25 tokenizer 以单个汉字和英文单词切分，不是中文分词器。

## 8. 调试步骤

1. 查看文档 `final_status` 和 `index_status`。
2. 单独运行 `HeadingAwareChunker.chunk()`，检查 chunk 长度、section_path 和 overlap。
3. 查看 `EmbeddingBatchResult.cache_hits` 与 `embedded_count`，确认缓存版本是否一致。
4. 检查 Provider 返回的每个 vector 长度。
5. 查询 Qdrant collection 维度和 payload schema。
6. 比较数据库 chunk IDs 与 Qdrant point IDs；根据 `DataLineage.vector_point_id` 定位缺口。
7. 运行 `python ../scripts/rebuild_bm25.py` 并检查输出 snapshot_path 和 document_count。
8. 定向运行：`python -m pytest tests/unit/test_indexing_components.py tests/integration/test_indexing_pipeline.py`。

## 9. 面试问题与参考答案

### 9.1 为什么 chunk ID 要包含 embedding 版本？

相同文本换模型或版本后向量语义可能变化。把模型和版本纳入 ID，可以明确区分旧点并在重建时删除 stale 点。

### 9.2 为什么先写向量再替换数据库 chunk？

只有向量就绪后才切换关系库到新 chunk 集，减少数据库指向尚不存在向量的窗口；若数据库切换失败，则删除本次新增点补偿。

### 9.3 overlap 的作用和风险是什么？

它保留跨边界上下文，但过大将增加重复、Embedding 成本和检索相似结果。配置验证保证 overlap 小于 target。

### 9.4 为什么 BM25 可以从数据库重建？

PostgreSQL 保存所有 indexed chunk 及 metadata；BM25 只是派生结构，`BM25RebuildService` 可生成完整快照，因此不应成为业务事实来源。

### 9.5 如何保证重复 reindex 幂等？

稳定 UUID5、Qdrant upsert、chunk 集比较和 embedding cache 共同作用。集成测试两次索引断言 point IDs 相同、第二次全部 cache hit 且不重复血缘。

## 10. 答辩问题与参考答案

### 10.1 为什么不用 Qdrant 保存全文业务数据？

版本、审查、外键和事务属于 PostgreSQL；Qdrant 保存检索所需向量与 payload。这样索引可删除重建而不丢业务事实。

### 10.2 附件页码如何进入引用？

解析后的多页文本用 `\f` 分隔，索引时逐页分块，Chunk 保存 attachment_id/page_number，并写入向量 payload，GroundingService 再把 page 放进 Citation。

### 10.3 远程 Embedding 不可用会不会写零向量？

不会。Provider 抛出明确异常，文档标 failed；只有 deterministic demo Provider 才生成可重复测试向量，且配置名称清楚区分。

### 10.4 跨数据库一致性如何保证？

无法获得真正分布式事务，因此使用状态机、稳定 ID、幂等 upsert、补偿删除和可重建索引。监控暴露 failed 状态供重试。

### 10.5 性能优化在哪里？

批量 Embedding、Redis cache、请求间隔、Qdrant payload index、BM25 快照和 bounded top-k 减少远程调用与扫描范围。

## 11. 代码阅读路线

1. `config/chunking.yaml` 与 `backend/app/chunking/heading.py`
2. `backend/app/embedding/providers.py`
3. `backend/app/cache/embedding.py`
4. `backend/app/embedding/batcher.py`
5. `backend/app/vector_store/store.py`
6. `backend/app/services/indexing.py`
7. `backend/app/repositories/indexing.py`
8. `backend/app/bm25/index.py` 与 `services/bm25.py`
9. 索引单元和集成测试

## 12. 实践修改练习

增加“只重建某个 embedding_version 的索引”命令。要求不修改已批准正文，生成新版本 chunk/point，成功后删除旧版本点，失败时保留旧可用索引；输出新增、复用、删除和失败计数，并为 Qdrant 合同与数据库状态写测试。
