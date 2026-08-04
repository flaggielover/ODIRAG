# 04 审查与结构化知识

## 1. 模块目的

审查模块决定抓取文档是否值得进入生产知识库，并把政策正文中的关键字段转为带证据的结构化知识。流程由规则过滤、LLM 严格结构化审查、人工复核和提示词版本记录组成。

## 2. 输入与输出

输入包括文档标题、正文、来源是否官方、`config/filters.yaml`、版本化审查提示词，以及 Direct LLM 或 Coze 返回的 JSON。

输出包括：

- `Document.quality_score`、rule/llm/manual review 状态和 `final_status`；
- `DocumentReview` 中规则与模型的决策、原因、摘要、原始响应、模型和 prompt 版本；
- `StructuredKnowledge` 中字段值、证据引文、置信度、模型和 prompt 版本；
- `PromptVersion` 中不可变的提示词内容哈希；
- 人工 approve/reject 后可供索引的最终状态。

## 3. 数据流

```text
Document
  -> RuleFilter.evaluate()
  -> hard reject：保存规则审查，final_status=rejected
  -> accept/review：确保 PromptVersion
  -> LLMOrchestrator.review_document()
  -> Pydantic ReviewResult 严格校验
  -> ExtractedField 校验 + evidence_quote 必须出现在正文
  -> DocumentReview + StructuredKnowledge
  -> approved / pending_manual_review / rejected
  -> 人工 approve/reject
```

Provider 连续失败时，文档被标记 `llm_review_status=unavailable`、`final_status=pending_llm`，然后返回结构化 Provider 错误，而不是自动批准。

## 4. 核心类与文件

- `backend/app/filters/rules.py`：`RuleFilterConfig`、`RuleFilter` 和 accept/review/reject。
- `backend/app/services/filter_config.py`：读取严格 YAML 配置。
- `config/filters.yaml`：长度阈值、拒绝模式、关键词和扣分值。
- `backend/app/llm/protocols.py`：`LLMOrchestrator`、`ReviewResult` 等契约。
- `backend/app/llm/adapters.py`：`DirectLLMAdapter` 与 `CozeAdapter`。
- `backend/app/services/prompts.py`：提示词版本和内容不可变检查。
- `backend/app/services/review.py`：完整审查编排、重试和证据绑定。
- `backend/app/repositories/reviews.py`：文档、审查、知识和 prompt 持久化。
- `backend/app/models/document.py`：`DocumentReview`、`StructuredKnowledge`。
- `backend/app/api/routes/reviews.py`：运行审查、待审列表和人工决策。
- `backend/tests/integration/test_review_pipeline.py` 与 `backend/tests/unit/test_filters_prompts_llm.py`。

## 5. 主要设计决策

1. 低成本规则过滤先执行，硬拒绝文档不会调用 LLM。
2. 软分数从 1.0 扣除短文本、缺关键词和非官方来源惩罚，并保存 reason code。
3. Provider 接口由 `LLMOrchestrator` 隔离，核心审查逻辑不依赖 Coze 协议。
4. Direct adapter 请求 JSON object，并用 Pydantic `extra='forbid'` 拒绝结构漂移。
5. 只允许 `ALLOWED_STRUCTURED_FIELDS` 中的 12 类政策字段，未知字段视为 Provider 响应错误。
6. 每个 extracted field 的 `evidence_quote` 必须是原文子串，防止模型编造依据。
7. 同一 prompt name/version 内容不可改变；变更必须创建新版本。
8. 规则、LLM、人工审查分别保存 `DocumentReview`，保留决策轨迹而非覆盖历史。
9. 当前结构化字段先绑定原文 quote；`evidence_chunk_id` 不会在审查阶段自动补齐，分块后的精确关联仍需后续增强。

## 6. 技术选型原因

- 规则 + LLM 两阶段：确定性规则可解释、便宜，LLM 处理复杂语义。
- Pydantic 严格模型：远程模型输出是非可信输入，必须在入库前校验类型和范围。
- tenacity：短暂 Provider 故障最多重试三次，并保留最终失败状态。
- PromptVersion 数据表：评估结果和查询 trace 可以关联真实提示词版本。
- 人工复核：边界样本和高风险政策不应只靠自动分数决定。
- 原文子串证据：实现简单、可验证，是比“模型说有证据”更强的约束。

## 7. 常见故障模式

- 规则直接 reject：内容低于 hard_minimum_chars，或命中标题/正文拒绝正则。
- 长文进入 manual review：分数低于 accept_score，或 LLM 明确返回 manual_review。
- `PROVIDER_UNAVAILABLE`：API key/bot ID 缺失、网络或远程 HTTP 失败。
- `PROVIDER_INVALID_RESPONSE`：JSON 字段多余、类型错误、分数越界或响应结构变化。
- 证据绑定失败：`evidence_quote` 不是正文的精确子串，可能由空白差异或模型改写造成。
- prompt 冲突：同 name/version 已存在但内容哈希不同。
- 模型审查成功但不能索引：仍需最终 `final_status=approved`，人工待审状态不满足索引条件。
- 结构知识没有 chunk ID：目前只有 quote，可在索引后做 quote-to-chunk 关联。

## 8. 调试步骤

1. 直接运行 `RuleFilter.evaluate()`，查看 decision、score 和 reasons。
2. 核对 `config/filters.yaml` 是否被正确路径解析，阈值是否满足 `reject <= accept` 的业务预期。
3. 查 `document_reviews`，确认 rule 记录是否先于 LLM 记录产生。
4. Provider 故障先看结构化日志中的 provider 和 reason；客户端只看到安全错误摘要。
5. 保存远程原始 JSON，在测试中用 `ReviewResult.model_validate_json()` 重现结构错误。
6. 对证据错误比较 `repr(evidence_quote)` 与正文，检查全角空格、换行和模型改写。
7. 核对 `prompt_versions` 的 name、version、content_hash。
8. 定向运行：`python -m pytest tests/unit/test_filters_prompts_llm.py tests/integration/test_review_pipeline.py`。

## 9. 面试问题与参考答案

### 9.1 为什么不用 LLM 一步决定所有文档？

规则能便宜、稳定地拒绝明显无效页面，并给出 reason code。LLM 只处理剩余语义问题，降低成本和不可预测性。

### 9.2 如何防止结构化抽取幻觉？

字段白名单、严格 Pydantic schema、置信度范围和 `evidence_quote in document.content` 四层校验，任何一层失败都不入库。

### 9.3 为什么要保存 raw_response？

便于审计 Provider 输出、定位 schema 漂移和复现实验。它与规范化字段并存，不能替代结构校验。

### 9.4 prompt 为什么要不可变？

若同一版本内容可被覆盖，历史评估和生产决策无法复现。内容变化必须创建新版本并在 trace 中引用。

### 9.5 规则分数是机器学习概率吗？

不是。它是从 1.0 按配置扣分的可解释启发式质量分，决策阈值来自 YAML，不能当作统计概率解释。

## 10. 答辩问题与参考答案

### 10.1 Coze 不可用时系统会自动批准吗？

不会。状态变为 `pending_llm`，接口返回 Provider 不可用；这是诚实降级，防止未经审查的数据进入索引。

### 10.2 如何展示一次审查的证据链？

查询 `DocumentReview` 的 model、prompt version、raw response 和 extracted fields，再查看 `StructuredKnowledge.field_value_json.evidence_quote` 与原文对应位置。

### 10.3 人工审查会覆盖模型历史吗？

不会。人工动作新增 `review_type='manual'` 的记录，同时更新当前文档状态，规则和模型记录仍保留。

### 10.4 为什么结构化知识不能直接相信高置信度？

置信度来自模型自报，不是充分证据。ODIRAG 还要求字段白名单和原文引文；未来可由人工把 `verified` 设为真并关联 chunk。

### 10.5 如何证明重试不是假实现？

集成测试的 orchestrator 前两次抛 `ProviderUnavailableError`、第三次成功，并断言调用次数为 3、原始响应和知识记录真实写入数据库。

## 11. 代码阅读路线

1. `config/filters.yaml`
2. `backend/app/filters/rules.py`
3. `backend/app/llm/protocols.py`
4. `backend/app/llm/adapters.py`
5. `backend/app/services/prompts.py`
6. `backend/app/services/review.py`
7. `backend/app/repositories/reviews.py`
8. `backend/app/api/routes/reviews.py`
9. 审查单元与集成测试

## 12. 实践修改练习

新增结构字段 `validity_period`，包含开始日期、结束日期和证据引文。要求更新字段白名单与 Pydantic schema，拒绝结束日期早于开始日期，增加 Direct/Coze 合同测试和 ReviewService 集成测试，并设计索引后将引文绑定到 `evidence_chunk_id` 的步骤。
