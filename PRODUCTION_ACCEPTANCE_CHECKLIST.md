# ODIRAG Production Acceptance Checklist

> Historical cumulative checklist: later Phase 1-5 execution reached
> `PRODUCTION_READINESS=PASS-LIVE`; see `PRODUCTION_READINESS_REPORT.md`. Older unchecked provider,
> TLS, recovery, monitoring, and release items below are retained as checkpoint history, not current
> blockers. The still-open Gold quality, OCR, unsupported attachment, and other explicitly current
> boundaries remain valid.

## Attachment / OCR closure gate (2026-08-15, latest authoritative)

- [x] Re-read real PostgreSQL before implementation and persisted
  `ATTACHMENT_BASELINE_REPORT.md`: 123 total, 0 parsed, 77 failed, 46
  unsupported, 0 pending, and 0 local files.
- [x] Reused trusted DNS resolution, public-IP validation, pinned connections,
  per-redirect validation, DNS rebinding protection, private/localhost/link-local
  blocking, timeout, and maximum-size guards. No SSRF allowlist was weakened.
- [x] Downloaded only current Attachment rows; no CrawlTask, corpus expansion,
  provider request, attachment reindex, or Qdrant write was started.
- [x] Byte identity is SHA-256 of actual file bytes. Storage uses an
  attachment-specific key, temporary file, fsync, size/hash validation, atomic
  replace, and cleanup. Final temporary residue is zero.
- [x] Cache validity includes content hash plus parser/version, and OCR cache adds
  provider/version. A real DOCX repeat was unchanged and skipped parser work.
- [x] Final current states are parsed `60`, failed `8`, unsupported `55`, pending
  `0`; all 123 rows are terminal with explicit reason/retryability.
- [x] Parser results: PDF `46/53`, DOCX `13/13`, XLSX `1/1`; 60/60 downloaded
  supported files parsed, while seven PDFs failed at HTTP 404.
- [x] Nine OLE files incorrectly served with DOCX MIME were proven by magic bytes
  and reclassified as `UNSUPPORTED_LEGACY_FORMAT`.
- [ ] OCR provider acceptance remains open: provider is not configured, the sole
  current image URL is HTTP 404, and no live OCR attempt/success exists. No success
  is fabricated; `ATTACHMENT_OCR=PARTIAL`.
- [x] Parsed provenance is complete 60/60; ten-item content/provenance quality
  sampling passed 10/10.
- [x] Final engineering: pytest `518/518`, Ruff check PASS, Ruff format `245/245`,
  mypy `169` files, compileall PASS, Alembic check PASS.
- [ ] Black remains `UNVERIFIED-WINDOWS-TIMEOUT`: even `--version` exceeded the
  bounded 30-second check; no residual process remained.
- [x] Final Docker runtime is 8/8 healthy; migration is 0012; API database/Redis/
  Qdrant dependencies are healthy.
- [x] Frozen core is unchanged: documents `182`, approved `101`, rejected `35`,
  pending `46`, chunks `821`, Qdrant green/`821`, Gold hashes unchanged, and prior
  5/5/Rerank/Brave/Human Evaluation gates retained.
- [ ] `ATTACHMENT_DOWNLOAD=PARTIAL`: eight real HTTP 404 failures remain and 45
  historical completed unsupported rows still lack verifiable bytes.

## Final Gold closure gate (2026-08-15, latest authoritative)

This checklist supersedes older Gold, guard, backend, image, and migration entries
below where they differ.

- [x] Restored the checkpoint without resetting/cleaning the dirty worktree or
  deleting any PostgreSQL, Redis, Qdrant, Docker, or artifact data.
- [x] Built the final backend image once and recreated only backend, worker, and
  scheduler. All three use manifest list `sha256:70b8e21a...` and are healthy.
- [x] Final Live Guard run 15 covered 23 supported and all 10 Gold refusal cases;
  all 10 refusal cases refused with zero citation, zero unsupported answer, and
  zero execution error.
- [ ] Final Live Guard answer-quality acceptance: supported result is
  `14 answer / 9 refuse`; QA14 is `5/8`, so status remains
  `FAIL-LIVE-QUALITY` despite refusal safety passing.
- [x] Final run 16 executed exactly one 100-case Human Verified Gold evaluation,
  100/100 with zero execution errors; artifacts are persisted under
  `data/evaluation/gold_run_16/` and the formal root artifact paths.
- [ ] Supported-answer acceptance: `58/90` answered; Supported Answer Recall
  `0.644444` remains below the suggested `0.80` target.
- [ ] Refusal-accuracy acceptance: `0.68` remains below the suggested `0.80`
  target, although Gold-refusal recall is `10/10 = 1.0` and unsafe answers are 0.
- [x] Evidence Sufficiency Accuracy is `0.96`; Unsupported Answer Rate is `0`.
- [ ] Remote Rerank run-wide reliability: provider boundary stays `PASS-LIVE`,
  but run 16 has `67 applied / 33 HTTP 429 fail-open`, hence `PARTIAL-LIVE`.
- [x] Final backend regression: `501 passed`; Ruff, Ruff format (237 files), mypy
  (167 files), compileall, Alembic check, and diff check pass.
- [ ] Black cannot be marked PASS: the only controlled production-source check
  timed out at 120 seconds; `BLACK=UNVERIFIED-WINDOWS-TIMEOUT`.
- [x] Final runtime/data gate: 8/8 healthy, homepage 200, dependencies healthy,
  PostgreSQL accepting, Redis PONG, documents `182`, approved `101`, rejected
  `35`, pending `46`, chunks `821`, Qdrant green/`821` points.
- [x] Retained completed gates:
  `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`,
  `REMOTE_RERANK_PROVIDER=PASS-LIVE`, `REMOTE_RERANK_FULL_RAG=PASS-LIVE`, and
  `BRAVE_SOURCE_DISCOVERY=PASS-LIVE`.
- [ ] Overall production acceptance remains open. Gold quality status is
  `PARTIAL`; P95, attachment/OCR, production engineering, and cloud production
  deployment remain outside this closure.

## Phase AD Gold evaluation final gate (2026-08-14, latest authoritative checkpoint)

- [x] Canonical `data/evaluation/eval_human_review.xlsx` contains exactly 100 rows
  with real document/source/chunk evidence. The user completed all six human-review
  fields for every row with `PASS` and the approved review note.
- [x] Workbook inspect/formula scan/render QA completed; no formula errors or
  macros. The strict importer remains authoritative for values and traceability.
- [x] Live-PostgreSQL dry-run and apply both returned
  `TOTAL=100`, `REVIEWED=100`, `UNREVIEWED=0`, `PASS=100`, `FIX=0`, `REJECT=0`,
  `VERIFIED=100`, `TRACEABILITY_ERRORS=0`; final output is
  `data/evaluation/phase_j_human_verified.json`.
- [x] Human-review statuses are
  `HUMAN_REVIEW_INFRASTRUCTURE=PASS-LOCAL`, `HUMAN_EVALUATION=PASS-HUMAN`,
  `HUMAN_VERIFIED_COUNT=100`, and `HUMAN_REVIEW_COMPLETE=true`.
- [x] Formal Gold run `6` executed all 100 questions through the real evaluation
  API with zero execution errors. Recall@5/10=`0.885`, MRR=`0.809`,
  nDCG@5/10=`0.789022`; citation precision=`0.067513`, citation recall=`0.116667`,
  refusal accuracy=`0.3`, unsupported-answer rate=`0.0`, evidence-sufficiency
  accuracy=`0.56`.
- [x] Run `5` is retained as a failed preflight only (unsupported metadata filters)
  and is excluded from all Gold metrics.
- [ ] Gold answer-quality acceptance: run `7` passed 2/2 refusal cases but 0/2
  intended-supported cases; status is `FAIL-LIVE-QUALITY` and no safety threshold
  was lowered.
- [x] Gold artifacts are `data/evaluation/gold_run_6/gold_metrics.json` and
  `gold_summary.md`; the 2+2 guard artifacts are under
  `data/evaluation/gold_quality_run_7/`.
- [x] Fixed performance workload: 20 Phase-J draft cases, three total warm-ups,
  three complete runs, 60 valid samples, zero Brave calls.
- [x] Before profile: P50 `2582 ms`, P95 `8763 ms`, P99 `10082 ms`.
- [x] After profile: P50 `1638 ms`, P95 `6774 ms`, P99 `9129 ms`; P95 improved
  `22.7%`; best complete-run P95 `6056 ms`.
- [x] Query embedding cache and shared Remote Embedding/Direct LLM connection pools
  verified; Remote Rerank and all evidence/citation/refusal controls unchanged.
- [ ] P95 acceptance: `6774 ms` is not `<5000 ms`; status remains
  `RAG_PERFORMANCE_P95=PARTIAL`.
- [x] Quality safety: the independent guard's two refusal cases returned refusal,
  zero citations, and no unsupported answer.
- [ ] Supported quality guard: both intended-supported human-gold cases refused;
  the supported-answer gate remains `FAIL-LIVE-QUALITY` rather than a fabricated
  pass.
- [x] Backend baseline remains `450 passed`; current Human Review/Gold helper
  checks pass with Ruff, mypy, compile, and `git diff --check`. Production Alembic
  remains at the previously verified `0010` head; no migration was needed for
  Human Review or Gold evaluation.
- [x] Runtime: 8/8 Compose services healthy; homepage and system health HTTP 200.
- [x] Core invariants: documents `182`, approved `101`, rejected `35`, pending
  `46`, chunks `821`, Qdrant green/optimizer OK with `821` exact points, and
  `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`.
- [x] Completed gates retained without modification:
  `REMOTE_RERANK_PROVIDER=PASS-LIVE`, `REMOTE_RERANK_FULL_RAG=PASS-LIVE`, and
  `BRAVE_SOURCE_DISCOVERY=PASS-LIVE`.

## Phase Z final Source Governance gate (2026-08-14, latest authoritative checkpoint)

- [x] Real Brave run `4`, candidate `7`, used
  `https://jxt.sc.gov.cn/scjxt/index.shtml` with one bounded provider candidate.
- [x] Official validation: HTTPS, HTTP 200, exact host/site, `.gov.cn`, government
  markers, and official score `1.0`.
- [x] Trial crawl: six columns, `30 fetched / 2 DIRECT accepted / 28 rejected`,
  accepted average length `798`.
- [x] Quality gate: `0.7667 >= 0.65`; threshold and official/trial scores were not
  changed or overridden.
- [x] Governance negative proof: `pending_approval -> activate` returned HTTP 409
  `INVALID_SOURCE_CANDIDATE_STATE`.
- [x] Explicit human approval used the formal API and recorded `approved_by=admin`
  and `approved_at=2026-08-14T06:01:58.993737Z`.
- [x] Formal activation created Source `46`, official/enabled at `jxt.sc.gov.cn`.
- [x] Column governance activated only SourceColumn `191` (`公告公示`,
  `#panel-20002 a[href]`), the sole `trial_crawled` column. Five `0/5` columns
  remain in discovery audit history and were not activated.
- [x] No automatic expansion: source-discovery automation is disabled, topics are
  empty, and no CrawlTask was created.
- [x] Final provider/governance status:
  `BRAVE_SEARCH_PROVIDER=PASS-LIVE`, `BRAVE_SSRF=PASS-LIVE`, official validation,
  column discovery, trial crawl, manual governance, and activation all
  `PASS-LIVE`; `BRAVE_SOURCE_DISCOVERY=PASS-LIVE`.
- [x] Core regression: documents `182`, approved `101`, rejected `35`, pending
  `46`, chunks `821`, Qdrant green/exact points `821`, and
  `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`.
- [x] Remote Rerank remains provider/full-RAG `PASS-LIVE`; Phase Z made no Cohere
  request.

## Phase W-X-Y closure gate (2026-08-14, latest authoritative checkpoint)

This section supersedes older Phase T-U provider checkboxes where they differ; the
older entries remain below as historical evidence.

- [x] Root cause of failing trace `f9a44597-a18e-46ae-8aa5-5d36632cddc1` is
  caller-side UTF-8 corruption: the persisted query contained 40 literal ASCII `?`
  characters. No backend validator or grounding rule was changed.
- [x] Supported official trace `70906f7f-648f-4356-a0ee-47829afae7c1`: Remote
  Rerank applied, Direct LLM answered, unchanged validation passed, and citation
  mapped to real chunk `0bf55b37-7bf1-5ce9-834a-f46754e84fec`, title, and URL.
- [x] Supported official trace `e0e57258-4d19-44a9-94d4-ea8430a6f2c4`: returned the supported September
  2023-March 2024 / April-June 2024 date answer and cited the same real official
  chunk.
- [x] Broad multi-fact trace `b48ca4d8-1f40-49c8-b98e-f4c057851963`: safely refused with
  `insufficient_evidence_relevance`.
- [x] No-evidence trace `47570efd-6352-4213-8abf-ce0fbc3408c7`: safely refused
  before the answer LLM.
- [x] `REMOTE_RERANK_PROVIDER=PASS-LIVE` and
  `REMOTE_RERANK_FULL_RAG=PASS-LIVE`: two supported cited answers plus two safe
  refusals, with unchanged evidence/relation/citation controls.
- [x] Local fake-IP DNS (`198.18.0.0/15`) root cause identified without weakening
  SSRF policy.
- [x] Secure fetch path: fail-closed DoH, validated-address connection pinning,
  original Host and TLS SNI, redirect revalidation, and IPv6 site-local rejection.
- [x] Only backend/worker/scheduler rebuilt and recreated; all three healthy;
  PostgreSQL/Redis/Qdrant/frontend/nginx and all volumes preserved.
- [x] Real Brave run 3/candidate 6 official validation:
  `https://jxt.sc.gov.cn/scjxt/index.shtml`, HTTP 200, exact HTTPS host, `.gov.cn`,
  official score 1.0.
- [x] Real column discovery: 12 columns.
- [ ] Trial/quality gate: 60 pages fetched, 0 relevant detail documents, all
  `NO_RELEVANT_DETAIL_DOCUMENTS`; quality 0.5 is below threshold 0.65.
- [x] Candidate 6 rejected/run 3 failed before approval. No approve, activate,
  Source, or CrawlTask action occurred.
- [x] `BRAVE_SEARCH_PROVIDER=PASS-LIVE`, `SSRF=PASS-LIVE`, official validation
  `PASS-LIVE`, and column discovery `PASS-LIVE`.
- [ ] Brave trial/quality is `FAIL-LIVE`; manual approval was not reached:
  `MANUAL_SOURCE_APPROVAL_REQUIRED=NO`.
- [x] Final read-only invariant re-audit: HTTP 8080 and system health are 200;
  dependencies are healthy; PostgreSQL has 182 documents, 101 approved, 35
  rejected, 46 pending manual review, and 821 chunks; Qdrant is green with 821
  exact points.
- [x] Targeted Phase W-X-Y regression: `127 passed`; scoped Ruff lint/format,
  Black, strict mypy, and `git diff --check` pass.
- [x] `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE` remains confirmed.

本文是部署到真实环境前的执行清单，不是模拟成功清单。最后审阅：2026-08-13。八个服务当前 healthy。Task 23 的真实 MIIT government/official 主链保持 `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5`；Phase A Evidence Sufficiency 已对“检索到无关 chunk”的场景取得 PASS-LIVE；Phase C multi-article canary、C1=10、C2=50 与 C3=100 已 PASS-LIVE。Phase K 的历史 P95 目标尚未达成，Phase L 生产工程仍为 PARTIAL，整体生产发布仍未接受。

## Phase N-Q historical gate (superseded by Phase AD, 2026-08-14)

### Phase T-U latest provider gates

- [x] Remote runtime provider is `remote`, model `rerank-v3.5`.
- [x] Five real Cohere requests: five applied, non-empty reranked results, finite
  `[0,1]` scores, zero provider errors.
- [x] No-evidence RAG regression: remote rerank applied, refusal true, citations 0,
  answer-LLM tokens 0.
- [ ] Supported RAG/citation regression: remote rerank and Direct LLM ran, but final
  Answer Validation returned `answer_contains_unsupported_relation`; citations 0.
- [x] Brave external search: two real calls; second call returned five candidates.
- [ ] Official validation/column/trial/quality: all five candidates hit
  `UnsafeUrlError` under the existing proxy/DNS SSRF boundary.
- [x] Governance preserved: pending approval 0, activated sources 0; no approve or
  activate action executed.
- [x] Core counts unchanged: 182 documents, 101 approved, 35 rejected, 46 pending,
  821 chunks and 821 Qdrant points.

### Phase S-V provider gate attempt

- [x] Host effective settings: Rerank `provider=remote`, model `rerank-v3.5`,
  configured true, failure policy open; Brave `provider=brave`, configured true.
- [ ] Runtime reload: blocked before execution by the local Docker approval service;
  running backend still reports rerank provider `none`/disabled.
- [ ] Remote Rerank Live: zero provider responses, zero applied remote reranks;
  restricted-network attempt returned `transport_error` and approved-network
  execution did not start. Do not count fail-open fusion as Live success.
- [ ] Brave Live: zero search calls and zero candidates; no manual approval gate was
  reached, and no source/trial result was fabricated.
- [x] Regression: 29 rerank/search tests and 19 source-discovery tests pass.
- [x] Invariants: health healthy; documents `182`, approved `101`, rejected `35`,
  pending `46`, chunks `821`, Qdrant exact points `821`.

- [x] Real PostgreSQL migration `0011_attachment_download_audit` is current and
  `alembic check` reports no drift.
- [x] Existing attachment rows have deterministic terminal states: `123 total / 0
  pending / 0 parsed / 77 failed / 46 unsupported`; failed/unsupported rows carry
  explicit error/reason fields.
- [ ] Attachment OCR is not live accepted: all 123 source records are URL-only,
  0 have local bytes, and the OCR-required outcome is `OCR_UNAVAILABLE`. Do not
  weaken SSRF protections or fabricate text.
- [x] Three-run real performance benchmark completed over the fixed two-case
  instrumentation set (one warm-up per case); overall P50 `734.236 ms` and P95
  `5121.708 ms` are persisted under `data/performance/`.
- [ ] `RAG_PERFORMANCE_P95` remains `PARTIAL` because P95 is not below 5000 ms and
  the quality guard is blocked by 0/100 human-verified cases.
- [x] Human-review workbook and strict dry-run importer exist; current dry-run is
  `REVIEWED=0`, `VERIFIED=0`, `PARTIAL_HUMAN_REVIEW`.
- [ ] Human evaluation remains `BLOCKED-HUMAN`; never create verified JSON or apply
  verdicts until a person reviews every row.
- [x] Backend regression from `backend/`: `399 passed`; application Ruff/format and
  mypy pass. Frontend audit is zero vulnerabilities; a fresh Vite/Compose process
  check was blocked by local spawn/named-pipe approval and is not claimed.
- [x] Core counts remain documents `182`, approved `101`, chunks `821`, Qdrant
  points `821`, and `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`.

## Phase K-L/M current status

- Phase K: `PERFORMANCE_PROFILED_LIVE`, `RAG_P95_LT_5000MS=FAIL-LIVE`. Historical trace stage split was incomplete; migration `0010_query_trace_stage_timings` now passes real PostgreSQL migration/no-drift and live supported/refusal trace persistence. `QUERY_TRACE_STAGE_TIMINGS=PASS-LIVE` without changing retrieval or grounding behavior.
- Phase L: `LOCAL-RUNTIME-VERIFIED / PRODUCTION-ENGINEERING-NOT-ACCEPTED`. See `DISASTER_RECOVERY_REPORT.md` and `SECURITY_READINESS_REPORT.md` for backup, restore, TLS, secrets, resource, logging, retention and alert blockers.
- Phase M: final acceptance audit complete. The local regression and evidence review are recorded below; unchecked external/production gates remain blockers. `PRODUCTION-READY` must not be inferred from code presence or fixture results.

## Phase M final gate (2026-08-13)

- [x] Knowledge-base closed loop remains `5/5 PASS-LIVE` with 100 official documents and 821 chunks/points.
- [x] Backend full regression: `370 passed`; Ruff and mypy pass (158 files).
- [x] SQLite migration round-trip through `0010_query_trace_stage_timings` and `alembic check` pass.
- [x] Ruff format check, frontend lint/type-check, Vitest `18/18`, Vite production build, Playwright `10 passed/1 expected skip`, and both npm audit modes (`0 vulnerabilities`) pass locally.
- [x] No credentials, active volumes, historical trust classifications or region audit values were exposed or rewritten.
- [x] Real PostgreSQL/backend rollout of migration `0010`: `PASS-LIVE`; supported and no-evidence requests persist non-empty, parseable, non-negative stage timings.
- [x] Runtime after the minimal backend-only rebuild: all 8 Compose services healthy; 8080 and dependency health return HTTP 200/healthy; PostgreSQL documents/chunks and Qdrant points remain `182/821/821`.
- [ ] Remote Rerank: `BLOCKED-EXTERNAL-RERANK-KEY`.
- [ ] Brave source discovery: `BLOCKED-EXTERNAL-BRAVE-KEY`.
- [ ] Human-verified representative evaluation: `BLOCKED-HUMAN-EVAL-REVIEW`.
- [ ] Production disaster recovery and security hardening: `BLOCKED-PRODUCTION`.
- [x] Black: `PASS-LOCAL`; with an isolated workspace cache, `backend/app`, `backend/tests`, `backend/alembic` (219 files) and the two changed scripts are unchanged under Black 25.12.0. The check explicitly excludes caches, uploaded files, Docker data and generated artifacts.
- [ ] Git checkpoint: `BLOCKED-LOCAL-PERMISSION`; no `index.lock` or active Git process exists, but inherited `.git` deny ACLs prevent index writes. The single controlled staging attempt failed before staging; no lock was deleted and no permission was forced.

The project must remain `NOT PRODUCTION ACCEPTED` until unchecked gates have independently verifiable evidence. See [`FINAL_ACCEPTANCE_REPORT.md`](FINAL_ACCEPTANCE_REPORT.md).

## 当前 official-source 最后一关（PASS-LIVE）

当前合法判定是索引 hit metadata 中 `official_status` 忽略大小写后等于 `official`。`organization_type` 和域名只用于来源治理/人工核验，不参与 chat-time 判定；不要把 association 改成 government，不要关闭 `grounding_require_official_source`。

## Phase C C3 最终验收（2026-08-13）

本表只记录真实业务链结果；不得用 pending、fixture、Local provider 或直接数据库写入替代通过项。

| Gate | Expected | Actual | Status |
| --- | --- | --- | --- |
| C3 qualified corpus | 100 government/official docs, valid non-corrupt region | 100 docs, 31 source rows, 10 domains | PASS-LIVE |
| database totals | auditable persisted counts | current after Phase G: documents 182; approved 101; rejected 35; pending 46; tasks 221; reviews 296; lineage 1053 | PASS-LIVE |
| PostgreSQL/Qdrant | chunks equal direct exact points | 821 PostgreSQL chunks; Qdrant `odirag_chunks` green; exact count 821 | PASS-LIVE |
| deduplication | approved URL/content hash duplicates zero | 0 / 0 | PASS-LIVE |
| content and metadata | non-empty title/content, valid URL, region not null/`??`, indexed | all approved qualifying rows pass; word count 180–6408; zero approved docs without chunks | PASS-LIVE |
| idempotent reindex | no duplicate points; cache reuse | document 181 reindex: 4 chunks, 4 cache hits, 0 new embeddings; Qdrant remained 821 | PASS-LIVE |
| disk safety | stop if D: <50 GiB | D: 106.86 GiB free | PASS |
| attachments/OCR | parsed attachment text | 123 audited: 77 failed, 46 unsupported, 0 pending/parsed; one OCR failure | **NOT ACCEPTED** |

Tasks 210–221 initially failed together with `COZE_NETWORK_ERROR` after approximately 195 seconds. Serial retry recovered 210–218; 219–221 remain failed evidence and contributed no accepted documents. Source 39 retains a PowerShell 5.1 encoding error (`??`) as audit evidence and was excluded from the qualified count; it was not silently repaired. Sources 40–45 were verified in PostgreSQL with UTF-8 bytes before use.

The current Phase M live regression is independently verified: five real retrieval hits, Direct `gpt-4.1-mini`, one exact citation, and safe refusal for no-evidence/adversarial questions. Backend `370 passed`; Ruff, Ruff format, mypy and source-scoped Black passed; frontend lint/type-check/Vitest `18/18`/build passed; Playwright `10 passed, 1 skipped`; eight Compose services healthy; PostgreSQL accepting, Redis `PONG`, Qdrant healthz 200, and 8080/API health 200. Historical timeout wording below does not override the current Black `PASS-LOCAL` result.

已执行结果：

| Task | Official URL type | HTTP / provider | discovered / fetched / documents | accepted / rejected / pending / failed | task chunks / Qdrant points |
| --- | --- | --- | --- | --- | --- |
| 19 | 四川省科技厅静态政策栏目 | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 20 | 工信部通知栏目 | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 21 | 中国政府网最新政策栏目 | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 22 | 工信部真实正文 URL | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 23 | 同一工信部真实正文 URL，Coze 重新发布后 | 200 / `completed` | 1 / 1 / 1 | 1 / 0 / 0 / 0 | 6 / 6 |

Tasks 19-22 是重新发布前的历史失败证据。Task 23 raw/normalized 已持久化并由当前 Pydantic Schema 重新解析通过；文章 1、content length 2,614、HTML、`needs_ocr=false`、quality 0.95、government/official。Document 6 已人工 approved，生成 6 stable chunks/points，并完成正式 cited answer。

Coze 重新发布后的精确重跑入口（不输出 token/password）：

~~~powershell
$ErrorActionPreference = 'Stop'
$pairs = @{}
Get-Content .env | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
    $key, $value = $line.Split('=', 2)
    $pairs[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
  }
}
$loginBody = @{ username = $pairs.ODIRAG_ADMIN_USERNAME; password = $pairs.ODIRAG_ADMIN_PASSWORD } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/auth/login -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($loginBody))
$headers = @{ Authorization = "Bearer $($login.access_token)" }
$taskBody = @{ source_column_id = 9; task_type = 'full'; trigger_type = 'manual'; provider = 'coze'; provider_contract = 'batch_crawl'; contract_mode = 'batch_crawl'; max_pages = 1; max_articles = 5 } | ConvertTo-Json
$task = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/crawl-tasks -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($taskBody))
do {
  Start-Sleep -Seconds 5
  $task = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/crawl-tasks/$($task.id)" -Headers $headers
} while ($task.status -notin @('completed', 'partial_failed', 'failed', 'cancelled'))
if ($task.discovered_count -lt 1 -or $task.fetched_count -lt 1) { throw 'Coze official-source discovery still produced no articles' }
$results = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/crawl-tasks/$($task.id)/results" -Headers $headers
if (@($results).Count -lt 1) { throw 'No official document was persisted' }
~~~

Task 23 实际结果满足上述预期：discovered/fetched/documents 1/1/1；raw/normalized 存在；正文和真实元数据正确；人工 approved；6 chunks/6 task points；重复 reindex 6 cache hits/0 new embeddings 且 IDs 不变；Hybrid final hits 5；正式 `/api/chat` 非拒答、Direct token usage 3,339、citation 可追溯；独立零命中问题 `refusal=true`、0 citations。因此本检查点已写入 `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5`。

## Phase A Evidence Sufficiency（PASS-LIVE）

~~~powershell
docker compose run --rm --no-deps -e ODIRAG_RUN_MIGRATIONS=false -v D:\RAG\backend:/app/backend backend alembic check
docker compose run --rm --no-deps -e ODIRAG_RUN_MIGRATIONS=false -v D:\RAG\scripts:/app/scripts backend python /app/scripts/live_accept_evidence_sufficiency.py --base-url http://backend:8000/api
powershell -NoProfile -ExecutionPolicy Bypass -File D:\RAG\scripts\run_live_playwright.ps1
~~~

预期：Alembic 输出 `No new upgrade operations detected`；Live 脚本输出 `PASS-LIVE`，受支持问题的 Direct token/citation 大于零，非空无关检索与 cancellation/penalty/scope adversarial 问题的 candidates 大于零但 `refusal=true`、citations/token/cost 均为零；8080 Playwright 登录、官方问答、引用和监控页通过。2026-08-09 实际结果：supported trace `47c5b283-5e38-40f4-a7a3-1e684737671f`（5 hits、3,336 tokens、1 个真实 MIIT citation）；Mars/dinosaur trace `b38598b2-89a3-4cd2-92b3-ee733b013f71`；cancellation/original-numeric-penalty/scope traces `e07f742b-fa91-4e52-bd5f-cd7de42d96fc`、`7b1434b2-a01f-4005-872c-bf98ce314667`、`99cba6de-53db-42f1-8fbf-e127f9858fd9`。四个拒答均为 5 candidates、0 citations/tokens/cost。后端 324 passed；fixture Playwright 9 passed/1 skipped，live-stack 1 passed。

评测期望：citation precision/recall 的分母排除 `should_refuse=true` 的正确拒答样本；9 个正确拒答加 1 个错误 citation 的回归结果必须为 precision/recall `0/0`，不能是 `0.9/0.9`。`answer_grounding_rate` 必须来自 citation-bound claim 检查，不得直接使用被测 ChatService 的 `answer_support_validated` 自证。

## 证据规则

- PASS-LIVE：命令在目标 PostgreSQL/Redis/Qdrant/worker/provider/入口上实际执行，输出与预期一致。
- PASS-FIXTURE：只使用 SQLite、内存实现、确定性模型、MockTransport 或 Playwright route fixture；不能替代 live acceptance。
- BLOCKED：前置依赖或凭据缺失，不能推断成功。
- FAIL：命令已执行但结果不符合预期。

每项保存命令、UTC 时间、镜像 digest、配置版本、脱敏日志和结果。不要把 token、密码、Authorization header 或完整响应中的敏感字段提交到仓库。

## 0. 前置准备

在部署机安装 Docker Engine、Docker Compose v2、PowerShell 7、Python 3.12+、Node 22+ 和 psql（或使用容器内客户端）。将 .env.example 复制为 .env，替换所有开发默认值；生产环境必须使用 ODIRAG_ENVIRONMENT=production、随机的 ODIRAG_JWT_SECRET_KEY、ODIRAG_ADMIN_PASSWORD_HASH，不能设置明文 ODIRAG_ADMIN_PASSWORD。

~~~powershell
$ErrorActionPreference = 'Stop'
docker version
docker compose version
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose model is invalid' }
~~~

预期：Docker/Compose 版本可打印，docker compose config --quiet 无输出且退出码为 0。若 Compose 输出 warning，先修复变量或镜像配置再继续。

## 1. 启动完整栈

~~~powershell
docker compose build --pull --no-cache backend
docker compose build --pull --no-cache frontend
docker compose --profile ui --profile async up -d --no-build
docker compose ps --all
docker compose ps --format json | ConvertFrom-Json | Format-Table
docker compose images
docker compose ps --all > acceptance-compose-ps.txt
docker compose logs --no-color --since 10m > acceptance-compose-logs.txt
~~~

预期服务：postgres、redis、qdrant、backend、frontend、nginx、worker、scheduler 均为 running，并且 health 为 healthy。保存镜像 tag/digest、Compose 状态和最近 10 分钟脱敏日志。

## 2. PostgreSQL

~~~powershell
$pgUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
$pgDb = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
docker compose exec -T postgres pg_isready -U $pgUser -d $pgDb
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -Atc "SELECT current_database(), current_user"
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "SELECT count(*) AS sources FROM sources; SELECT count(*) AS documents FROM documents;"
~~~

预期：pg_isready 报 accepting connections；SQL 成功并返回数据库/用户；业务查询返回整数且无 relation/permission 错误。继续核对 Phase 16 表：

~~~powershell
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -Atc "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('source_discovery_runs','source_candidates','source_candidate_columns','source_discovery_events') ORDER BY tablename"
~~~

预期恰好返回四张表。若使用受管 PostgreSQL，另执行备份、恢复和连接池耗尽演练；这些不由 Compose 默认配置证明。

### PostgreSQL 备份/恢复演练（独立临时容器与临时卷）

以下 PowerShell 5.1 兼容脚本只从业务库执行 `pg_dump` 和只读计数。恢复写入发生在
`--network none` 的临时 PostgreSQL 容器及唯一临时卷中，不写入项目 `postgres-data`。
`finally` 只清理本次运行精确命名并带标签的临时资源；宿主备份和 SHA-256 留档：

~~~powershell
$ErrorActionPreference = 'Stop'
function Assert-Exit([string]$step) {
  if ($LASTEXITCODE -ne 0) { throw "$step failed, exit=$LASTEXITCODE" }
}

$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$token = "$stamp-$PID"
if ($token -notmatch '^\d{14}-\d+$') { throw 'Unsafe run token' }

$artifactDir = Join-Path $PWD "data\reports\acceptance\$token"
$sourceDump = "/tmp/odirag-acceptance-$token.dump"
$dumpPath = Join-Path $artifactDir "odirag-acceptance-$token.dump"
$restoreContainer = "odirag-pg-restore-$token"
$restoreVolume = "odirag-pg-restore-$token"
$restoreDb = "odirag_acceptance_restore_${stamp}_$PID"
if ($sourceDump -notmatch '^/tmp/odirag-acceptance-\d{14}-\d+\.dump$' -or
    $restoreContainer -notmatch '^odirag-pg-restore-\d{14}-\d+$' -or
    $restoreVolume -notmatch '^odirag-pg-restore-\d{14}-\d+$' -or
    $restoreDb -notmatch '^odirag_acceptance_restore_\d{14}_\d+$') {
  throw 'Unsafe restore resource name'
}

$pgUser = (@(docker compose exec -T postgres printenv POSTGRES_USER) -join '').Trim()
Assert-Exit 'read POSTGRES_USER'
$pgDb = (@(docker compose exec -T postgres printenv POSTGRES_DB) -join '').Trim()
Assert-Exit 'read POSTGRES_DB'
$pgContainer = (@(docker compose ps -q postgres) -join '').Trim()
Assert-Exit 'locate postgres container'
$pgImageId = (@(docker inspect --format '{{.Image}}' $pgContainer) -join '').Trim()
Assert-Exit 'inspect postgres image'
if ($pgImageId -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Invalid PostgreSQL image ID' }

if (@(docker container ls -a --format '{{.Names}}') -contains $restoreContainer) {
  throw "Container already exists: $restoreContainer"
}
Assert-Exit 'list containers'
if (@(docker volume ls --format '{{.Name}}') -contains $restoreVolume) {
  throw "Volume already exists: $restoreVolume"
}
Assert-Exit 'list volumes'

New-Item -ItemType Directory -Path $artifactDir | Out-Null
$sourceDumpCreated = $false
$containerCreated = $false
$volumeCreated = $false
$ok = $false

try {
  docker compose exec -T postgres pg_dump -U $pgUser -d $pgDb -Fc `
    --no-owner --no-privileges -f $sourceDump
  Assert-Exit 'pg_dump'
  $sourceDumpCreated = $true

  docker compose cp "postgres:$sourceDump" $dumpPath
  Assert-Exit 'copy dump'
  $dumpFile = Get-Item -LiteralPath $dumpPath
  if ($dumpFile.Length -lt 1024) { throw 'Dump is implausibly small' }
  Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath

  $countSql = "SELECT 'sources',count(*) FROM sources UNION ALL SELECT 'source_columns',count(*) FROM source_columns UNION ALL SELECT 'source_discovery_runs',count(*) FROM source_discovery_runs UNION ALL SELECT 'source_candidates',count(*) FROM source_candidates UNION ALL SELECT 'source_candidate_columns',count(*) FROM source_candidate_columns UNION ALL SELECT 'source_discovery_events',count(*) FROM source_discovery_events UNION ALL SELECT 'crawl_tasks',count(*) FROM crawl_tasks UNION ALL SELECT 'coze_invocations',count(*) FROM coze_invocations UNION ALL SELECT 'documents',count(*) FROM documents ORDER BY 1"
  $sourceCounts = @(docker compose exec -T postgres psql -U $pgUser -d $pgDb -At -v ON_ERROR_STOP=1 -c $countSql)
  Assert-Exit 'source counts'

  docker volume create --label "odirag.acceptance.run=$token" $restoreVolume | Out-Null
  Assert-Exit 'create isolated volume'
  $volumeCreated = $true

  $tempPassword = [guid]::NewGuid().ToString('N')
  $runArgs = @(
    'run','-d','--name',$restoreContainer,'--network','none',
    '--label',"odirag.acceptance.run=$token",
    '--mount',"type=volume,source=$restoreVolume,target=/var/lib/postgresql/data",
    '--env','POSTGRES_USER=restore_admin','--env',"POSTGRES_PASSWORD=$tempPassword",
    '--env',"POSTGRES_DB=$restoreDb",$pgImageId
  )
  & docker @runArgs | Out-Null
  Assert-Exit 'start isolated PostgreSQL'
  $containerCreated = $true

  $ready = $false
  for ($i = 0; $i -lt 60; $i++) {
    docker exec $restoreContainer pg_isready -U restore_admin -d $restoreDb *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw 'Isolated PostgreSQL did not become ready' }

  docker cp $dumpPath "${restoreContainer}:/tmp/source.dump"
  Assert-Exit 'copy dump to isolated PostgreSQL'
  docker exec $restoreContainer pg_restore -U restore_admin -d $restoreDb `
    --exit-on-error --no-owner --no-privileges /tmp/source.dump
  Assert-Exit 'isolated pg_restore'

  $restoreCounts = @(docker exec $restoreContainer psql -U restore_admin -d $restoreDb -At -v ON_ERROR_STOP=1 -c $countSql)
  Assert-Exit 'restored counts'
  if (Compare-Object $sourceCounts $restoreCounts) { throw 'Restored counts differ' }
  $ok = $true
}
finally {
  if ($containerCreated) { docker rm -f $restoreContainer | Out-Null }
  if ($volumeCreated) { docker volume rm $restoreVolume | Out-Null }
  if ($sourceDumpCreated) { docker compose exec -T postgres rm -f $sourceDump | Out-Null }
}
if (-not $ok) { throw 'Restore acceptance failed' }
~~~

预期：`pg_dump`、隔离 `pg_restore`、九张关键表计数对比全部退出 0；备份文件及
SHA-256 留档；按 `odirag.acceptance.run=$token` 查询不到残留容器或卷。当前仓库没有自动
备份调度器，目标环境仍需验证加密、保留策略、RPO/RTO 和生产数据量。

## 3. Alembic

~~~powershell
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
docker compose exec -T backend alembic check
~~~

历史 Phase B 预期：当时 current 和 heads 都指向 `0008_rerank_observability` 并标记 (head)，且 alembic check 退出码为 0。该历史检查点已由本轮真实 PostgreSQL `0010_query_trace_stage_timings (head)` 和 no-drift 结果取代。

使用专用验收数据库验证全链路迁移（不要在生产业务库直接 downgrade）：

~~~powershell
$acceptanceDb = 'odirag_acceptance_migration'
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $acceptanceDb;"
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "CREATE DATABASE $acceptanceDb;"
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic upgrade head'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic downgrade 0003_crawl_reliability'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic upgrade head'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic current'
~~~

预期：upgrade、downgrade、再 upgrade 都退出 0，最终 `0008_rerank_observability (head)`。完成后清理专用数据库或按组织保留审计证据。

## 4. Redis

~~~powershell
docker compose exec -T redis redis-cli ping
docker compose exec -T redis redis-cli SET odirag:acceptance:probe ok EX 60
docker compose exec -T redis redis-cli GET odirag:acceptance:probe
docker compose exec -T redis redis-cli DEL odirag:acceptance:probe
~~~

预期依次为 PONG、OK、ok、1。随后从 backend 容器确认应用 Redis URL 可达：

~~~powershell
docker compose exec -T backend python -c "import asyncio,os; from redis.asyncio import Redis; print(asyncio.run(Redis.from_url(os.environ['ODIRAG_REDIS_URL']).ping()))"
~~~

预期打印 True。继续验证应用使用共享 Redis 限流器，而不是进程内 fallback：

~~~powershell
docker compose exec -T backend python -c "from app.config import Settings; print(Settings().rate_limit_backend)"
docker compose exec -T backend python -c "from app.config import Settings; s=Settings(); print(s.trusted_proxy_ips)"
$base = 'http://127.0.0.1:8080'
curl.exe -sS -D acceptance-rate-limit-headers.txt -o NUL "$base/api/system/health"
Get-Content acceptance-rate-limit-headers.txt | Select-String 'x-ratelimit-limit|x-ratelimit-remaining|x-ratelimit-reset'
docker compose exec -T redis redis-cli --scan --pattern 'odirag:ratelimit:*'
$spoof = '203.0.113.250'
curl.exe -sS -H "X-Forwarded-For: $spoof" -o NUL "$base/api/system/health"
if (@(docker compose exec -T redis redis-cli --scan --pattern "*$spoof*").Count -ne 0) {
  throw 'Client-supplied X-Forwarded-For created a limiter bucket'
}
~~~

预期第一条为 `redis`，响应同时包含三类 `X-RateLimit-*` header，Redis scan 至少返回一个
`odirag:ratelimit:<window>:<bucket>:<profile>:<identity>` key。staging/production 配置若选择 `memory`
必须在启动时失败，不能以单实例假设绕过共享限流。

只在隔离验收环境执行 fail-closed 演练：停止 Redis 后请求受限 API，预期 HTTP 503 且错误码为
`RATE_LIMIT_BACKEND_UNAVAILABLE`；恢复 Redis 后请求恢复成功。不要在承载业务流量的生产实例直接停止 Redis。

还需确认 broker、result backend、embedding cache 使用隔离 Redis DB/ACL；一次 PING 和一次计数写入仍不证明故障转移或持久化恢复。

## 5. Qdrant

~~~powershell
$qdrant = 'http://127.0.0.1:6333'
Invoke-RestMethod "$qdrant/healthz"
Invoke-RestMethod "$qdrant/collections" | ConvertTo-Json -Depth 8
~~~

预期：health endpoint 返回成功；collections 响应可解析。完成一次真实 reindex 后检查：

~~~powershell
$collection = docker compose exec -T backend python -c "from app.config import get_settings; print(get_settings().qdrant_collection)"
$collection = $collection.Trim()
$info = Invoke-RestMethod "$qdrant/collections/$collection"
$info.result.status
$info.result.config.params.vectors.size
$info.result.points_count
~~~

预期：status 为 green（或目标版本等价健康状态），vector size 等于 ODIRAG_EMBEDDING_DIMENSIONS，points_count 与已索引 chunk 数一致且大于零。删除/重解析后再次检查 points_count 下降，不能只检查数据库行。

## 6. Worker

~~~powershell
docker compose exec -T worker celery -A app.tasks.celery_app:celery_app inspect ping --timeout 10
docker compose exec -T backend python -c "from app.tasks.celery_app import ping; r=ping.delay(); print(r.get(timeout=30, propagate=True))"
~~~

预期：inspect 输出 worker 的 pong；第二条输出 {'status': 'healthy', 'service': 'odirag-worker'}（或等价 JSON），证明任务确实经过 broker 被 worker 执行。再创建一个 queued crawl task 和一个 queued source-discovery run，确认状态从 pending 到 running 再到完成/审批等待，并在 broker 不可用时确认任务被持久化为 failed 且可 retry。

用一个已启用、已通过来源验收的栏目执行真实 queued crawl（不要把 `inline` 当作 worker 证据）：

~~~powershell
$apiBase = 'http://127.0.0.1:8080/api'
$columnId = <真实已启用栏目ID>
$queued = Invoke-RestMethod "$apiBase/crawl-tasks" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  source_column_id = $columnId
  task_type = 'incremental'
  trigger_type = 'manual'
  execution_mode = 'queued'
  provider = 'coze'
  contract_mode = 'batch_crawl'
  provider_contract = 'batch_crawl'
  max_articles = 1
  max_pages = 1
} | ConvertTo-Json)
$deadline = (Get-Date).AddMinutes(5)
do {
  Start-Sleep -Seconds 2
  $queued = Invoke-RestMethod "$apiBase/crawl-tasks/$($queued.id)" -Headers $headers
} while ($queued.status -in @('pending','queued','running','calling_coze','coze_running','normalizing','saving_documents') -and (Get-Date) -lt $deadline)
if ($queued.status -notin @('completed','waiting_review','partial_failed')) {
  throw "Queued crawl did not reach an accepted terminal state: $($queued.status)"
}
if ($queued.provider -ne 'coze' -or $queued.contract_mode -ne 'batch_crawl') { throw 'Worker used the wrong provider contract' }
~~~

预期：任务曾进入 queued/running，最终为 `completed`、`waiting_review` 或明确的 `partial_failed`；`provider` 为 `coze`、`contract_mode` 为 `batch_crawl`，并且 invocation、失败 URL 和持久化计数可由后续接口核对。

## 7. Scheduler

~~~powershell
docker compose exec -T scheduler sh -c 'test -s /tmp/celerybeat.pid'
docker compose logs --no-color --since 5m scheduler
~~~

预期：PID 文件存在且进程仍在；日志包含 beat 启动和调度信息。至少观察到 refresh-monitoring-alerts（300 秒）和 recover-crawl-tasks（60 秒）各执行一次，不能只凭容器 running 判定 scheduler 有效。

## 8. Nginx 与前端

~~~powershell
$base = 'http://127.0.0.1:8080'
(Invoke-WebRequest "$base/healthz").StatusCode
(Invoke-WebRequest "$base/").StatusCode
(Invoke-WebRequest "$base/api/system/health").StatusCode
~~~

预期三个状态码都是 200；/healthz body 为 ok，/ 返回前端 HTML，health JSON 的 database、redis、qdrant 状态与目标环境事实一致，不得被 demo 值覆盖。保存响应头并确认 X-Content-Type-Options、X-Frame-Options、Referrer-Policy 存在。

验证滚动替换不会让 Nginx 固定旧 Docker IP（会短暂重建单个 backend，只在验收环境执行）：

~~~powershell
docker compose exec -T nginx nginx -t
docker compose up -d --no-deps --force-recreate backend
docker compose ps backend nginx
1..15 | ForEach-Object {
  (Invoke-WebRequest "$base/api/system/health" -TimeoutSec 5).StatusCode
  Start-Sleep -Seconds 2
}
~~~

预期：`nginx -t` 成功，backend 和 Nginx 都恢复 healthy；Nginx 无需重启，15 次代理请求全部为 200。任何持续 502 或 `connect() failed` 都说明服务名仍被固定到旧容器 IP，不能通过该门禁。

容器用户边界也要留证：

~~~powershell
docker compose exec -T backend id -u
docker compose exec -T frontend id -u
docker compose exec -T nginx id -u
~~~

预期：backend 输出 `10001`。当前 frontend/reverse-proxy Nginx 基础镜像的 master 进程可能输出 `0`（worker 会降权）；这只能记录为残余 hardening 风险，不能把它写成“所有容器均 non-root”或生产通过。

在 frontend/ 执行：

~~~powershell
npm ci
npx playwright install chromium
npm run lint
npm run type-check
npm test
npm run build
npm audit --omit=dev
npm audit
npm ls --all
npm run test:e2e
~~~

预期：lint/type-check/test/build 全部退出 0；两次 audit 均为 0 high/critical（发布门禁建议所有级别均为 0），依赖树无 invalid/extraneous 必需依赖；fixture Playwright 用例全部通过，live-stack.spec.ts 在未设置 E2E_LIVE=1 时明确 skipped。fixture 通过只证明浏览器 API 契约，不证明生产依赖。

在仓库根目录执行 Python 依赖一致性检查。先单独构建两个 builder stage，再对 Compose
使用的全部运行时镜像与 builder 镜像生成 SBOM 和 critical/high CVE 报告：

~~~powershell
pip --python .\backend\.venv check
docker build --pull --no-cache --file Dockerfile.backend --target builder --tag odirag/backend-builder:acceptance .
docker build --pull --no-cache --file Dockerfile.frontend --target builder --tag odirag/frontend-builder:acceptance .
$scanDir = Join-Path $PWD 'artifacts\acceptance\image-scan'
New-Item -ItemType Directory -Force -Path $scanDir | Out-Null
$images = @(
  @(docker compose config --images)
  'odirag/backend-builder:acceptance'
  'odirag/frontend-builder:acceptance'
) | Sort-Object -Unique
foreach ($image in $images) {
  $safeName = $image -replace '[^A-Za-z0-9._-]', '_'
  $digestPath = Join-Path $scanDir "$safeName.digest.txt"
  docker image inspect $image --format '{{.Id}} {{json .RepoDigests}}' |
    Set-Content -LiteralPath $digestPath
  if (-not (Test-Path -LiteralPath $digestPath) -or (Get-Item -LiteralPath $digestPath).Length -lt 20) {
    throw "Image ID/digest evidence is missing for $image"
  }
  $sbomPath = Join-Path $scanDir "$safeName.spdx.json"
  docker scout sbom "local://$image" --format spdx `
    --output $sbomPath
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sbomPath) -or (Get-Item -LiteralPath $sbomPath).Length -lt 100) {
    throw "SBOM generation failed or produced an empty report for $image"
  }
  $cvePath = Join-Path $scanDir "$safeName.cves.md"
  docker scout cves "local://$image" --multi-stage --only-severity critical,high `
    --format markdown --output $cvePath --exit-code
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $cvePath) -or (Get-Item -LiteralPath $cvePath).Length -lt 1) {
    throw "Unapproved critical/high CVE or scan failure: $image"
  }
}
Get-ChildItem -LiteralPath $scanDir | Select-Object Name,Length
~~~

预期：pip 报告 `No broken requirements found`；backend、frontend、PostgreSQL、Redis、Qdrant、
reverse-proxy Nginx 以及 Python/Node builder 全部产生非空 SPDX SBOM、镜像 ID/digest 记录和 CVE
报告，且没有未批准的 critical/high CVE。`local://` 确保扫描本机刚构建或刚拉取的镜像，而不是
同名 registry 镜像。发布到 registry 后还必须把不可变 RepoDigest 写入部署清单；只有本地 image ID
不能满足发布 provenance 门禁。若扫描器需要联网更新漏洞库，必须保留扫描时间、数据库版本、镜像
digest 和例外审批，不能以“命令不可用”记为通过。

真实栈浏览器门禁：

~~~powershell
$env:E2E_LIVE = '1'
$env:E2E_BASE_URL = 'https://<real-odirag-host>'
$env:E2E_USERNAME = '<acceptance-user>'
$env:E2E_PASSWORD = '<acceptance-password>'
$env:E2E_QUERY = '企业研发投入有哪些支持措施？'
npm run test:e2e -- e2e/live-stack.spec.ts
~~~

预期：live 用例通过且没有 request interception；登录、来源、文档、带真实引用的聊天和监控均可达。失败时保留 trace，不要改成 fixture 以“修复”结果。

## 9. Auth 与核心 API 烟测

~~~powershell
$login = Invoke-RestMethod "$base/api/auth/login" -Method Post -ContentType 'application/json' -Body (@{ username = $env:E2E_USERNAME; password = $env:E2E_PASSWORD } | ConvertTo-Json)
$token = $login.access_token
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "$base/api/auth/me" -Headers $headers
Invoke-RestMethod "$base/api/sources" -Headers $headers
Invoke-RestMethod "$base/api/documents?limit=1" -Headers $headers
~~~

预期：login 返回 access/refresh token；me 返回当前管理员；sources/documents 返回真实数据库数据。不要在终端或日志打印 $token。

## 10. Coze

先在受控 shell 注入真实凭据，重启 backend；不要在仓库 .env.example 填入 token：

~~~powershell
$env:ODIRAG_LLM_PROVIDER = 'coze'
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:ODIRAG_COZE_BASE_URL = 'https://api.coze.com'
$env:COZE_API_TOKEN = '<real-token>'
$env:ODIRAG_COZE_BOT_ID = '<real-bot-id>'
docker compose up -d --force-recreate backend worker
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.coze_base_url, bool(s.coze_api_token), s.coze_bot_id)"
~~~

用一个真实待审核文档执行 POST /api/reviews/{document_id}/run，再执行 POST /api/chat。预期：Coze 返回符合 Pydantic 严格 JSON schema 的真实 review/answer，chat trace 的 model_name 为配置模型，引用仍来自已存储 chunk；缺 token 时必须是结构化 503，不能返回模拟答案。Coze Chat v3 的异步/消息读取语义必须以目标账户实际响应确认；当前适配器只做了协议夹具测试，未宣称 live 通过。参考：[Coze Chat v3](https://www.coze.com/open/docs/developer_guides/chat_v3)。

### Coze 栏目批量抓取部署

在本机未提交的 `.env` 中配置 `COZE_ENABLED=true`、`COZE_BATCH_API_URL`、
`COZE_API_TOKEN`、`COZE_DEFAULT_CONTRACT=batch_crawl`、`COZE_TIMEOUT_SECONDS=90` 和
`COZE_MAX_RETRIES=2`。旧单篇部署如需验证，使用独立的 `COZE_LEGACY_API_URL`；不要增加
`workflow_id` 或 Coze 远端轮询配置。然后执行：

2026-08-06 本机 live diagnostic：URL 与 Token 均只在未提交的 `.env` 中，三个消费服务确认
`enabled=true`、`batch_workflow_configured=true`、`token_configured=true`。task 4 证明部署入口要求
string `task_id`；task 5 证明 `coze.site/run` 返回 `run_id + batch_result` 外层；task 6 在两项修复后
HTTP 200、invocation completed、raw/normalized response 均持久化。其业务结果仍为 `NO_ARTICLES`、
0 discovered/fetched/documents/chunks/Qdrant points，故状态只能是 PARTIAL/LIVE-DIAGNOSTIC，不能算
真实内容验收通过。2026-08-07 Docker Desktop/Engine 已恢复，八服务 healthy，最终状态修复镜像已 rollout。

2026-08-07 task 7 真实执行记录（不输出 URL、Token 或 Authorization）：HTTP 200，invocation
`completed`，持久化 task `status=completed`、`provider_status=no_articles`，所有发现/抓取/成功/文档/
chunk/Qdrant point 计数均为 0；脚本结果为 `status=batch_result_empty`、exit code 1。该结果验证
鉴权、transport、raw/normalized 持久化和 no-articles 终态语义，但对已知存在内容的动态 SPA 属于
内容验收 FAIL，不得标为 `live_batch_verified`。

2026-08-07 新部署后的 task 8 真实执行记录（同样不记录部署 URL、Token、Authorization 或正文）：
HTTP 200、invocation `completed`、attempts `1`、retries `0`、duration `4141 ms`；normalized
`task_id` 为 string `"8"`，`workflow_version=batch_crawl-v1`。worker 正常结束异步执行，但业务任务
持久化为 `status=partial_failed`、`provider_status=partial_failed`，没有 provider error。statistics
只有 `pages_visited=1`；discovered/fetched/accepted/rejected/pending/failed、persisted failures、documents、
chunks 和 Qdrant points 均为 0。warnings 包含 `SPA_API_NOT_DISCOVERED`，并明确说明只取得基础 HTML、
未发现 API。验收脚本仍返回 `status=batch_result_empty`、exit code 1。

独立来源证据：`https://scsia.org/portal/news/264?pageNum=1&pageSize=5` 返回 HTTP 200 JSON、
`total=69`、五行，首行 ID `7587`；`https://scsia.org/portal/new/7587` 返回 data，`newsContent`
长度为 995。这里只保存状态、结构、ID 和长度，不保存正文。PostgreSQL 对 task 8 为 1 invocation、
0 documents、0 chunks；Qdrant collection 数为 0。监控打开 `high_failure_rate` high/open 告警，
observed `0.4` 超过 threshold `0.2`；相关回归 `49 passed`。这些仍是失败诊断证据。

2026-08-07 task 9 历史 bounded crawl checkpoint（不记录部署 URL、Token、Authorization、凭据或正文）：

- bounded 参数为 `max_pages=1`、`max_articles=5`；task/current stage/provider status 均为 `completed`，provider error 为 null；
- invocation HTTP 200/completed、attempts 1、retries 0、duration 22,757 ms；`raw_response_json=true`、`normalized=true`，normalized `task_id` 是 string `"9"`；
- 在当前 backend 容器中从 PostgreSQL 读取 raw response，再用 `parse_batch_crawl_response` 校验，Pydantic schema passed，articles/discovered/fetched 均为 5；
- accepted 0、rejected 5、pending 0、failed 0、provider failed URLs 0；task、normalized 和 persisted results 决策一致；
- PostgreSQL 为 5 documents、5 lineage、0 chunks、1 invocation；Qdrant 为 0 collections/points。

首篇元数据：标题“关于公布四川省2026年第六批软件企业及软件产品评估结果的通知”，URL
`https://www.scsia.org/portal/new/7587`，content length 0、needs OCR、image extraction、9 images、
decision rejected、index pending。五篇中三篇 image-only/needs-OCR/content length 0，另两篇 content length
349/203，全部 rejected。抓取层因此是 PASS-LIVE，但 OCR、正文可用性、质量复核、chunking、indexing 和
cited-answer 均不是 PASS-LIVE。

`embedding_provider=remote` 且 key 未配置，但 embedding 未参与本次 crawl；task 9 completed 且 failed 0，
不得据此把抓取判为失败。`live_accept_coze_batch.py` 在任务完成后读取 acceptance-summary 时收到 HTTP 503
`PROVIDER_UNAVAILABLE`，根因是不存在的 `odirag_chunks` collection count 在 Qdrant 返回 404；另有
qdrant-client 1.19/server 1.14 compatibility warning。两项均为后续本地修复，不撤销 task 9 抓取层 PASS-LIVE。

2026-08-08 当前证据替代上述 task 9 下游阻塞：task 13 保留为 Coze HTTP 200 后
`TASK_STATE_CHANGED` 的历史竞态失败；修复 source-column/row locking、queued→running 状态处理、
`image_ocr` schema、重复 URL 版本刷新和人工审核幂等后，task 14 成功。

Task 14 (`max_pages=1`, `max_articles=5`) 的 task/current stage/provider status 均 completed、provider error null；Coze
HTTP 200/completed、1 attempt/0 retries，raw/normalized persisted，strict BatchCrawlResult passed。
统计为 5 discovered/fetched/docs、1 accepted、4 rejected、0 pending、0 failed。五篇元数据依次为：

- length 0 / image / needs OCR / `OCR_FAILED` / rejected；
- length 0 / image / needs OCR / `OCR_FAILED` / rejected；
- length 5,358 / image_ocr / needs OCR false / `ocr_performed` / accepted / score 70；
- length 349 / html / rejected / score 0；
- length 203 / html / rejected / score 10。

Document 3 version history：v1 length 0/image/rejected/score 0 → v2 length 5,358/image_ocr/accepted/
score 0.70。现有 `POST /reviews/3/approve` 成功后文档为 approved，task 14 completed、pending 0。
acceptance-summary 的空状态曾真实返回 HTTP 200、`collection_exists=false`、points 0；索引后当前状态
为 HTTP 200、5 documents、8 chunks、`collection_exists=true`、8 points，并与 Qdrant REST 一致。

两次 pre-credential reindex 与一次 malformed-credential HTTP 401 保留为历史失败。修正 credential 后，
真实 remote `text-embedding-3-small`/1536 reindex 返回 HTTP 200、8 chunks、8 embeddings。Qdrant
直接查询为 1 collection/8 points。初次直查发现 payload 没有显式 `chunk_id`；适配器已补齐并测试，
第二次 reindex 原地回填，8 cache hits/0 embeddings，前后 point ID 集合哈希相同，全部 8 payload 合格。
真实 hybrid 检索返回 BM25/vector/fusion 8/8/8 和 5 final hits。当前 answer provider 是 `llm`，
LLM provider direct、model `gpt-4.1-mini`，密钥配置布尔值为 true；Direct 严格 AnswerResult provider 调用已执行。正式 `/api/chat` 因现有检索 hit 全部属于 association 而在模型前被 `official_source_required` 拒绝。

先设置 `ODIRAG_SOURCE_COLUMN_ID` 为一个已人工批准并启用的真实栏目 ID；以下命令会在变量为空时立即失败：

~~~powershell
if ([string]::IsNullOrWhiteSpace($env:ODIRAG_SOURCE_COLUMN_ID)) {
  throw 'ODIRAG_SOURCE_COLUMN_ID must reference a real enabled source column'
}
docker compose build backend
docker compose build frontend
docker compose --profile async --profile ui up -d --no-build
python scripts/live_accept_coze_batch.py --source-column-id $env:ODIRAG_SOURCE_COLUMN_ID
~~~

预期：脚本通过认证 API 创建真实 queued Coze/batch_crawl 任务，固定 `max_articles=5`、`max_pages=1`，
worker 完成一次 `batch_crawl` invocation；退出码为 0，单行 JSON 中
`status=live_batch_verified`，并给出 `success_count`、`accepted_count`、`rejected_count`、
`pending_review_count`、`failed_count`、`database_document_count`、`chunk_count` 和
`qdrant_point_count`。后四项来自任务持久化结果和 Qdrant `count(exact=true)`，不能用数据库
`index_status` 冒充。脚本不输出 token、部署 URL、header 或 raw response。未配置新批量 URL 时退出码必须为 2，
`status=batch_workflow_not_published`；这不是 Live 成功。节点级施工步骤和十组控制台用例见
`docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md`。

Task 9 的 summary 503 保留为历史证据。Task 14 已同时验证两种状态：索引前空 collection 返回 HTTP 200、
`collection_exists=false`、`qdrant_point_count=0`；真实 reindex 后返回 HTTP 200、
`collection_exists=true`、`qdrant_point_count=8`、`chunk_count=8`，并与 Qdrant REST 直查一致。

对已知存在文章的动态页面，`NO_ARTICLES`、0 discovered、0 persisted documents 或 0 Qdrant
points 均为 FAIL。HTTP 200 和 invocation `completed` 只证明鉴权与 transport，不证明文章发现、
正文抽取、质量判断、持久化或索引成功。动态 HTML 无链接时工作流必须报告
`DYNAMIC_CONTENT_UNSUPPORTED`，不得用 `NO_ARTICLES` 掩盖能力缺口。

栏目任务只能使用 `batch_crawl`。向 `POST /api/crawl-tasks` 提交
`provider=coze, contract_mode=legacy_single_article` 的预期结果是 HTTP 422、错误码
`COZE_LEGACY_SINGLE_ARTICLE_ONLY`；旧单篇部署只通过来源连通性/单篇兼容回归验证，不能创建栏目任务，
也不能用于证明批量抓取成功。

## 11. Embedding provider

~~~powershell
$env:ODIRAG_EMBEDDING_API_KEY = '<real-key>'
docker compose up -d --force-recreate backend
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.embedding_provider, s.embedding_base_url, bool(s.embedding_api_key), s.embedding_model, s.embedding_dimensions)"
$doc = Invoke-RestMethod "$base/api/documents?final_status=approved&limit=1" -Headers $headers | Select-Object -First 1
$reindex = Invoke-RestMethod "$base/api/documents/$($doc.id)/reindex" -Method Post -Headers $headers
$reindex.embedding_model
$reindex.embedding_version
$reindex.chunk_count
$reindex.vector_point_ids.Count
~~~

当前 OpenAI-compatible `remote` / `text-embedding-3-small` / 1536 已 PASS-LIVE。历史 document 3 为 8 chunks/8 points；task 23 official document 6 首次 reindex 为 6 chunks/6 embeddings，第二次为 6 cache hits/0 embeddings 且 ID 集合不变。PostgreSQL/Qdrant 当前均为 14 indexed chunks/points；payload 的 `chunk_id` 与 point ID 相等。历史 401 保留为 credential fail-closed 证据，没有 fake fallback 或半写入。

## 11.1 Phase B rerank and retrieval-matrix checkpoint

Run these checks after deploying a build containing migration `0008_rerank_observability`:

~~~powershell
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print({'provider': s.rerank_provider, 'configured': bool(s.rerank_api_key), 'model': s.rerank_model, 'timeout_seconds': s.rerank_timeout_seconds, 'failure_policy': s.rerank_failure_policy})"
~~~

Expected: Alembic reports `0008_rerank_observability (head)` and `No new upgrade operations detected`; the configuration output contains only `configured=true|false`, never a key. With `provider=none`, a protected `/api/search/debug` request using `mode=hybrid_rerank` must return `rerank_applied=false`, `rerank_metadata.provider=none`, `rerank_metadata.cost=null`, `rerank_metadata.cost_measurement=not_applicable`, and `warnings` containing `rerank_provider_disabled`, while ordinary Hybrid hits remain available.

For a remote provider, set `ODIRAG_RERANK_PROVIDER=remote`, `ODIRAG_RERANK_BASE_URL`, `ODIRAG_RERANK_MODEL`, `ODIRAG_RERANK_TIMEOUT_SECONDS`, `ODIRAG_RERANK_FAILURE_POLICY`, and inject `ODIRAG_RERANK_API_KEY` through the approved secret mechanism. Do not put it in this checklist output, a shell history artifact, or a response capture. Then verify a real `/api/search/debug` result has `rerank_applied=true`, a non-empty `rerank_results`, bounded `candidate_count`/`reranked_count`, a non-negative latency, and a cost measurement that is either provider-reported or explicitly `not_available`.

Test both policies with a controlled unreachable endpoint only in a non-production environment:

- `open`: response remains 200, final hit order equals fusion order, `rerank_applied=false`, and metadata contains a stable redacted error code.
- `closed`: the request returns the normal structured provider-unavailable error; it must not silently degrade.

Run the four-mode matrix against the same verified evaluation-question snapshot:

~~~powershell
# Authenticate normally, then post the same verified question IDs for all modes.
Invoke-RestMethod "$api/evaluations/matrix" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  matrix_name = "retrieval-matrix-$(Get-Date -Format yyyyMMddHHmmss)"
  question_ids = @('<verified-question-id>')
  top_k = 10
} | ConvertTo-Json)
~~~

Expected: exactly four runs named/marked `bm25`, `vector`, `hybrid`, and `hybrid_rerank`, all using the same returned `question_ids` snapshot and requested/effective `top_k`. Compare Recall@5/10, MRR, nDCG, citation precision/recall, answer-grounding rate, unsupported-answer rate, latency, and cost only when their report denominator is non-zero. A fixture or deterministic result is not remote rerank PASS-LIVE.

Actual 2026-08-10 local checkpoint: fresh backend image installed Alembic `1.18.5`; real PostgreSQL reached `0008_rerank_observability (head)` with no drift; all eight Compose services healthy; 8080 and health endpoint returned 200. The current runtime was `provider=none/configured=false`, and a real debug search produced five hits with the required disabled metadata. Remote rerank remains **BLOCKED-LIVE**.

## 11.2 Phase C bounded corpus expansion checkpoint

### 11.2.1 Generalized-crawl code gate (local/fixture only)

Run before any live corpus task:

~~~powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests\unit\test_crawler_adapters.py tests\unit\test_coze_crawl_provider.py -q
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\black.exe --check app tests
.\.venv\Scripts\mypy.exe app
Pop-Location
~~~

Expected code gate: backend regression, Ruff, mypy and the current source-scoped Black check pass. This gate verifies deterministic HTML candidate scoring, URL normalization, bounded pagination, direct-detail extraction, attachment/image/OCR metadata, SPA/API fallback, site rules, stable failure codes and strict Coze relative-resource normalization. A separate read-only public-URL smoke in the backend container currently returns `UnsafeUrlError` from the existing SSRF/public resolver for the tested government domains; do not weaken that resolver or count the smoke as live acceptance. This gate must not be counted as a real document or provider acceptance.

### 11.2.2 Live C1 gate

Run each source through the authenticated Source/CrawlTask API after the backend runtime has loaded the new code. Use `max_pages=1` and `max_articles=5`. A task is eligible for C1 only when its persisted raw and normalized Coze response has `articles[]` with real URLs, `articles_discovered >= 1`, `articles_fetched >= 1`, and a strict `BatchCrawlResponse`; then continue through quality decision, manual approval, chunking and indexing. A HTTP 200 with `NO_ARTICLES`, a directory-page rejection, or a contract error is negative live evidence, not a success. Do not edit old task rows to pass.

Run each canary through the authenticated API with `max_pages=1` and `max_articles=5`; do not mark a task successful merely because the provider returned HTTP 200.

| Task | Column | Expected interpretation | Actual result |
| --- | ---: | --- | --- |
| 24 | 4 (gov.cn JSON) | `discovered >= 1` and a result-bearing `articles[]` | `0/0/0`, `no_articles`, HTTP 200 |
| 25 | 5 (JXT list) | article detail extraction followed by quality review | `1/1/1`, directory page rejected, quality `0.0` |
| 26 | 3 (KJT list) | article detail extraction followed by quality review | `1/1/1`, directory page rejected, quality `0.0` |
| 27 | 2 (KJT detail) | strict detail contract | task failed, `COZE_CONTRACT_MISMATCH` |

The historical pre-generalization baseline was 2 approved documents, 14 chunks and 14 Qdrant points. **Historical status only:** the three list-page canaries and one detail canary were **BLOCKED-LIVE** until a fresh invocation proved real detail expansion; task 27's historical relative-image contract error remains immutable evidence. The later 2026-08-12 canary and 2026-08-13 C3 checkpoint supersede this stop condition. Do not create speculative documents, use the local provider to inflate live counts, bypass manual review, or edit PostgreSQL directly.

#### 11.2.3 Post-generalization live checkpoint (2026-08-10)

The backend rollout and local code gate passed, then tasks 28-34 were run through the authenticated API with `max_pages=1,max_articles=5`. Task 28 is the only new qualifying result: KJT detail `1/1/1`, strict response, manual approval, document 9, `government/official`, `region=四川省`, HTML word count 1619, quality 0.85. It generated 9 chunks and 9 real Qdrant points using `text-embedding-3-small`; a second reindex produced 9 cache hits and did not increase the direct Qdrant count (23). Its two attachments have `download_status=completed` but `parse_status=pending` and zero parsed text, so attachment parsing is not accepted.

Tasks 29, 30 and 32 each returned a single directory-page document and were rejected. Tasks 31, 33 and 34 returned `0/0/0` with HTTP 200. Together with tasks 25-27, these are independent negative live results across KJT, JXT, MIIT and gov.cn. **At this historical checkpoint they did not satisfy C1** (10 approved documents from at least 2 sources); the then-current Coze deployment required republish/deploy with list/API detail expansion and the strict `BatchCrawlResult` contract. That blocker was later resolved; current C1/C2/C3 status is recorded at the top of this checklist. No prior task rows were modified.

Persisted totals **at this historical checkpoint** were `documents=10`, `approved=3`, `rejected=7`, `chunks=23`, `crawl_tasks=34`, `reviews=20`, `lineage=78`, `attachments=3`. The later C3 table at the top is the current total. Historical regression commands recorded backend full suite `356 passed`, `ruff check`, `black --check`, and `mypy`; the later Phase M source-scoped Black gate is `PASS-LOCAL`. These checks did not turn the then-blocked corpus gate into a live pass.

#### 11.2.4 Redeploy canary result (task 35)

The same KJT notification column (`source_column_id=3`) was rerun after the reported Coze republish with `max_pages=1,max_articles=5`. **Historical result:** HTTP 200/completed and strict `batch_crawl`, but `articles_discovered=1`, `articles_fetched=1`, `articles[]=1`; the sole URL was the directory page `https://kjt.sc.gov.cn/kjt/gstz/newschild.shtml`, not a detail URL, and the quality decision was rejected (`0.0`). The URL deduplicated against an existing rejected document, so totals at that time remained `documents=10`, `approved=3`, `rejected=7`, `chunks=23`, Qdrant points `23`, and `crawl_tasks=35`. The canary threshold was not met then; the later five-article canary resolved it.

Task 36 repeated the canary and inspected the persisted raw response. **Historical result:** raw `batch_result.articles` itself contained one item with `success=true` and no failed URLs, proving the missing articles were not dropped by local Pydantic normalization. This recorded the then-current endpoint/deployment mismatch; it was resolved by the later endpoint alignment and is not the current stop condition.

Task 37 confirmed the request still used the intended KJT list URL, while the raw response remained one directory article. Its invocation endpoint/deployment identifiers match task 36 and both report `batch_crawl-v1`. Before resuming C1, synchronize the local runtime to the exact Coze endpoint/version whose HTTP response was verified in the console; do not change crawler code or bypass the `articles>=2` and distinct-detail-URL gate.

#### 11.2.5 Formal multi-article canary and C2 gate (2026-08-12)

The deployment mismatch above is historical evidence, not the current state. The formal HTTP endpoint was called directly with `source_url=https://www.scsia.org/newslist/1.html`, `max_pages=1`, and `max_articles=5`. It returned HTTP 200, `workflow_version=batch_crawl-v1`, `articles_discovered=5`, `articles_fetched=5`, and five distinct detail URLs (`/portal/new/7587`, `/7556`, `/7555`, `/7551`, `/7542`). Mark the multi-article canary **PASS-LIVE**; retain scsia as association rather than changing its trust type.

C1 and C2 then ran only through the authenticated Source/CrawlTask API with provider `coze`, strict `batch_crawl`, existing quality decisions, manual review, remote `text-embedding-3-small`, and real Qdrant upserts. No fixture, Local provider, direct SQL insertion, quality-threshold reduction, historical rewrite or source-trust downgrade was used.

Current C2 acceptance values:

| Gate | Expected | Actual 2026-08-12 | Status |
| --- | --- | --- | --- |
| qualified corpus | 50 government/official documents with valid region | 50 across 14 source rows and 11 domains | PASS-LIVE |
| global persistence | database and audit counts retained | documents 98; approved 51; rejected 21; pending 26; tasks 128; reviews 160; lineage 539 | PASS-LIVE |
| index consistency | PostgreSQL chunks = direct Qdrant exact points | 393 = 393; collection green | PASS-LIVE |
| approved dedupe | duplicate canonical URLs/content hashes = 0 | 0 / 0 | PASS-LIVE |
| repeat reindex | point IDs/count unchanged | document 98 points 4→4; global 393→393 | PASS-LIVE |
| attachment text | parsed/OCR evidence for attachment-dependent claims | 52 downloaded, all parse pending; one requires OCR | **NOT ACCEPTED** |
| disk guard | stop below 50 GiB free | D: 107.29 GiB free | PASS |

The 50 qualified government/official documents exclude the retained historical association record with `region='??'`. Do not count the 26 pending documents as accepted. Do not claim attachment parsing or OCR success from `download_status=completed`; main HTML content is the accepted C2 evidence.

Checkpoint regression commands/results (historical): backend pytest `356 passed`; Ruff and mypy pass; frontend lint/type-check/Vitest `18/18`/build pass; fixture Playwright `10 passed, 1 skipped`; Compose config valid; all eight services healthy; Alembic `No new upgrade operations detected`; Redis PONG; 8080 and health API HTTP 200. The later Phase M regression is authoritative (`370 passed`, source-scoped Black `PASS-LOCAL`, current migration `0010`). The live evidence-sufficiency script still returns a grounded MIIT Direct-LLM citation and safe refusal for no-evidence/adversarial queries, preserving `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5`. Runtime `python -m pip check` is not applicable because the hardened runtime intentionally omits pip; use the builder-stage check documented in Phase E.

## 11.3 Phase D-E local gates

Run the source-discovery contract checks without a Brave key; the expected result is an explicit provider blocker, never a fixture claim:

~~~powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests\unit\test_source_discovery.py tests\integration\test_source_discovery_api.py tests\integration\test_source_discovery_scheduler.py -q
Pop-Location
npm --prefix frontend audit --json
npm --prefix frontend audit --omit=dev --json
docker scout cves --only-severity critical,high,medium,low odirag/backend:local
docker scout cves --only-severity critical,high,medium,low odirag/frontend:local
~~~

Expected: 19 source-discovery focused tests pass; a real Brave run is **BLOCKED-LIVE** when `ODIRAG_SOURCE_DISCOVERY_API_KEY` is absent; npm audit reports zero vulnerabilities; current Scout results are backend digest `b41a63d5b943` at `0C/0H/0M/0L` and frontend digest `7dcc62cebccd` at `0C/0H/0M/3L` for Alpine `libxml2 2.13.9-r2` with no fixed version. Do not mark the three low findings resolved and do not run a force/base-image major upgrade solely to clear them. Verify the actual builder dependency set with `docker build --target builder -t odirag/backend:builder-check -f Dockerfile.backend .` followed by `docker run --rm odirag/backend:builder-check python -m pip check`; remove only that exact temporary tag after confirming no container uses it.

## 11.4 Phase F live evaluation matrix

This command uses the existing authenticated API session (`$api` and `$headers` from the authentication section) and writes real evaluation questions, query traces, lineage and four report sets. It is not a fixture command. Do not place a password, token or provider key in this file or shell history.

~~~powershell
$matrixPayload = @{
  matrix_name = 'phase-f-live-miit-app-filing-20260810'
  category = 'phase-f-live'
  retrieval_version = 'phase-f-live-20260810'
  top_k = 5
  questions = @(
    @{
      question_id = 'phase-f-live-miit-app-filing-support-v2'
      question = '未履行备案手续的 APP 主办者能否从事 APP 互联网信息服务？'
      query_type = 'rag'
      expected_document_ids = @('868a6c55-5806-4237-875c-40163fa5b8e5')
      expected_chunk_ids = @('d7353b15-4d57-5a81-a034-708b616e93e6')
      expected_answer_points = @('不得从事APP互联网信息服务')
      difficulty = 'acceptance'
      category = 'phase-f-live'
      created_by = 'phase-f-live'
      verified = $true
    },
    @{
      question_id = 'phase-f-live-miit-app-filing-refusal-v2'
      question = '火星地表是否已经发现活体恐龙？'
      query_type = 'rag'
      should_refuse = $true
      difficulty = 'acceptance'
      category = 'phase-f-live'
      created_by = 'phase-f-live'
      verified = $true
    }
  )
}
$matrix = Invoke-RestMethod "$api/evaluations/matrix" -Method Post -Headers $headers -ContentType 'application/json' -Body ($matrixPayload | ConvertTo-Json -Depth 8)
if ($matrix.runs.Count -ne 4) { throw 'Expected all four retrieval modes' }
$hybridRerank = @($matrix.runs | Where-Object { $_.retrieval_mode -eq 'hybrid_rerank' })[0]
if ($null -eq $hybridRerank) { throw 'Missing hybrid_rerank result' }
$report = Invoke-RestMethod "$api/evaluations/$($hybridRerank.run_id)/report" -Headers $headers
$support = @($report.cases | Where-Object { $_.question_id -eq 'phase-f-live-miit-app-filing-support-v2' })[0]
$refusal = @($report.cases | Where-Object { $_.question_id -eq 'phase-f-live-miit-app-filing-refusal-v2' })[0]
if ($null -eq $support -or $support.refused -or $support.cited_chunk_ids -notcontains 'd7353b15-4d57-5a81-a034-708b616e93e6') { throw 'Expected real grounded MIIT citation' }
if ($null -eq $refusal -or -not $refusal.refused -or $refusal.cited_chunk_ids.Count -ne 0) { throw 'Expected no-evidence safe refusal' }
~~~

Expected: every mode must record its actual retrieval mode and top-k. The selected `hybrid_rerank` report must retrieve the real official MIIT chunk, use Direct LLM only when evidence is sufficient, return a non-empty cited answer, and safely refuse the no-evidence question. When `ODIRAG_RERANK_PROVIDER=none`, a `rerank_provider_disabled` warning is correct degradation and must not be reported as remote-rerank acceptance. A two-question matrix is a live plumbing gate only; retain a larger human-reviewed corpus for release-quality and SLA conclusions.

Actual local regression checkpoint (2026-08-10, historical): backend `350 passed`; Ruff, Black (203 files), and mypy (155 source files) passed. Frontend lint, type-check, Vitest `18/18`, and production build passed; Playwright reported `10 passed, 1 skipped`. The skip is an explicit live-stack gate and is not reported as Live Acceptance. The later Phase M regression supersedes this table with backend `370 passed` and source-scoped Black `PASS-LOCAL`. All eight Compose services were healthy, and 8080 root plus `/api/system/health` returned 200.

## 12. Rerank provider

~~~powershell
$env:ODIRAG_RERANK_PROVIDER = 'remote'
$env:ODIRAG_RERANK_BASE_URL = 'https://<rerank-provider-base>'
$env:ODIRAG_RERANK_API_KEY = '<real-key>'
$env:ODIRAG_RERANK_MODEL = '<real-model>'
docker compose up -d --force-recreate backend
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.rerank_provider, s.rerank_base_url, bool(s.rerank_api_key), s.rerank_model)"
$debug = Invoke-RestMethod "$base/api/search/debug" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入支持措施'; mode = 'hybrid_rerank' } | ConvertTo-Json)
$debug.rerank_results.Count
$debug.warnings
~~~

预期：rerank_results.Count 大于零，index 在输入范围内且按 provider 分数排序；warnings 不包含 rerank_provider_disabled 或 provider_unavailable。没有 rerank 凭据时只能显式使用 none 并接受降级警告。

## 13. Direct LLM provider

~~~powershell
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:ODIRAG_DIRECT_LLM_API_KEY = '<real-key>'
docker compose up -d --force-recreate backend
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.direct_llm_base_url, bool(s.direct_llm_api_key), s.direct_llm_model)"
$chat = Invoke-RestMethod "$base/api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入有哪些支持措施？' } | ConvertTo-Json)
$trace = Invoke-RestMethod "$base/api/chat/traces/$($chat.trace_id)" -Headers $headers
$trace.model_name
$trace.token_usage_json
$trace.cost
~~~

Embedding/index/hybrid retrieval 已成功。当前 `llm_provider=direct`、model `gpt-4.1-mini`、answer provider `llm`，Direct 严格 schema/citation provider call 已真实通过。正式 Chat 对 association 来源返回 `official_source_required`，这不是 cited-answer PASS。下一次验收必须先由正常抓取路径产生满足 official-only policy 的文档；provider answer 只能引用 retrieval 返回的 chunk，trace model 必须等于配置模型，且 token usage 必须证明真实调用。若 provider 不返回价格，必须保留 `cost_measurement=not_available`，不能把 cost=0 解释为免费。

## 14. Brave source discovery / Phase 16

~~~powershell
$env:ODIRAG_SOURCE_DISCOVERY_PROVIDER = 'brave'
$env:ODIRAG_SOURCE_DISCOVERY_API_KEY = '<real-brave-key>'
$env:ODIRAG_SOURCE_DISCOVERY_SEARCH_URL = 'https://api.search.brave.com/res/v1/web/search'
$api = "$base/api"
docker compose build backend
docker compose --profile async up -d --no-build backend worker scheduler
$discoveryConfig = docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.source_discovery_provider, s.source_discovery_search_url, bool(s.source_discovery_api_key))"
if ($discoveryConfig -notmatch '^brave ') { throw 'Brave source discovery is not configured' }

$run = Invoke-RestMethod "$api/source-discovery/runs" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  topic = '企业研发投入支持政策'
  region = '四川'
  organization_level = 'provincial'
  required_source_count = 1
  required_document_count = 3
  max_candidates = 10
  execution_mode = 'queued'
} | ConvertTo-Json)
$deadline = (Get-Date).AddMinutes(5)
do {
  Start-Sleep -Seconds 2
  $run = Invoke-RestMethod "$api/source-discovery/runs/$($run.id)" -Headers $headers
} while ($run.status -in @('pending','running') -and (Get-Date) -lt $deadline)
if ($run.status -ne 'awaiting_approval') { throw "Discovery did not reach manual approval: $($run.status)" }

$candidates = @(Invoke-RestMethod "$api/source-discovery/runs/$($run.id)/candidates" -Headers $headers)
$candidate = @($candidates | Where-Object { $_.status -eq 'pending_approval' } | Sort-Object quality_score -Descending | Select-Object -First 1)[0]
if ($null -eq $candidate) { throw 'No pending_approval candidate was returned' }
if ($candidate.official_status -ne 'official' -or $candidate.quality_score -lt 0.65) { throw 'Candidate failed official/quality threshold' }
if (-not $candidate.official_evidence_json.same_host -or -not $candidate.official_evidence_json.status_ok) { throw 'Candidate failed exact-host or HTTP success validation' }
if (@($candidate.columns | Where-Object { $_.status -eq 'trial_crawled' }).Count -lt 1) { throw 'No trial-crawled column' }

# Approval is an explicit gate: activation before approval must fail with 409.
$blocked = Invoke-WebRequest "$api/source-discovery/candidates/$($candidate.id)/activate" -Method Post -Headers $headers -SkipHttpErrorCheck
$blockedError = $blocked.Content | ConvertFrom-Json
if ($blocked.StatusCode -ne 409 -or $blockedError.error.code -ne 'INVALID_SOURCE_CANDIDATE_STATE') { throw 'Expected 409 INVALID_SOURCE_CANDIDATE_STATE' }
$approved = Invoke-RestMethod "$api/source-discovery/candidates/$($candidate.id)/approve" -Method Post -Headers $headers
if ($approved.status -ne 'approved' -or [string]::IsNullOrWhiteSpace($approved.approved_by)) { throw 'Manual approval was not recorded' }
$activated = Invoke-RestMethod "$api/source-discovery/candidates/$($candidate.id)/activate" -Method Post -Headers $headers
if ($activated.status -ne 'activated' -or $null -eq $activated.source_id) { throw 'Candidate activation failed' }
$source = Invoke-RestMethod "$api/sources/$($activated.source_id)" -Headers $headers
if (-not $source.enabled -or $source.official_status -ne 'official' -or @($source.columns | Where-Object enabled).Count -lt 1) { throw 'Activated source/column is not enabled and official' }

$events = @(Invoke-RestMethod "$api/source-discovery/runs/$($run.id)/events" -Headers $headers)
if ($events.Count -lt 1 -or $events[0].stage -ne 'content_gap_detection') {
  throw 'Run event history does not start with content_gap_detection'
}
$candidateEvents = @(Invoke-RestMethod "$api/source-discovery/candidates/$($candidate.id)/events" -Headers $headers)
$requiredStages = @('candidate_discovery','official_status_validation','column_discovery','trial_crawl','quality_scoring','manual_approval','source_activation')
$observedStages = @($candidateEvents | ForEach-Object stage)
$lastIndex = -1
foreach ($stage in $requiredStages) {
  $nextIndex = -1
  for ($index = $lastIndex + 1; $index -lt $observedStages.Count; $index++) {
    if ($observedStages[$index] -eq $stage) { $nextIndex = $index; break }
  }
  if ($nextIndex -lt 0) { throw "Missing or out-of-order candidate stage: $stage" }
  $lastIndex = $nextIndex
}
$metrics = Invoke-RestMethod "$api/source-discovery/metrics" -Headers $headers
if ($metrics.activated_source_count -lt 1) { throw 'Activation metrics were not updated' }
~~~

预期事件顺序包含：content_gap_detection → candidate_discovery → official_status_validation → column_discovery → trial_crawl → quality_scoring → manual_approval → source_activation。候选必须先是 pending_approval，未经管理员 approve 的 activate 必须返回 409；批准后 activate 才能创建 enabled Source 和 enabled SourceColumn。Brave API 的真实响应/配额要单独记录；Bing Search API 已在 2025-08-11 退役，不能把旧 Bing endpoint 当作验收路径（见 [Microsoft retirement notice](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement) 和 [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get)）。

### 14.1 真实官方站点至少 10 篇

试抓上限是 5 篇，不能把 trial crawl 当作十篇生产证据。对刚激活且人工确认至少有 10 篇可访问文章的栏目执行：

~~~powershell
$column = @($source.columns | Where-Object enabled | Select-Object -First 1)[0]
if ($null -eq $column) { throw 'No enabled column is available for the ten-article acceptance' }
$cozeStatus = Invoke-RestMethod "$api/system/coze/status" -Headers $headers
if (-not $cozeStatus.enabled -or -not $cozeStatus.token_configured -or -not $cozeStatus.batch_workflow_configured) { throw 'Coze batch workflow is not fully configured' }
$task = Invoke-RestMethod "$api/crawl-tasks" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  source_column_id = $column.id
  task_type = 'full'
  trigger_type = 'manual'
  execution_mode = 'queued'
  provider = 'coze'
  contract_mode = 'batch_crawl'
  provider_contract = 'batch_crawl'
  max_articles = 10
  max_pages = 1
} | ConvertTo-Json)
$deadline = (Get-Date).AddMinutes(15)
do {
  Start-Sleep -Seconds 2
  $task = Invoke-RestMethod "$api/crawl-tasks/$($task.id)" -Headers $headers
} while ($task.status -notin @('completed','waiting_review','partial_failed','failed','cancelled') -and (Get-Date) -lt $deadline)
if ($task.status -notin @('completed','waiting_review')) { throw "Ten-article crawl failed: $($task.status)" }
if ($task.discovered_count -lt 10 -or $task.fetched_count -lt 10 -or $task.failed_count -ne 0) { throw "Ten-article requirement failed: discovered=$($task.discovered_count), fetched=$($task.fetched_count), failed=$($task.failed_count)" }
$invocations = @(Invoke-RestMethod "$api/crawl-tasks/$($task.id)/invocations" -Headers $headers)
if (@($invocations | Where-Object { $_.contract -eq 'batch_crawl' -and $_.status -eq 'completed' -and $_.http_status_code -ge 200 -and $_.http_status_code -lt 300 }).Count -lt 1) { throw 'No successful persisted batch_crawl invocation' }
$results = @(Invoke-RestMethod "$api/crawl-tasks/$($task.id)/results" -Headers $headers)
$summary = Invoke-RestMethod "$api/crawl-tasks/$($task.id)/acceptance-summary" -Headers $headers
$failedUrls = @(Invoke-RestMethod "$api/crawl-tasks/$($task.id)/failed-urls" -Headers $headers)
if ($results.Count -lt 10 -or $summary.database_document_count -lt 10 -or $failedUrls.Count -ne 0) { throw 'Ten real documents were not persisted' }
~~~

预期：任务为 `completed` 或正常的 `waiting_review`，至少发现/抓取/持久化 10 篇，失败 URL 为 0，且存在成功的 `batch_crawl` Coze invocation。少于 10 篇、失败 URL、没有 invocation 或只有 fixture 数据均为 FAIL。

### 14.2 Coze review 与 grounded chat

配置真实 `ODIRAG_LLM_PROVIDER=coze`、`ODIRAG_ANSWER_PROVIDER=llm`、`COZE_API_TOKEN`、`ODIRAG_COZE_BOT_ID` 后，按串行构建规则重启；栏目批量 URL 仍使用独立的 `COZE_BATCH_API_URL`：

~~~powershell
$env:ODIRAG_LLM_PROVIDER = 'coze'
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:COZE_ENABLED = 'true'
$env:COZE_API_TOKEN = '<real-token>'
$env:ODIRAG_COZE_BOT_ID = '<real-bot-id>'
docker compose build backend
docker compose --profile async up -d --no-build backend worker
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.coze_base_url, bool(s.coze_api_token), s.coze_bot_id)"

$review = $null
foreach ($item in $results) {
  $attempt = Invoke-RestMethod "$api/reviews/$($item.id)/run" -Method Post -Headers $headers
  if ($null -ne $attempt.llm_decision) { $review = $attempt; break }
}
if ($null -eq $review) { throw 'No fetched document reached a real Coze review' }
$documentId = $review.document_id
if ($review.final_status -ne 'approved') {
  $manual = Invoke-RestMethod "$api/reviews/$documentId/manual-review" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ decision = 'approve'; summary = 'Production acceptance reviewer confirmed this official document'; reasons = @('Acceptance evidence') } | ConvertTo-Json)
  if ($manual.final_status -ne 'approved') { throw 'Manual review approval failed' }
}
$index = Invoke-RestMethod "$api/documents/$documentId/reindex" -Method Post -Headers $headers
if ($index.chunk_count -lt 1 -or $index.vector_point_ids.Count -lt 1) { throw 'Approved Coze-reviewed document was not indexed' }
$chat = Invoke-RestMethod "$api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '<来自该官方文档、可由原文直接回答的问题>' } | ConvertTo-Json)
$trace = Invoke-RestMethod "$api/chat/traces/$($chat.trace_id)" -Headers $headers
if ($chat.refusal -or $chat.citations.Count -lt 1 -or $trace.model_name -ne 'coze-bot') { throw 'Grounded Coze chat did not return a cited answer' }
if ($trace.token_usage_json.measurement -eq 'not_available') { Write-Warning 'Provider omitted token usage; record cost as unverified, not zero' }
~~~

预期：review 的 `llm_decision` 来自真实 Coze，批准文档可被真实 embedding 索引，chat 只引用已存储 chunk；Coze trace 的 `model_name` 为 `coze-bot`。缺少凭据、异步语义不匹配、无 usage 或无引用必须保留为 UNVERIFIED/FAIL，不能用 fixture 替代。

## 15. 结束条件与当前结论

### Phase G data-debt acceptance（2026-08-13 actual）

- [x] Real PostgreSQL upgraded to `0009_attachment_parsing_audit`; `alembic check` returned `No new upgrade operations detected`.
- [x] All 123 attachments reached a terminal audit state: 77 failed, 46 unsupported, 0 pending.
- [x] No attachment/OCR success was fabricated; the one OCR-required case records `OCR_UNAVAILABLE`.
- [x] Manual review gate preserved: auto-approved 0, deterministic hard-rejected 1, human review required 46.
- [x] Sixteen historical `region='??'` values retained with unresolved immutable correction records; no silent update.
- [x] Phase C accepted corpus retained: 101 approved documents, 821 chunks, Qdrant collection `odirag_chunks` with 821 points.
- [x] Full backend regression: 364 passed; Ruff and mypy passed; eight Compose services healthy; 8080/health returned 200.
- [x] Black local gate: `PASS-LOCAL`; isolated-cache source-scoped checks leave 219 backend files and the two changed scripts unchanged.
- [ ] Attachment content recovery: `BLOCKED-EXTERNAL` until source bytes/OCR are available.
- [ ] Remaining document decisions: `BLOCKED-HUMAN` for 46 records.

### Phase H/I provider gates

- [ ] Remote rerank: `BLOCKED-EXTERNAL-RERANK-KEY`; host and Compose use `none`. Neither disabled nor deterministic results may be reported as remote live acceptance. Provider/failure-policy regression: 82 passed, including explicit 429/500/503 mapping.
- [ ] Brave discovery: `BLOCKED-EXTERNAL-BRAVE-KEY`; provider contract tests do not replace a real Brave response. Source-discovery contract/security/manual-gate regression: 25 passed.
- [x] Missing provider credentials do not stop independent Phase J-M engineering work.

### Phase J formal evaluation gate

- [x] Generated 100 candidate cases from real approved/indexed official PostgreSQL documents and chunks.
- [x] Positive cases include real document ID, source URL and chunk ID; 93 distinct document/chunk identities and 11 official domains are represented.
- [x] All 18 required fact, temporal, regional, attachment/OCR, multi-document, refusal and adversarial categories are represented.
- [x] Dataset is explicitly `DRAFT_EVAL_SET`; `human_verified_count=0`; formal metrics are null in `evaluation_results.json`.
- [ ] Human verification of question, expected answer, evidence identities, refusal expectation, region and temporal constraint: `BLOCKED-HUMAN-EVAL-REVIEW`.
- [ ] Four-mode formal matrix with remote rerank: also depends on `BLOCKED-EXTERNAL-RERANK-KEY`.

只有 PostgreSQL、Redis、Qdrant、worker、scheduler、Nginx、frontend、Alembic 和所选真实 provider 全部 PASS-LIVE，且日志/trace/备份恢复证据已归档，才可把部署标为生产接受。

### 本机 development 栈证据（历史检查点；2026-08-09 当前补充）

以下结果是真实本地 Compose 运行结果，标记为 `VERIFIED-LOCAL`。它们证明当前 development 栈，但不能替代目标生产环境的 `PASS-LIVE`：

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| Compose 服务 | 2026-08-09 当前 8 个服务均 healthy：backend、frontend、postgres、redis、qdrant、worker、scheduler、nginx | development 配置未证明生产 secret/TLS、目标持久化和 registry provenance |
| PostgreSQL | healthy；6 documents、2 approved、14 indexed chunks；task 23 completed 1/1 discovered/fetched, 1 accepted/approved official doc, pending/rejected/failed 0 | production scale/RPO/RTO unverified |
| Redis | PONG、backend ping=True、应用配置 `redis`、响应含限流 header、共享 `odirag:ratelimit:*` key 存在 | 未证明 ACL、故障转移、多副本公平性和持久化恢复 |
| Qdrant | health 正常；direct REST 1 collection/14 points；task 23 official payload 6/6；重复 reindex ID 集合不变；summary 1 doc/6 chunks/true/6 | live delete/compensation、备份和生产拓扑未验 |
| worker/scheduler | healthy；task 13 historical `TASK_STATE_CHANGED` retained；task 14 OCR and task 23 official closed loop completed | crawl/OCR/review/official answer PASS-LIVE；Brave/long-running failure recovery remains |
| monitoring | task 8 后 `high_failure_rate` 告警为 severity `high`、status `open`，observed `0.4`、threshold `0.2` | 证明本地规则检测到失败率；生产通知投递、升级、确认、恢复和多实例聚合未验证 |
| Nginx/frontend | `/`、`/api/system/health` 均 200；dependencies healthy；fixture Playwright 9 passed/1 skipped；真实 8080 live-stack 1 passed并展示正式 official citation；查询检查器可见 Evidence decision | HTTPS/目标生产浏览器门禁未通过 |
| Docker/WSL 恢复 | WSL 数据位于 D 盘且未删除 VHD/Volume/数据库；2026-08-07 Client/Server 29.6.2、Compose v5.3.1 与八服务通过 | 目标主机自动启动、生产 secret/TLS、容灾和 registry provenance 未验证 |
| fresh 镜像与供应链 | Current backend/frontend digest 为 `b41a63d5b943` / `7dcc62cebccd`；构建、`pip check`、Alembic、八服务和 npm 两种 audit 通过；Scout backend `0C/0H/0M/0L`, frontend `0C/0H/0M/3L` | 三项 libxml2 low 均无修复版本；目标 registry 仍必须生成新 SBOM/CVE、签名和 provenance |
| Alembic | 正式约束 `>=1.18,<1.19`，锁定并实装 1.18.5；existing PostgreSQL 到 `0008_rerank_observability` 且 `check` 无漂移；既有专用库 round-trip 通过 | 未对生产业务库直接 downgrade；目标维护窗口、锁等待和回滚审批未验证 |
| scsia.org | task 14 HTTP 200/completed、strict schema、5 docs；doc 3 OCR v2 length 5358 accepted/approved/indexed；8 chunks/8 points；hybrid retrieval 5 hits | association source is correctly refused by official-only grounding；region metadata `??` breaks province auto-filter；two docs remain OCR_FAILED/rejected |
| MIIT official | task 23 HTTP 200/completed、strict schema、1 doc accepted/approved/indexed；6 chunks/6 points；Hybrid 5 official hits；Direct answer 1 exact citation；zero-hit 与 non-empty irrelevant retrieval 均安全拒答 | Phase A PASS-LIVE；仍需 Phase B-F 的广泛评估与生产门禁 |

因此知识库真实闭环结论为 **PASS-LIVE / 5/5**，Phase A Evidence Sufficiency 和 Phase C C1/C2/C3（100 篇合格官方文档、821 chunks/points）也为 **PASS-LIVE**。Phase B/D/E 已完成本地门禁，Phase F 已完成两题真实矩阵但不代表代表性质量评估。整体生产发布仍为 **NOT ACCEPTED / EXTERNAL ACCEPTANCE REQUIRED**：真实 remote rerank、Phase D Brave、region `??` 历史数据、附件解析/OCR、生产 TLS/secret、CI/registry 和代表性 Phase F 评估仍未全部验收。
