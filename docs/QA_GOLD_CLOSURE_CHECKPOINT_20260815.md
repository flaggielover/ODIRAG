# QA Gold Closure Checkpoint - 2026-08-15

## Pause State

- Mode: `SAFE_PAUSE`
- Current phase: step 6 of 8, final live guard / final image boundary
- Estimated completion: 82%
- No new quality, provider, benchmark, build, migration, or test task may be started tonight.
- Process check found no Python/Black/pytest/evaluation/build process. Only normal responsive Docker Desktop backend processes remained.
- No process was force-killed. No container, volume, database, code change, or artifact was deleted.

## Completed Tonight

- Audited the evaluation metric contract and preserved exact-chunk citation metrics.
- Added emitted-only and document-level citation metrics, refusal precision/recall, supported-answer recall, assessed denominators, and execution-error accounting.
- Generated and audited the 100-case failure matrix for run 13.
- Completed 10 citation-failure plus 5 citation-success provenance review.
- Classified retrieval/rerank/context/evidence/citation retention and refusal confusion.
- Implemented evidence, relation, scope, policy-identifier, meta-claim, and observability fixes proven by the failure matrix.
- Persisted generated answer, generated citation IDs, selected context IDs, and final answer-validation decision.
- Added safe `model_output_invalid` handling for malformed provider output.
- Added region canonicalization from `四川` to the production value `四川省`.
- Targeted quality regression reached `129/129 passed`.
- Evidence/relation/scope suite reached `76/76 passed`.
- Full backend regression reached `501/501 passed` after updating the stale integration fixture to `四川省`.
- Ruff check passed, Ruff format reported 237 files formatted, Mypy passed 167 source files, compileall passed, and `git diff --check` passed.
- Black is **not passed**: even `black --version` and source-scoped checks timed out in the current Windows Python environment. Do not report Black PASS.

## Live Runs Preserved

### Full run 13

- Host artifacts: `data/evaluation/gold_run_13/`
- 100 questions, 0 execution errors.
- Supported confusion: 45 answered / 45 refused.
- Gold-refusal confusion: 0 answered / 10 refused.
- Recall@5 0.885; Recall@10 0.885; MRR 0.844833; nDCG@10 0.809955.
- Exact citation precision/recall 0.222804 / 0.327778.
- Emitted document citation precision/recall 0.918519 / 0.922222.
- Grounded answer rate 0.977778; unsupported answer rate 0.0.
- Evidence sufficiency accuracy 0.97; supported answer recall 0.50.
- Root matrices are also copied to `data/evaluation/gold_failure_matrix.json` and `.csv`.

### Targeted run 14

- Evaluation run ID: `14`
- Run name: `phase-j-final-targeted-30-20260815`
- Docker volume artifact: `/app/data/evaluation/runs/14/evaluation.json` in the persistent `app-data` volume.
- 20 supported + all 10 Gold-refusal questions; 0 execution errors.
- Supported: 12 answered / 8 refused.
- Gold refusal: 0 answered / 10 refused; all ten had zero final citations.
- Recall@5 0.883333; Recall@10 0.916667; MRR 0.894762; nDCG@10 0.855957.
- Refusal accuracy 0.733333; refusal precision 0.555556; refusal recall 1.0; supported answer recall 0.60.
- Grounded answer rate 0.916667 (11/12); unsupported answer rate 0.0; hallucination rate 0.023256.
- Exact citation precision/recall 0.241667 / 0.375.
- Emitted document citation precision/recall 0.875 / 0.875.
- This run used the currently running Uvicorn process. It covered all fixes except the last in-memory q082 compressed progression endpoint update; disk source contains that final update and DB replay passes q082.

Supported refusals in run 14 were q025, q032, q039, q045, q048, q069, q088, and q098. q032 is intentionally conservative because the answer broadened `有研/符合条件企业` to all industrial enterprises. The other generated variants require final rerun under the disk source before classification.

## Current Code Checkpoint

Critical disk hashes:

```text
91FE93DE802250B48B00F713A32EAA4883A53395C998608ED836CDFFCB4519D1  backend/app/rag/evidence.py
E8270F913F6D93248AB1BCA1EAED70F340F0BD8FDE02E6C5906AAC9C9E24FB62  backend/app/services/chat.py
3F78CB56DF8742D089D747FC787F17CA69FE036E16F04D8619EB546DF0B4B35F  backend/app/evaluation/failure_analysis.py
1BDC732CBFCE44B2F74080DED5A31BE0917072993E1A58947A2AA8605D1062A4  data/evaluation/phase_j_human_verified.json
8F557B691E580847FFD5F7E2F99F28F2BB4AEFB70DDD4047BEADAE9D7E660B9E  data/evaluation/gold_failure_matrix.json
2C3E0D67F87A3AB0FBBAA15389AC10B5547B73AF85AD8F11A3C8D387F1FAD436  GOLD_EVALUATION_FAILURE_ANALYSIS.md
```

Key quality changes:

- `backend/app/evaluation/metrics.py`, `reports.py`, `runner.py`: metric contract and denominators.
- `backend/app/evaluation/failure_analysis.py`, `scripts/analyze_gold_failures.py`: failure matrix, root classification, retention funnel, citation sampling.
- `backend/app/rag/evidence.py`: minimum evidence/relation/scope/claim fixes; no global threshold reduction and no validator bypass.
- `backend/app/services/chat.py`, `evaluation.py`: answer-validation observability and safe malformed-model refusal.
- `backend/app/retrieval/analysis.py`: canonical region mapping.
- `backend/tests/unit/test_evidence_sufficiency.py`, `test_chat_grounding.py`, `test_evaluation_phase9.py`, `test_gold_failure_analysis.py`, `test_retrieval_phase6.py`: regression coverage.

New quality-closure files:

- `GOLD_EVALUATION_FAILURE_ANALYSIS.md`
- `backend/app/evaluation/failure_analysis.py`
- `backend/tests/unit/test_gold_failure_analysis.py`
- `scripts/analyze_gold_failures.py`
- `data/evaluation/gold_failure_matrix.json`
- `data/evaluation/gold_failure_matrix.csv`
- `data/evaluation/gold_run_13/`

## Git State

- Worktree is intentionally uncommitted and contains pre-existing user work from several phases.
- Tracked diff: 48 files, 3326 insertions, 297 deletions.
- A safe isolated commit was not created because changes are mixed with pre-existing work and prior repository ACL evidence reports `.git` index writes blocked.
- `GIT_CHECKPOINT=BLOCKED-LOCAL-PERMISSION`
- No reset, clean, checkout, revert, or deletion was attempted.

Tracked modified files:

```text
.env.example
IMPLEMENTATION_STATUS.md
PRODUCTION_ACCEPTANCE_CHECKLIST.md
PRODUCTION_READINESS_REPORT.md
backend/app/config.py
backend/app/crawler/__init__.py
backend/app/crawler/fetcher.py
backend/app/crawler/generic.py
backend/app/crawler/storage.py
backend/app/crawler/urls.py
backend/app/embedding/__init__.py
backend/app/evaluation/metrics.py
backend/app/evaluation/reports.py
backend/app/evaluation/runner.py
backend/app/main.py
backend/app/models/document.py
backend/app/models/observability.py
backend/app/rag/evidence.py
backend/app/retrieval/analysis.py
backend/app/runtime.py
backend/app/schemas/chat.py
backend/app/schemas/document.py
backend/app/services/chat.py
backend/app/services/crawl.py
backend/app/services/evaluation.py
backend/app/services/parsing.py
backend/app/services/source_discovery.py
backend/app/tasks/source_discovery.py
backend/tests/integration/test_phase_g_data_debt.py
backend/tests/integration/test_phase_j_draft_dataset.py
backend/tests/integration/test_search_api.py
backend/tests/integration/test_source_discovery_api.py
backend/tests/unit/test_chat_grounding.py
backend/tests/unit/test_evaluation_phase9.py
backend/tests/unit/test_evidence_sufficiency.py
backend/tests/unit/test_models.py
backend/tests/unit/test_providers_and_retrieval.py
backend/tests/unit/test_rate_limit.py
backend/tests/unit/test_rerank_phase_b.py
backend/tests/unit/test_retrieval_phase6.py
backend/tests/unit/test_tasks.py
docker-compose.yml
scripts/build_phase_j_draft.py
scripts/live_accept_coze_batch.py
scripts/load_test.py
scripts/rebuild_bm25.py
scripts/run_experiment.py
scripts/seed_demo.py
```

Untracked content includes the following exact files/directories; do not delete them:

```text
ATTACHMENT_OCR_REPORT.md
DISASTER_RECOVERY_REPORT.md
FINAL_ACCEPTANCE_REPORT.md
GOLD_EVALUATION_FAILURE_ANALYSIS.md
PERFORMANCE_REPORT.md
SECURITY_READINESS_REPORT.md
backend/alembic/versions/0010_query_trace_stage_timings.py
backend/alembic/versions/0011_attachment_download_audit.py
backend/app/attachments/
backend/app/crawler/dns.py
backend/app/embedding/cached.py
backend/app/evaluation/failure_analysis.py
backend/app/evaluation/human_review.py
backend/app/ocr/
backend/app/services/attachment_download.py
backend/tests/integration/test_attachment_download.py
backend/tests/unit/test_attachment_detection.py
backend/tests/unit/test_attachment_download.py
backend/tests/unit/test_benchmark_rag_performance.py
backend/tests/unit/test_doh_resolver.py
backend/tests/unit/test_gold_failure_analysis.py
backend/tests/unit/test_human_evaluation_review.py
backend/tests/unit/test_source_discovery_relevance.py
data/evaluation/eval_human_review.xlsx
data/evaluation/eval_human_review.xlsx.inspect.ndjson
data/evaluation/eval_human_review_preview.png
data/evaluation/gold_failure_matrix.csv
data/evaluation/gold_failure_matrix.json
data/evaluation/gold_quality_run_7/
data/evaluation/gold_run_13/
data/evaluation/gold_run_6/
data/evaluation/gold_safety_run_11/
data/evaluation/gold_safety_run_12/
data/evaluation/gold_targeted_run_10/
data/evaluation/gold_targeted_run_8/
data/evaluation/gold_targeted_run_9/
data/evaluation/phase_ab_benchmark.json
data/evaluation/phase_ab_quality_guard.json
data/evaluation/phase_j_human_verified.json
data/evaluation/phase_o_benchmark.json
data/performance/
docs/EVALUATION_HUMAN_REVIEW_GUIDE.md
docs/superpowers/specs/2026-08-14-n-o-p-closure-design.md
scripts/analyze_gold_failures.py
scripts/benchmark_rag_performance.py
scripts/import_human_evaluation_review.py
scripts/process_attachments.py
scripts/summarize_human_verified_gold.py
```

## Docker And Migration State

- Latest successful image build: `odirag/backend:local`, manifest list `sha256:52a123625cdf3999ae1052f02490de0f2ba5ca5bd4fb2f18e301966b6540cb57`.
- That image predates the final q082 compressed-endpoint disk change.
- The latest `evidence.py` was copied into `odirag-backend-1`, but restart approval timed out twice. The running Uvicorn process therefore must be treated as the previous in-memory code until verified after restart.
- Final rebuild/recreate of backend, worker, and scheduler is still required.
- Migration files form head `0011_attachment_download_audit` over `0010_query_trace_stage_timings`. The real DB revision was not freshly queried tonight because Docker exec approval timed out; do not claim a fresh Alembic check.
- Current local API health is `healthy`; database, Redis, and Qdrant dependencies are all healthy.
- Current Qdrant collection is `green` with exactly 821 points.
- The final eight-service `docker compose ps` refresh was blocked by approval-service overload; last accepted project state remains 8/8 healthy.

## Data Safety

- Last verified corpus baseline remains 182 documents: 101 approved, 35 rejected, 46 pending; 821 chunks.
- Current Qdrant was freshly confirmed at 821 green points.
- Run 14 only added evaluation/query-trace rows and its artifact; it did not mutate documents, chunks, or vectors.
- No migration, crawl, reindex, benchmark, provider run, or long transaction was started after SAFE PAUSE.
- API dependency health confirms PostgreSQL, Redis, and Qdrant are reachable and healthy.
- Direct SQL activity/Redis persistence detail was not refreshed because the approval service timed out. There is no local Python task or known migration process running.
- It is safe to perform a normal Windows restart. Do not run `docker compose down -v`, prune, or delete volumes.

## Artifacts Safe On Disk

- Human Gold: `data/evaluation/phase_j_human_verified.json`
- Historical baseline: `data/evaluation/gold_run_6/`
- Current full run: `data/evaluation/gold_run_13/`
- Root failure matrix: `data/evaluation/gold_failure_matrix.json` and `.csv`
- Prior safety/targeted runs: `gold_safety_run_11`, `gold_safety_run_12`, `gold_targeted_run_8/9/10`
- Partial QA16 analysis: `GOLD_EVALUATION_FAILURE_ANALYSIS.md`
- Run 14: persistent Docker `app-data` volume and evaluation DB row ID 14; copy to the host tomorrow.

## Final Continuation Result - run 16

The 2026-08-15 checkpoint resume completed successfully. No reset, clean, volume
deletion, Gold edit, validator change, or second final evaluation run occurred.

### Restored Environment

- Docker Desktop was restarted and all eight Compose services became healthy.
- Corpus baseline matched the checkpoint before and after evaluation: documents
  `182`, approved `101`, rejected `35`, pending manual review `46`, chunks `821`,
  Qdrant `green / 821 points`.
- Key code and Human Gold hashes matched this checkpoint. The final run16 failure
  matrix intentionally has a new hash because its source run changed from run13
  to run16.
- Migration is `0011_attachment_download_audit (head)` and Alembic reports
  `No new upgrade operations detected`.

### Final Image And Guard

- Final backend image was built once. Manifest list:
  `sha256:70b8e21a15aa2b2f1f3fccfccb56ce6aa3e68d36b1119384d43e59632e55f7c5`.
- Only backend, worker, and scheduler were recreated; all three use that same
  image and are healthy. PostgreSQL, Redis, Qdrant, frontend, nginx, and all
  volumes were preserved.
- Final Live Guard run 15: supported `14 answer / 9 refuse`, all 14 answered
  cases grounded; Gold refusal `10/10`, citations `0`, unsupported answers `0`,
  errors `0`. QA14 passed `5/8`, so `QUALITY_GUARD=FAIL-LIVE-QUALITY` while the
  refusal-safety contract passed.
- Guard Remote Rerank was `20 applied / 13 HTTP 429 fail-open`.

### Final Gold

- The only final 100-case evaluation was run 16,
  `phase-j-final-gold-100-20260815`: 100/100, zero execution errors.
- Metrics: Recall@5/10 `0.885/0.885`, MRR `0.840667`, nDCG@5/10 `0.806227`,
  exact citation P/R `0.288069/0.433333`, grounded `0.948276`, refusal accuracy
  `0.68`, unsupported-answer rate `0`, Evidence Sufficiency Accuracy `0.96`,
  Supported Answer Recall `0.644444`.
- Confusion: Gold supported `58 answer / 32 refuse`; Gold refusal
  `0 answer / 10 refuse`.
- Run-wide Remote Rerank: `67 applied / 33 HTTP 429 fail-open`, status
  `PARTIAL-LIVE`. Provider boundary acceptance remains `PASS-LIVE`.
- Final quality decision: `GOLD_EVALUATION_QUALITY=PARTIAL`.

### Final Regression And Artifacts

- Backend pytest: `501 passed in 35.19s`.
- Ruff PASS; Ruff format `237 files already formatted`; mypy PASS over 167 files;
  compileall, Alembic check, and `git diff --check` PASS.
- Black production-source check timed out at 120 seconds:
  `BLACK=UNVERIFIED-WINDOWS-TIMEOUT`.
- Runtime: 8/8 healthy, homepage 200, API/dependencies healthy, PostgreSQL
  accepting, Redis PONG, Qdrant green/821.
- Final artifacts: `data/evaluation/gold_run_16/`,
  `data/evaluation/gold_metrics.json`, `data/evaluation/gold_summary.md`, and
  final `gold_failure_matrix.json/.csv`.
- Checkpoint status: `RESTORED-AND-CLOSED`.
