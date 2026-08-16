# Gold Quality Closure Checkpoint

Checkpoint date: 2026-08-15

Status: `RESTORED-AND-CLOSED`

## 当前完成

- Checkpoint 恢复、代码/Gold hash 核对、数据基线核对已完成。
- 最终 backend 镜像只构建一次；backend、worker、scheduler 已用同一最终
  镜像重建，其他服务和全部 volume 保留。
- Final Live Guard run 15 已完成：23 supported 中 14 answer/9 refuse；
  10/10 Gold refusal 安全拒答，citation=0、unsupported answer=0、error=0。
- 唯一一次最终 100-Gold run 16 已完成：100/100，0 execution errors。
- 正式 run16 metrics、summary、failure matrix、refusal confusion、retention
  funnel 与 Before/Intermediate/After 已写盘。
- 最终结论为 `GOLD_EVALUATION_QUALITY=PARTIAL`；没有修改 Gold、降低阈值、
  关闭 validator 或开启第二轮优化。
- 最终 backend pytest `501 passed`；Ruff、Ruff format、mypy、compileall、
  Alembic check 与 diff check 通过。
- Black 唯一受控检查在 Windows 上 120 秒超时，准确记录为
  `BLACK=UNVERIFIED-WINDOWS-TIMEOUT`。
- 8/8 Compose services healthy；homepage 200；PostgreSQL、Redis、Qdrant
  healthy；documents 182、approved 101、rejected 35、pending 46、chunks 821、
  Qdrant green/821 points。
- 五份顶层报告、`GOLD_EVALUATION_FAILURE_ANALYSIS.md` 和本 checkpoint 已同步。

## 当前未完成

Gold Evaluation Quality Closure 范围内没有待执行任务。以下是 closure 之外
的真实项目剩余项，不应在本 checkpoint 中继续：

- P95 性能目标及 Direct LLM latency。
- Attachment/OCR 完整验收。
- Production Engineering：backup/PITR、Qdrant snapshot、Redis recovery/HA、
  retention、资源/日志/告警、TLS、Secret Manager、发布 provenance。
- Remote Rerank run-wide HTTP 429 capacity/reliability。
- Cloud Production Deployment。

## 当前代码状态

- Dirty working tree 被完整保留；未执行 reset、clean 或删除未跟踪产物。
- `GIT_CHECKPOINT=BLOCKED-LOCAL-PERMISSION`，保留未提交 diff。
- Final image manifest list:
  `sha256:70b8e21a15aa2b2f1f3fccfccb56ce6aa3e68d36b1119384d43e59632e55f7c5`。
- Migration: `0011_attachment_download_audit (head)`，无 Alembic drift。
- Final artifacts: `data/evaluation/gold_run_16/`、
  `data/evaluation/gold_live_guard_run_15/`、`data/evaluation/gold_metrics.json`、
  `data/evaluation/gold_summary.md`、`data/evaluation/gold_failure_matrix.*`。

## 下次会话

不要重复 run6/run13 audit、failure matrix discovery、Final Live Guard、run16
或 501-test closure。仅在用户明确开启新的项目阶段时，从上述 closure 外
剩余项选择一个独立目标。
