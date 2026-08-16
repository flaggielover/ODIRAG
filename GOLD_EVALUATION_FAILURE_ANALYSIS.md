# Gold Evaluation Quality Closure

更新时间：2026-08-15

## Metric Contract

- Exact Citation Precision/Recall 比较最终 citation 与 Gold `expected_chunk_ids` 的集合交集。Precision 为 `|cited ∩ expected| / |cited|`，Recall 为 `|cited ∩ expected| / |expected|`。
- 聚合 Exact Citation 指标排除 `should_refuse=true && refused=true` 的正确拒答，但保留 supported false-refusal；因此 false-refusal 的空 citation 会将该指标记为 0。
- Emitted Citation 指标只统计实际回答样本，用于把 citation mapping 质量与 false-refusal 分开观察。
- Document Citation 指标比较 `cited_document_ids` 与 Gold `expected_document_ids`，不替代 exact-chunk 指标。
- Refusal Accuracy 是所有无执行错误问题上 `refused == should_refuse` 的比例。Refusal Precision、Refusal Recall、Supported Answer Recall 分别单独报告。
- Evidence Sufficiency Accuracy 比较持久化的前置 evidence decision 与 `not should_refuse`；post-answer validator 结果另行持久化和分析。
- 执行错误从质量指标分母排除，但仍计入 attempted latency；错误数量单独报告。

## Before

正式历史基线（run 6）：

| Metric | Value |
| --- | ---: |
| Recall@5 / Recall@10 | 0.885 / 0.885 |
| MRR | 0.809 |
| nDCG@5 / nDCG@10 | 0.789022 / 0.789022 |
| Exact Citation Precision / Recall | 0.067513 / 0.116667 |
| Grounded Answer Rate | 1.000000 |
| Refusal Accuracy | 0.300000 |
| Unsupported Answer Rate | 0.000000 |
| Evidence Sufficiency Accuracy | 0.560000 |
| Supported Answer Recall | 0.222222 |

run 6 refusal confusion matrix：Gold supported `20 answer / 70 refuse`；Gold refusal `0 answer / 10 refuse`。Refusal Precision `0.125`，Refusal Recall `1.0`。

## Root Cause

run 6 的 70 条 supported false-refusal 中，40 条发生于前置 Evidence Gate，30 条发生于 post-answer validation。39 条在 final retrieval 中已包含全部 Gold evidence，但被 evidence selection 规则错误拒绝；仅 1 条是完整 retrieval miss。

已证明的主要原因：

1. 中文关系解析将普通文档归因“根据/依据”误当成法律依据关系。
2. scope 解析把泛化问句、动作性“针对”、以及实体后缀截断误当成适用范围约束。
3. 数值 answer-shape 将“数量、比例或编号”的析取问题错误要求为必须包含比例。
4. post-answer lexical claim gate 把无新增事实的导航、回指、政策文号和受支持跨文档归纳误判为 unsupported claim。
5. evaluator 的 exact Gold chunk 是生成题 seed，不是所有合法支持 chunk 的穷举集合；同文档其他合法 chunk 会在 exact metric 中记为 mismatch。

## Citation Audit

抽审覆盖 10 个 citation metric failure 和 5 个 success。run 13 回答样本的 emitted document citation precision/recall 达到 `0.918519 / 0.922222`，而 exact emitted chunk precision/recall 为 `0.445608 / 0.655556`。这证明低 exact 指标同时包含三类因素：false-refusal 的零 citation、同文档非 seed chunk、以及多 chunk 引用不完整；不能直接解释为“大量引用错误来源”。

原 exact 指标已保留。新增 document-level 与 emitted-only 指标只提供诊断维度，不修改 Gold，也不替代 exact contract。

## Retention Funnel

run 13 的 90 条 supported case：

| Stage | Any Gold Evidence | Complete Gold Set |
| --- | ---: | ---: |
| Top 10 | 89/90 (0.9889) | 68/90 (0.7556) |
| After Rerank | 89/90 (0.9889) | 68/90 (0.7556) |
| Final Retrieval | 89/90 (0.9889) | 68/90 (0.7556) |
| Context Packing | 87/90 (0.9667) | 66/90 (0.7333) |
| Cited | 33/90 (0.3667) | 26/90 (0.2889) |

没有 supported case 在 fusion→rerank 或 rerank→final 阶段丢失已有 Gold evidence。Remote Rerank 不是主要根因；21/22 个双 chunk supported case 在 fusion 阶段已只保留 1/2 Gold seed，属于独立的 multi-evidence completeness 信号。

## Intermediate After

首轮最小修复后的完整 run 13：

| Metric | Value |
| --- | ---: |
| Recall@5 / Recall@10 | 0.885 / 0.885 |
| MRR | 0.844833 |
| nDCG@5 / nDCG@10 | 0.809955 / 0.809955 |
| Exact Citation Precision / Recall | 0.222804 / 0.327778 |
| Emitted Exact Citation Precision / Recall | 0.445608 / 0.655556 |
| Document Citation Precision / Recall | 0.459259 / 0.461111 |
| Emitted Document Citation Precision / Recall | 0.918519 / 0.922222 |
| Grounded Answer Rate | 0.977778 |
| Refusal Accuracy | 0.550000 |
| Unsupported Answer Rate | 0.000000 |
| Evidence Sufficiency Accuracy | 0.970000 |
| Supported Answer Recall | 0.500000 |

run 13 confusion matrix：Gold supported `45 answer / 45 refuse`；Gold refusal `0 answer / 10 refuse`。无执行错误，10/10 Gold refusal 保持安全拒答。

run 13 failure distribution（最终窄修复前）：

| Category | Count | Percent of 64 failures |
| --- | ---: | ---: |
| POST_ANSWER_VALIDATION_UNRESOLVED | 40 | 62.50% |
| CITATION_EXPECTATION_MISMATCH | 11 | 17.19% |
| MULTI_CHUNK_CITATION_INCOMPLETE | 7 | 10.94% |
| INCORRECT_REFUSAL | 3 | 4.69% |
| EVIDENCE_GATE_FALSE_NEGATIVE | 2 | 3.13% |
| RETRIEVAL_MISS | 1 | 1.56% |

## Final After - run 16

最终且唯一一次 100 条 Human Verified Gold Evaluation 为 run 16，100/100
完成，execution error 为 0。最新结果如下：

| Metric | Value |
| --- | ---: |
| Recall@5 / Recall@10 | 0.885000 / 0.885000 |
| MRR | 0.840667 |
| nDCG@5 / nDCG@10 | 0.806227 / 0.806227 |
| Exact Citation Precision / Recall | 0.288069 / 0.433333 |
| Emitted Exact Citation Precision / Recall | 0.447003 / 0.672414 |
| Document Citation Precision / Recall | 0.588889 / 0.583333 |
| Emitted Document Citation Precision / Recall | 0.913793 / 0.905172 |
| Grounded Answer Rate | 0.948276 (55/58) |
| Refusal Accuracy / Precision / Recall | 0.680000 / 0.238095 / 1.000000 |
| Unsupported Answer Rate | 0.000000 |
| Evidence Sufficiency Accuracy | 0.960000 |
| Supported Answer Recall | 0.644444 (58/90) |

run 16 confusion matrix：Gold supported `58 answer / 32 refuse`；Gold refusal
`0 answer / 10 refuse`。安全拒答仍为 10/10，且拒答无 citation、无
unsupported answer。

run 16 的 90 条 supported case retention funnel：

| Stage | Any Gold Evidence | Complete Gold Set |
| --- | ---: | ---: |
| Top 10 | 89/90 (0.9889) | 68/90 (0.7556) |
| After Rerank | 89/90 (0.9889) | 68/90 (0.7556) |
| Context Packing | 87/90 (0.9667) | 66/90 (0.7333) |
| Cited | 44/90 (0.4889) | 34/90 (0.3778) |

最终失败分母为 56。root cause 为：post-answer validation unresolved 29，
citation expectation mismatch 13，multi-chunk citation incomplete 10，
Evidence Gate false negative 2，incorrect refusal 1，retrieval miss 1。
`CITATION_EXPECTATION_MISMATCH` 已命中预期文档并通过 safety validation，
表示 exact Gold seed 不穷举所有合法支持 chunk，不应直接解释为错误来源。

Remote Rerank provider 边界验收仍为 `PASS-LIVE`。run 16 的 100 条 trace
中 67 条 remote applied，33 条因 HTTP 429 fail-open，故 run-wide application
coverage 为 `PARTIAL-LIVE`。Top10 到 rerank 没有 evidence retention 下降，
因此 429 不是 32 条 supported false-refusal 的主要解释。

## Fixed Causes

- Legal-basis、penalty、cancellation 分关系验证；普通“根据/依据”、文档归因、`根据实际` 不再触发法律关系。
- 错误主体的法律责任、伪造取消关系、跨句歧义和对抗关系仍 fail-closed。
- scope 只接受有绑定语句的适用对象；错误地区、扩大企业范围、无证据负面 scope 仍拒绝。
- 政策文号加入 exact-value 校验；错误文号仍拒绝。
- 只忽略不引入实体、数值或关系的导航/回指元句，以及结构化 UUID citation note。
- “从 A 到 B”的跨文档归纳必须逐端点在引用中命中；缺少任一端点仍拒绝。
- post-answer validation 的完整 decision（reason、confidence、unsupported aspects）已持久化，不再只靠离线推断。
- 地区过滤规范化为生产数据使用的 `四川省`，未修改 Gold 或生产文档。

## Safety Regression

- 定向 citation/evidence/relation/context/rerank/refusal 套件：`129 passed`。
- Evidence/Relation 专项：`76 passed`，包含错误地域、扩大 scope、无证据负面 scope、错误处罚主体、错误文号、缺失跨文档端点和伪造/跨句关系。
- 最终 Backend 全量：`501 passed in 35.19s`；Ruff、Ruff format（237 files）、
  Mypy（167 files）、compileall、Alembic check 通过。
- Black 对生产源码的唯一受控检查在 Windows 上 120 秒超时，准确状态为
  `BLACK=UNVERIFIED-WINDOWS-TIMEOUT`，未重试。
- 最终 live Guard run 15：23 条 supported 中 14 条回答且 14/14 grounded；
  10/10 Gold refusal 安全拒答、citation=0、unsupported answer=0、error=0。
  QA14 固定子集为 5/8，状态 `FAIL-LIVE-QUALITY`。
- 最终 run 16 由最终镜像执行，100/100 完成且无 execution error；没有使用
  离线 replay 代替 live evaluation。

## Remaining

1. 32/90 条 supported 问题仍 false-refuse，其中 29 条属于 post-answer
   validation unresolved，2 条 Evidence Gate false negative，1 条 evidence
   通过后仍错误拒答。
2. 10 条 multi-chunk citation incomplete，另有 3/224 assessed claims 未
   grounded；唯一完整 retrieval miss 为 q071。
3. run 16 Remote Rerank 为 67 applied / 33 HTTP 429 fail-open，provider 边界
   已通过，但 run-wide capacity/reliability 仍是 `PARTIAL-LIVE`。
4. 最终质量目标未全部达到，准确结论为
   `GOLD_EVALUATION_QUALITY=PARTIAL`；本轮不再修改 validator 或重跑 100 条。
