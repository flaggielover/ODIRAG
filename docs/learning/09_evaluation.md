# 09 评估、基准与反馈闭环

## 1. 模块目的

评估模块用人工验证问题实际运行检索和 Chat，计算检索、答案点、引用、拒答、幻觉、延迟和成本指标，并生成可审计报告。它还接收用户反馈并把真实失败转换为新的 verified evaluation question。

## 2. 输入与输出

输入是 `EvaluationCase`/`EvaluationQuestion`：问题、预期文档/chunk、答案点、filters、是否应拒答、难度和类别，以及注入的 retrieval/chat callback。

输出包括：

- 每题 `EvaluationQuestionResult`、实际 retrieval/chat 数据、错误阶段和指标；
- 聚合 Recall@1/5/10、MRR、nDCG@10、文档/Chunk hit、答案点覆盖、引用准确/完整、拒答准确、幻觉率、P50/P95、tokens/cost；
- JSON、CSV、Markdown 和 `chart_data.json`；
- `EvaluationRun` 数据库记录和到命中证据的 lineage；
- Feedback 转换产生的 verified `EvaluationQuestion`。

## 3. 数据流

```text
verified questions
  -> EvaluationApplicationService
  -> EvaluationRunner
     -> retrieval callback
     -> chat callback
     -> EvaluationSample
  -> per-question metrics
  -> aggregate metrics
  -> write_evaluation_reports()
  -> EvaluationRun + DataLineage

UserFeedback
  -> FeedbackService.convert_to_evaluation()
  -> verified EvaluationQuestion
  -> 下一轮回归评估
```

默认 `fail_fast=False`，单题检索或 Chat 异常会记录 error_stage/error，并用空结果参与报告，而不是隐藏失败或中断剩余问题。

## 4. 核心类与文件

- `backend/app/evaluation/metrics.py`：样本与聚合指标公式。
- `backend/app/evaluation/runner.py`：case 执行、耗时、错误隔离和 sample 构建。
- `backend/app/evaluation/reports.py`：四类原子写入报告。
- `backend/app/services/evaluation.py`：真实 ODIRAG 检索/Chat 回调、持久化与报告读取。
- `backend/app/repositories/evaluation.py`：问题、run 和 lineage 数据访问。
- `backend/app/models/evaluation.py`：`EvaluationQuestion`、`EvaluationRun`、`Experiment`。
- `backend/app/services/feedback.py`、`repositories/feedback.py`：反馈转评估。
- `backend/app/api/routes/evaluations.py`、`feedback.py`：API。
- `data/evaluation/demo_benchmark.yaml`：固定 demo benchmark。
- `backend/tests/unit/test_evaluation_phase9.py`、`backend/tests/integration/test_evaluation_api.py`、`test_feedback_api.py`。

## 5. 主要设计决策

1. Runner 依赖注入 retrieval/chat callback，指标框架不绑定具体 Provider。
2. `expected_chunk_ids` 优先用于排名与引用；没有 chunk 期望时可退回 document 级。
3. Recall、MRR 和 nDCG 基于去重后的排名；无 relevant item 的样本按无需召回处理。
4. Citation accuracy 是 precision，completeness 是 recall，避免只报一个引用指标。
5. 幻觉率只统计 callback 明确提供 `claim_count>0` 的 claim；未评估问题不进入分母。
6. 报告常量 `HALLUCINATION_SCOPE` 明示这一范围，防止把 0 误解为全自动事实核验通过。
7. P50/P95 采用 nearest-rank；tokens/cost 来自实际 callback，缺失时不伪造。
8. 报告使用临时文件再 replace，减少中途写坏 artifact。
9. `helpful` 反馈不能转换为回归；其他六类负反馈按类型生成期望文档/chunk/拒答标签。
10. 重复转换使用稳定 `feedback-{id}`，保持幂等。

## 6. 技术选型原因

- Dataclass 指标模型：公式层轻量、不可变、易单测。
- 注入回调：同一评估器可测试真实 runtime、实验 variant 或 deterministic fixture。
- JSON/CSV/Markdown/chart-ready：分别服务程序分析、表格复查、人工报告和前端图表。
- 数据库 + 文件 artifact：数据库便于列表查询，文件保存逐题详情和可移植报告。
- 固定 benchmark：prompt、chunk、embedding、检索、重排和拒答变更都可做回归比较。
- 用户反馈转题：把线上真实错误变成可重复测试，而不是只记一条工单。

## 7. 常见故障模式

- question 未 verified：真实评估服务应只运行明确验证的数据或请求内 verified case。
- expected ID 与当前索引版本不一致：Recall/Citation 会下降，应检查重建后 chunk ID 变化。
- retrieval callback 异常：该题 error_stage=`retrieval`，后续题仍运行。
- chat callback 异常：保留 retrieval 数据，error_stage=`chat`。
- 幻觉率为 0 但 assessed_claims 为 0：表示没有评估 claim，不能宣称无幻觉。
- Citation accuracy 高、completeness 低：引用都正确，但漏引预期证据。
- report artifact 找不到：检查 `evaluation_artifact_dir`、写权限和数据库 `result_path`。
- helpful feedback 转换返回 409：这是防止正向样本被错误当回归。
- missing_document/should_not_refuse 未给 expected_document_id：schema 返回 422。

## 8. 调试步骤

1. 检查每题 expected document/chunk 是否存在且与当前版本一致。
2. 先看 report 的 `questions[].error_stage/error`，不要只看 aggregate。
3. 对排名问题比较 retrieved IDs、relevant IDs 和去重顺序。
4. 对引用问题分别计算 cited ∩ expected、cited 数和 expected 数。
5. 检查 `hallucination_assessed_claims/questions` 后再解释 hallucination_rate。
6. 比较 run 的 retrieval_version、prompt_version、embedding_model、rerank_model 和 top_k。
7. 检查四个 artifacts 是否同属一个 run 目录且 JSON question_count 一致。
8. 定向运行：`python -m pytest tests/unit/test_evaluation_phase9.py tests/integration/test_evaluation_api.py tests/integration/test_feedback_api.py`。

## 9. 面试问题与参考答案

### 9.1 Recall@k、MRR 和 nDCG 的区别是什么？

Recall@k 看前 k 是否覆盖相关项；MRR 强调第一个相关项出现位置；nDCG 对整个前 k 排序位置折损，能区分同样召回但排序质量不同的结果。

### 9.2 为什么引用需要 accuracy 和 completeness 两个指标？

只看 accuracy 可能只引用一个正确来源却漏掉其他必要证据；只看 completeness 又可能加入错误引用。precision/recall 分别覆盖两类风险。

### 9.3 幻觉率为何不能直接根据答案文本自动算？

需要定义 claim 并判断是否被证据支持。当前由 chat callback 显式提供 assessed/hallucinated claim 数，未评估 claim 不进入分母，报告会披露范围。

### 9.4 为什么单题失败不立即停止？

评估目标是收集完整失败分布。默认隔离错误可以看到其他问题表现；调试特定问题时才启用 fail_fast。

### 9.5 用户反馈如何避免重复创建评估题？

question ID 固定为 `feedback-{feedback.id}`，转换前先查询；重复调用只更新同一反馈状态，不新增第二题。

## 10. 答辩问题与参考答案

### 10.1 如何证明指标不是硬编码？

集成测试先创建并索引真实文档，再通过 `/api/evaluations/run` 执行两个问题，报告中的 IDs、答案、引用和指标来自实际 callback；公式还有独立边界单测。

### 10.2 demo evaluation 能代表生产效果吗？

不能。它证明执行链和指标计算可运行；样本量、语料和 deterministic Provider 都有限，最终报告必须分别说明本地 demo 与真实外部模型结果。

### 10.3 为什么评估结果还要关联 lineage？

当指标回归时需要追溯命中的 chunk、文档版本和来源，判断是模型、索引版本还是语料变化导致。

### 10.4 P95 低于目标是否就是 SLA？

不是。指南把 search/chat/DB P95 明确列为工程目标，实际本地负载测试必须报告环境、并发、样本量和实际值，不能外推为生产 SLA。

### 10.5 反馈转换后是否自动修改模型？

不会。它只创建 verified evaluation question；后续通过评估和实验验证候选改动，避免未经验证的在线自动学习破坏质量。

## 11. 代码阅读路线

1. `backend/app/evaluation/metrics.py`
2. `backend/app/evaluation/runner.py`
3. `backend/app/evaluation/reports.py`
4. `backend/app/services/evaluation.py`
5. `backend/app/repositories/evaluation.py`
6. `backend/app/services/feedback.py`
7. Evaluation/Feedback API
8. 指标单测、真实评估和反馈集成测试

## 12. 实践修改练习

新增按 `category`、`difficulty` 分组的指标切片。要求复用现有公式，JSON/Markdown/chart data 同时输出；小样本明确显示 question_count；不把空分组写成 100% 成功，并新增两个类别、一个失败 case 的报告测试。
