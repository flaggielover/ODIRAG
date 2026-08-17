# ODIRAG Implementation Status

## Production Engineering Closure (2026-08-17, latest authoritative)

This section supersedes older deployment, provider-availability, security, disaster-recovery,
observability, release, public-ingress, and overall production-acceptance statements below. It does
not replace the separate latest Attachment/OCR and Gold quality sections that follow.

- Phase 1 through Phase 5 and final `PRODUCTION_READINESS` are `PASS-LIVE`.
- Current production is release `v0.1.0-r6` at <https://rag.suzheodirag.top/>, with 8/8
  application services healthy and public HTTPS/TLS acceptance complete.
- The live provider path is Bailian `text-embedding-v4` at 1536 dimensions, hybrid BM25/vector
  retrieval, Cohere `rerank-v3.5`, and DeepSeek `deepseek-v4-flash` grounded answer/refusal.
- PostgreSQL remains the source of truth with 182 documents and 821 chunks; active and rollback
  Qdrant collections each retain 821 points, and the accepted attachment state is 60 parsed files
  with 69 stored attachment files.
- PostgreSQL/Qdrant/Redis/attachment recovery, measured RPO/RTO, Prometheus/Grafana/Alertmanager,
  immutable GHCR digests, SPDX SBOM, BuildKit provenance, authenticated deploy/rollback, and public
  browser/API/RAG checks are live-verified.
- The engineering regression at final public acceptance is 531 backend tests plus the recorded
  frontend/static/config checks. Production remains single-node rather than highly available.
- Answer quality is not promoted by this closure: the latest 100-question Gold result remains
  `GOLD_EVALUATION_QUALITY=PARTIAL` and `QUALITY_GUARD=FAIL-LIVE-QUALITY`.

Current production evidence and boundaries are in `PRODUCTION_READINESS_REPORT.md`; historical
checkpoint sections below remain unchanged for auditability.

## Attachment / OCR Production Closure (2026-08-15, latest authoritative)

This section supersedes older attachment counts, attachment acceptance decisions,
backend-test totals, backend image runtime, and Alembic head values below. Gold,
RAG, P95, Remote Rerank, and Brave results remain frozen.

- Real current state: attachments `123`; parsed `60`; failed `8`; unsupported
  `55`; pending `0`; terminal rate `100%`.
- Download attempt coverage is `123/123`; status-completed `115`; byte-verified
  success `70`; local files `69`; failure `8`, all real `DOWNLOAD_HTTP_404`.
- True parser-format denominator is `67`: PDF `46/53`, DOCX `13/13`, XLSX
  `1/1`; end-to-end parsing coverage is `60/67 = 89.55%`. All 60 files that
  reached a supported parser succeeded.
- Nine incorrect DOCX MIME responses contained OLE legacy bytes and are now
  terminal `UNSUPPORTED_LEGACY_FORMAT`, not parser failures.
- OCR provider is not configured. One image remains OCR-eligible but its source is
  HTTP 404, so actual OCR attempts/success are `0/0`; `ATTACHMENT_OCR=PARTIAL`.
- Parsed provenance is complete `60/60`; directed quality sampling passed `10/10`.
  The attachment volume has 69 files and zero temporary-file residue.
- Text-attachment repeat processing is a real cache hit with unchanged byte hash,
  parse timestamp, processed timestamp, and extracted length. No attachment chunks
  or Qdrant points were added.
- Final regression is pytest `518/518`; Ruff check PASS; Ruff format `245/245`;
  mypy `169` files; compileall and Alembic check PASS. Black `--version` reached
  the bounded 30-second Windows timeout with no residual process.
- Backend, worker, and scheduler all run final image
  `sha256:6d1b89444b4ef9fda3885521f6e3fbbee61c0a8fc41e3dd450352dfcd0cbacb9`;
  all 8 Compose services and API dependencies are healthy. Alembic is
  `0012_attachment_processing_audit (head)` with no drift.
- Frozen core remains documents `182`, approved `101`, rejected `35`, pending
  `46`, chunks `821`, Qdrant green/`821`; Gold artifact hashes are unchanged.
- Detailed evidence: `ATTACHMENT_BASELINE_REPORT.md` and
  `ATTACHMENT_OCR_REPORT.md`.

## Final Gold Quality Closure (2026-08-15, latest authoritative)

This section supersedes older Gold metrics, quality-guard results, image IDs,
backend-test counts, and migration status below where they differ.

- Checkpoint restore completed with the dirty working tree and every volume
  preserved. Final `odirag/backend:local` manifest list is
  `sha256:70b8e21a15aa2b2f1f3fccfccb56ce6aa3e68d36b1119384d43e59632e55f7c5`;
  backend, worker, and scheduler run that same image and are healthy.
- Final Live Guard run 15: supported `14 answer / 9 refuse`, with `14/14`
  answered cases grounded; Gold refusal `10/10`, citations `0`, unsupported
  answers `0`, and errors `0`. QA14 is `5/8`, hence
  `QUALITY_GUARD=FAIL-LIVE-QUALITY` while refusal safety is PASS.
- Final Gold run 16: 100/100, zero execution errors. Recall@5/10
  `0.885/0.885`, MRR `0.840667`, nDCG@5/10 `0.806227`, exact citation P/R
  `0.288069/0.433333`, grounded `0.948276`, refusal accuracy `0.68`, unsupported
  answer rate `0`, Evidence Sufficiency Accuracy `0.96`, Supported Answer Recall
  `0.644444`.
- Final confusion: Gold supported `58 answer / 32 refuse`; Gold refusal
  `0 answer / 10 refuse`. The accurate result is
  `GOLD_EVALUATION_QUALITY=PARTIAL`; no further validator or evaluation loop ran.
- Remote provider boundary remains `PASS-LIVE`; run 16 coverage is
  `67/100 applied + 33/100 HTTP 429 fail-open`, so
  `GOLD_RUN16_RERANK_APPLICATION_COVERAGE=PARTIAL-LIVE`.
- Final engineering regression: pytest `501 passed in 35.19s`; Ruff PASS; Ruff
  format `237 files already formatted`; mypy PASS across 167 files; compileall,
  Alembic check, and diff check PASS. Black is
  `UNVERIFIED-WINDOWS-TIMEOUT` after the only controlled 120-second check.
- Runtime/data: 8/8 services healthy; homepage 200; API, PostgreSQL, Redis, and
  Qdrant healthy; documents `182`, approved `101`, rejected `35`, pending `46`,
  chunks `821`, Qdrant green/`821` points; migration
  `0011_attachment_download_audit (head)` with no drift.
- Formal artifacts are `data/evaluation/gold_run_16/`,
  `data/evaluation/gold_metrics.json`, `data/evaluation/gold_summary.md`, and the
  run16 root `gold_failure_matrix.json/.csv`.

## Phase AD Gold evaluation closure (2026-08-14, latest authoritative checkpoint)

This section supersedes the older Human Evaluation and Gold metrics below where
they differ. It does not change the completed Remote Rerank, Brave Source
Discovery, Source Governance, SSRF, or Phase C results.

- Human review is complete. The canonical workbook
  `data/evaluation/eval_human_review.xlsx` was reviewed row-by-row and imported
  through the formal importer. Live PostgreSQL dry-run and apply both returned
  `TOTAL=100`, `REVIEWED=100`, `UNREVIEWED=0`, `PASS=100`, `FIX=0`, `REJECT=0`,
  `VERIFIED=100`, and `TRACEABILITY_ERRORS=0`; the final artifact is
  `data/evaluation/phase_j_human_verified.json`. Therefore
  `HUMAN_REVIEW_INFRASTRUCTURE=PASS-LOCAL`, `HUMAN_EVALUATION=PASS-HUMAN`,
  `HUMAN_VERIFIED_COUNT=100`, and `HUMAN_REVIEW_COMPLETE=true`.
- Formal real-chain Gold run `6` completed all 100 questions with zero execution
  errors. Retrieval metrics were Recall@5 `0.885`, Recall@10 `0.885`, MRR `0.809`,
  nDCG@5 `0.789022`, and nDCG@10 `0.789022`. Citation precision/accuracy was
  `0.067513`, citation recall/completeness `0.116667`, grounded-answer rate
  `1.0` over 20 assessed answers, refusal accuracy `0.3`, unsupported-answer rate
  `0.0` over 10 intended refusals, and evidence-sufficiency accuracy `0.56`.
- The answer-quality gate did not pass: 80/100 cases refused, including 70 cases
  labelled supported. Independent run `7` selected two supported and two refusal
  questions; both refusal cases passed their refusal contract, but both supported
  cases refused. The authoritative status is
  `GOLD_EVALUATION=COMPLETE-WITH-QUALITY-FAILURE` and
  `QUALITY_GUARD=FAIL-LIVE-QUALITY` (2/4 passed). No threshold, validator,
  grounding, citation, or refusal rule was weakened.
- Run `5` is retained only as a failed preflight: its source rows used unsupported
  metadata filters and it produced no valid evaluation samples. It is excluded from
  Gold metrics.
- Run `6` persisted 100 remote-provider traces, 68 applied reranks, and 31
  fail-open traces. This does not invalidate the provider acceptance, but the
  100-case application coverage is recorded as `PARTIAL-LIVE`; no credentials or
  provider response bodies are stored in the report.
- Gold artifacts are `data/evaluation/gold_run_6/gold_metrics.json` and
  `data/evaluation/gold_run_6/gold_summary.md`; the independent guard artifacts are
  under `data/evaluation/gold_quality_run_7/`.
- The latest fixed performance matrix remains 60 valid samples: P50 `1638 ms`,
  P95 `6774 ms`, P99 `9129 ms`, with the `<5000 ms` target unmet. Core state is
  unchanged: documents `182`, approved `101`, rejected `35`, pending manual review
  `46`, chunks `821`, Qdrant green with `821` points, and
  `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`.
- Completed provider statuses remain `REMOTE_RERANK_PROVIDER=PASS-LIVE`,
  `REMOTE_RERANK_FULL_RAG=PASS-LIVE`, and `BRAVE_SOURCE_DISCOVERY=PASS-LIVE`.

## Phase Z Source Governance Closure (2026-08-14, latest authoritative checkpoint)

This section supersedes older Brave Source Discovery conclusions where they differ.
The Remote Rerank and historical Brave sections below remain as audit evidence.

- Real Brave run `4`, candidate `7`, validated the Sichuan Provincial Department
  of Economy and Information Technology at
  `https://jxt.sc.gov.cn/scjxt/index.shtml`: HTTPS/HTTP 200, exact host and site,
  trusted `.gov.cn` suffix, government markers, and official score `1.0`.
- Six bounded columns fetched `30` real details. The embedded `#panel-20002`
  announcement panel accepted `2/5` DIRECT software-policy documents; total trial
  result was `2 accepted / 28 rejected`, average accepted length `798`, and quality
  `0.7667` against the unchanged `0.65` threshold.
- Before approval, Candidate 7 activation returned HTTP `409`
  `INVALID_SOURCE_CANDIDATE_STATE`. The explicit human decision then used the
  formal API: `pending_approval -> approved` at
  `2026-08-14T06:01:58.993737Z`, followed by formal activation.
- Activation created enabled official government Source `46` and only the proven
  `trial_crawled` announcement SourceColumn `191`. The five `0/5` columns remain
  in candidate audit history and were not activated. Automatic discovery remains
  disabled with zero configured topics; no CrawlTask was created.
- The persisted run-level summary still reports `approved_count=0` and
  `activated_count=0`; this is an aggregate-counter drift. Candidate, approval,
  event-lineage, Source, and SourceColumn records are the authoritative activation
  evidence and are internally consistent.
- Final statuses: `BRAVE_SEARCH_PROVIDER=PASS-LIVE`, `BRAVE_SSRF=PASS-LIVE`,
  official validation/column discovery/trial crawl/manual governance/source
  activation all `PASS-LIVE`, and `BRAVE_SOURCE_DISCOVERY=PASS-LIVE`.
- Post-activation invariants: documents `182`, approved `101`, rejected `35`,
  pending manual review `46`, chunks `821`, Qdrant green with `821` points, and
  `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`. Remote Rerank remains
  `REMOTE_RERANK_PROVIDER=PASS-LIVE` and `REMOTE_RERANK_FULL_RAG=PASS-LIVE`;
  no Cohere call was made during Phase Z.

## Phase W-X-Y Closure (2026-08-14, latest authoritative checkpoint)

This section supersedes the older Phase T-U provider status where the two differ.
The older sections remain below as historical evidence and are not current status.

### Phase W: Remote Rerank full RAG

- The prior failing trace `f9a44597-a18e-46ae-8aa5-5d36632cddc1` contained 40
  literal ASCII `?` characters in the persisted caller query. The root cause was
  corrupted caller-side UTF-8 serialization, not loss of retrieved evidence or an
  Answer Validation defect. No backend validator, relation, evidence, citation, or
  grounding rule was changed.
- Trace `70906f7f-648f-4356-a0ee-47829afae7c1` completed real Remote Rerank and
  Direct LLM execution, returned a supported official answer, and cited real chunk
  `0bf55b37-7bf1-5ce9-834a-f46754e84fec` with its title and source URL.
- Trace `e0e57258-4d19-44a9-94d4-ea8430a6f2c4` returned the supported answer that the existing-stock APP
  filing stage was September 2023 through March 2024 and the supervision/inspection
  stage was April through June 2024. It passed the unchanged relation validator and
  cited the same real official chunk.
- Broad multi-fact trace `b48ca4d8-1f40-49c8-b98e-f4c057851963` safely refused with
  `insufficient_evidence_relevance`. No-evidence trace
  `47570efd-6352-4213-8abf-ce0fbc3408c7` also safely refused before the answer LLM.
- Current result: `REMOTE_RERANK_PROVIDER=PASS-LIVE` and
  `REMOTE_RERANK_FULL_RAG=PASS-LIVE`: two supported cited answers and two safe
  refusals, with valid real citation provenance.

### Phase X: Brave Source Discovery and SSRF

- The previous `198.18.0.0/15` rejection was traced to local fake-IP DNS behavior.
  The secure resolution path now uses fail-closed DoH, validates the resolved
  addresses, pins the vetted IP at connection time while retaining the original
  HTTP Host and TLS SNI, revalidates redirects, and rejects IPv6 site-local as well
  as private, reserved, loopback, link-local, and fake-IP destinations. SSRF rules
  were not weakened.
- Only `backend`, `worker`, and `scheduler` were rebuilt/recreated; all three were
  healthy after rollout. PostgreSQL, Redis, Qdrant, frontend, nginx, and all Docker
  volumes were preserved.
- Real Brave run `3`, candidate `6`, used
  `https://jxt.sc.gov.cn/scjxt/index.shtml`. Official validation returned HTTP 200
  with exact HTTPS host, `.gov.cn` evidence, and official score `1.0`. Column
  discovery found 12 real columns.
- The bounded trial fetched 60 pages and accepted 0 documents. Every trial ended
  `NO_RELEVANT_DETAIL_DOCUMENTS`; quality was `0.5`, below threshold `0.65`.
  Candidate 6 was rejected and run 3 failed at the quality gate.
- No candidate was approved or activated; no Source or CrawlTask was created. The
  manual approval gate was not reached, so
  `MANUAL_SOURCE_APPROVAL_REQUIRED=NO` for this rejected candidate.
- Current result: `BRAVE_SEARCH_PROVIDER=PASS-LIVE`, `SSRF=PASS-LIVE`, official
  validation `PASS-LIVE`, column discovery `PASS-LIVE`, and trial/quality
  `FAIL-LIVE`. Genuine public government URLs pass while private, fake-IP, mixed,
  redirect, and rebinding cases remain fail-closed.

### Phase Y: Invariants and regression

- Final read-only re-audit confirmed HTTP 8080 `200`, `/api/system/health` `200`
  and healthy PostgreSQL/Redis/Qdrant dependencies. PostgreSQL remains at
  `documents=182`, `approved=101`, `rejected=35`, `pending_manual_review=46`, and
  `chunks=821`; Qdrant `odirag_chunks` is green with exact points `821`.
- Targeted Phase W-X-Y regression passed: `127 passed`; Ruff lint, Ruff format,
  Black, strict mypy, and `git diff --check` passed for the scoped files.
- `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE` is confirmed unchanged.

Last updated: 2026-08-14

## Phase T-U Live Results (latest authoritative provider checkpoint)

- Running Remote Rerank is now `provider=remote`, model `rerank-v3.5`. Exactly five
  real Cohere requests were made and all five returned validated remote results with
  `applied=true`, non-empty reranked candidates, finite scores in `[0,1]`, and zero
  provider errors. Three `/api/search/debug` requests passed the strict provider,
  score, chunk-provenance, warning, and count assertions.
- The supported Chat trace `f9a44597-a18e-46ae-8aa5-5d36632cddc1` persisted remote
  rerank (`8 -> 8`, 1282.509 ms), sufficient evidence and a real Direct LLM call.
  Final Answer Validation conservatively rejected the generated answer with
  `answer_contains_unsupported_relation`, so it returned zero citations. The
  no-evidence trace `06766442-fc45-4b6f-b70e-cce45e2173bd` also reranked `8 -> 8`
  (1109.401 ms), then correctly refused before the answer LLM with zero citations
  and zero answer-LLM tokens. Therefore `REMOTE_RERANK_PROVIDER=PASS-LIVE`, while
  the full supported RAG/citation gate is `PARTIAL` rather than a fabricated pass.
- Brave made two real searches. Run 1 received no usable URLs because the request
  query was corrupted by the local PowerShell encoding boundary. Run 2 used an
  explicit Unicode query and returned five real `sc.gov.cn` candidates, including
  `jxt.sc.gov.cn`, `fgw.sc.gov.cn`, `kjt.sc.gov.cn`, `www.sc.gov.cn`, and
  `jhj.sc.gov.cn`. Every candidate was rejected by the existing fetcher as
  `UnsafeUrlError` before official validation because of the local proxy/DNS SSRF
  boundary. No column, trial crawl, quality score, pending approval, activation, or
  CrawlTask was fabricated. `BRAVE_SEARCH_PROVIDER=PASS-LIVE`; the end-to-end Source
  Discovery gate is `BLOCKED-LOCAL-SSRF-PROXY-RESOLUTION`.
- Core invariants after T/U: health healthy; documents `182`, approved `101`,
  rejected `35`, pending manual `46`, chunks `821`, Qdrant exact points `821`.
  Targeted regression remains green: rerank/search `29 passed`, source discovery
  `19 passed`.

## Phase S-V Provider Acceptance Attempt (2026-08-14)

- Host `.env` now has only the required non-sensitive rerank switch changed:
  `provider=remote`, model `rerank-v3.5`, base URL `https://api.cohere.com/v2`,
  `failure_policy=open`; Remote Rerank and Brave credentials both evaluate as
  `configured=true`. No credential value was printed or copied.
- The requested minimal `backend/worker/scheduler` recreation did not execute:
  the local approval service timed out once and rejected the single retry before
  Docker access. The running backend therefore remains on the previous snapshot:
  a real `hybrid_rerank` debug request returned provider `none`, model `disabled`,
  `applied=false`, eight candidates, zero reranked results, and warning
  `rerank_provider_disabled`.
- A direct project-adapter Cohere call first failed inside the restricted network
  with `transport_error`; both approved-network attempts were stopped by the same
  approval-service failure before a provider response was received. Real Remote
  Rerank API responses: `0`; `REMOTE_RERANK` remains
  `BLOCKED-LOCAL-RUNTIME-RELOAD-AND-NETWORK`, not `PASS-LIVE`.
- Brave was not charged or called after the shared reload/network blocker was
  established. Real Brave searches: `0`; `BRAVE_SOURCE_DISCOVERY` remains
  `BLOCKED-LOCAL-RUNTIME-RELOAD-AND-NETWORK`. No candidate, Source, SourceColumn,
  trial crawl, approval, activation, or CrawlTask was fabricated.
- Current regression evidence: Remote Rerank/search tests `29 passed`; Source
  Discovery tests `19 passed`; `/api/system/health` is healthy; PostgreSQL metrics
  remain documents `182`, approved `101`, rejected `35`, pending `46`, chunks
  `821`; direct Qdrant exact count remains `821`.

## Phase N-Q Closure (historical snapshot, superseded by Phase AD)

- `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE` remains unchanged. Current
  retained counts are `documents=182`, `approved=101`, `rejected=35`,
  `pending_manual_review=46`, `chunks=821`; direct Qdrant remains at 821 points.
  No CrawlTask, document, volume, or historical trust/region row was created,
  deleted, or rewritten in this closure.
- Phase N applied additive migration `0011_attachment_download_audit` to real
  PostgreSQL and passed `alembic check`. Existing attachments are terminal:
  `123 total / 0 pending / 0 parsed / 77 failed / 46 unsupported`. All 123 are
  URL-only in this environment; 76 are `DOWNLOAD_SSRF_BLOCKED` and one is
  `OCR_UNAVAILABLE`. `ATTACHMENT_PARSING=PASS-LOCAL` for terminal-state and
  security accounting; `ATTACHMENT_OCR=PARTIAL` because approved egress bytes and a
  real OCR provider are unavailable. See `ATTACHMENT_OCR_REPORT.md`.
- Phase O executed three real benchmark runs over two fixed cases with one warm-up
  per case. Six measured samples produced overall `P50=734.236 ms`,
  `P95=5121.708 ms`, `P99=5121.708 ms`, `max=5121.708 ms`; the `<5000 ms` target
  was not met. Stage P95 values were Direct LLM `4012.936 ms`, query embedding
  `1042.8 ms`, and retrieval total `1076.773 ms`. The performance result is
  `RAG_PERFORMANCE_P95=PARTIAL`; the quality guard remains blocked because
  `human_verified_count=0`. Remote Rerank and Brave were not called.
- Phase P generated `data/evaluation/eval_human_review.xlsx` with 100 traceable
  real-corpus cases. Dry-run is `TOTAL=100, REVIEWED=0, UNREVIEWED=100, PASS=0,
  FIX=0, REJECT=0, VERIFIED=0, TRACEABILITY_ERRORS=0,
  PARTIAL_HUMAN_REVIEW`; no verified JSON was generated. Infrastructure is
  `PASS-LOCAL`, while `HUMAN_EVALUATION=BLOCKED-HUMAN`.
- Phase Q backend regression from the `backend` working directory is `399 passed`.
  Application Ruff/format and mypy pass (164 files); the three closure scripts pass
  Ruff and format. Strict Black 25.12.0 reports formatter differences on a subset
  under the current Windows toolchain, so global Black is not claimed as a pass.
  Frontend npm audit (full and production-only) reports zero vulnerabilities;
  fresh Vite/esbuild and Docker named-pipe checks were blocked by the local
  process/approval boundary and are not overstated as fresh passes.

## Current Phase (historical roadmap snapshot; Phase AD is current)

- Phase: Production strengthening Phases G-J complete; Phases K-Q locally executed with performance/OCR/human gates explicitly partial or blocked.
- Status: **KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5, EVIDENCE_SUFFICIENCY=PASS-LIVE, POSTGRESQL_MIGRATION_0011=PASS-LIVE, and QUERY_TRACE_STAGE_TIMINGS=PASS-LIVE.** The 100-document official corpus and 821-point Qdrant index remain intact. Overall production release is **NOT ACCEPTED**: OCR bytes/provider, performance target, human evaluation, external providers, disaster recovery, TLS/secrets, resource/logging and release-provenance gates remain open.
- Next Action: Human review of the 100-row workbook and approved external OCR/egress are the only next actions in this scope. Do not lower quality/grounding thresholds, count pending documents, rewrite historical rows, or extend the corpus.

## Latest Verification Checkpoint

- 2026-08-13 Phase M live trace checkpoint: real PostgreSQL is at `0010_query_trace_stage_timings` with no Alembic drift, and only the backend image was rebuilt/restarted. A supported official MIIT query produced five real retrieval hits, a real Direct LLM call (`gpt-4.1-mini`, 2,907 tokens), one traceable title/URL/chunk citation, and a non-empty stage map including retrieval, evidence, grounding, Direct LLM, citation validation and total. A no-evidence query retrieved candidates but failed Evidence Sufficiency, returned `refusal=true`, zero citations and zero answer-LLM tokens; its stage map correctly omits stages that were not executed. Both PostgreSQL rows contain only non-negative numeric timings. Query traces increased from 70 to 83 solely because this closure performed repeated real supported/refusal diagnostics; corpus counts did not change.
- 2026-08-13 local toolchain closure: frontend lint/type-check pass; sandboxed Vite/esbuild/Playwright showed `spawn EPERM`, while the approved non-sandbox rerun passed Vitest `18/18`, production build (1,850 transformed modules), and Playwright `10 passed, 1 expected skip` at four workers. With an isolated workspace Black cache and the intended source scopes, Black 25.12.0 passes `backend/app`, `backend/tests`, `backend/alembic` (219 files) and the two changed scripts; `BLACK=PASS-LOCAL`. `.git/index.lock` is absent and no Git process is active, but inherited explicit deny ACLs prevent index writes; the single controlled `git add --all` attempt failed before staging, so `GIT_CHECKPOINT=BLOCKED-LOCAL-PERMISSION` and the complete diff is preserved.
- 2026-08-13 Phase C C3 corpus checkpoint: C3 stopped at exactly 100 approved `government/official` documents with non-corrupt region metadata. All qualifying rows followed the authenticated Source/Column/CrawlTask API, real Coze `batch_crawl`, existing automatic quality decision, manual approval, remote `text-embedding-3-small`, and real Qdrant upsert path. No fixture, Local provider, direct SQL insertion, source-trust downgrade, historical rewrite or pending document was used to reach the count. The post-Phase-G current totals are `documents=182`, `approved=101` (100 qualifying official plus the retained historical association document), `rejected=35`, `pending_manual_review=46`, `chunks=821`, `sources=45`, `crawl_tasks=221`, `reviews=296`, `lineage=1053`, and `attachments=123`. The pre-cleanup C3 snapshot was `rejected=34`, `pending_manual_review=47`; it remains a historical checkpoint.
- 2026-08-13 C3 Data Quality Gate: the 100-document qualifying set spans 31 source rows and 10 official domains. Canonical/source URL duplicates, content-hash duplicates, empty titles, empty content, corrupt/null regions, missing content hashes, unindexed documents and approved documents without chunks are all zero. Word counts range from 180 to 6,408. Direct Qdrant reports collection `odirag_chunks` green with exact points `821`, matching PostgreSQL chunks. Reindexing document 181 returned `cache_hits=4`, `embedded_count=0`, and left Qdrant at 821, proving idempotency. Phase G subsequently audited the 123 attachments: 77 are `failed`, 46 `unsupported`, and none are accepted as parsed text; attachment parsing/OCR is explicitly **NOT ACCEPTED**.
- 2026-08-13 C3 provider/encoding evidence: tasks 129-221 comprise 93 bounded real Coze tasks with 86 discovered/fetched articles; persisted task decisions total 53 accepted, 15 rejected and 23 pending, with three remaining network failures. Tasks 210-221 initially timed out together after about 195 seconds with `COZE_NETWORK_ERROR`; serial retries recovered tasks 210-218, while 219-221 remain failed evidence. A PowerShell 5.1 request encoded Source 39's Chinese metadata as `??`; none of its documents were approved or counted, and no row was silently repaired. Later Sources 40-45 used explicit UTF-8 request bytes and PostgreSQL hex verification (`四川省` = `e59b9be5b79de79c81`) before tasks were created.
- 2026-08-13 C3 regression (historical checkpoint): the real evidence-sufficiency script was `PASS-LIVE`: five Qdrant retrieval hits, Direct `gpt-4.1-mini`, one exact MIIT citation, and correct pre-LLM refusal for the no-evidence and three adversarial queries. Backend `356 passed`; Ruff passed; mypy reported no issues in 156 source files. Frontend lint/type-check, Vitest `18/18`, production build, and Playwright `10 passed, 1 skipped` passed. All eight Compose services were healthy; PostgreSQL accepted connections; Redis returned PONG; Qdrant, 8080 and `/api/system/health` returned HTTP 200. D: had 106.86 GiB free. Black was unverified at that checkpoint; the later Phase M isolated-cache/source-scoped run supersedes it with `BLACK=PASS-LOCAL`.
- 2026-08-12 Phase C formal endpoint canary: the deployed Coze HTTP workflow returned HTTP 200, `workflow_version=batch_crawl-v1`, `articles_discovered=5`, `articles_fetched=5`, and five distinct detail URLs for the bounded `https://www.scsia.org/newslist/1.html` request (`max_pages=1`, `max_articles=5`). This resolves the historical single-directory deployment mismatch and is **PASS-LIVE** transport evidence; it does not change the association trust classification.
- 2026-08-12 Phase C C1/C2 corpus checkpoint: all new rows were created through the normal authenticated API with provider `coze`, contract `batch_crawl`, manual review and real reindexing. No fixture, Local provider, direct SQL insertion, source-trust downgrade or historical row rewrite was used. C1 passed with at least ten newly approved official documents from multiple domains. C2 now has exactly 50 approved `government/official` documents with non-corrupt region metadata across 14 source rows and 11 domains. Global persisted totals are `documents=98`, `approved=51` (50 government/official plus the retained historical association document), `rejected=21`, `pending_manual_review=26`, `chunks=393`, `sources=28`, `crawl_tasks=128`, `reviews=160`, `lineage=539`, and `attachments=52`; direct Qdrant exact count is 393 and matches PostgreSQL chunks.
- 2026-08-12 Phase C Data Quality Gate: approved canonical URLs and content hashes each have zero duplicates. The approved government/official distribution spans `czt.sc.gov.cn` (12), `www.miit.gov.cn` (9), `fgw.sc.gov.cn` (5), `sthjt.sc.gov.cn` (5), `jst.sc.gov.cn` (4), `kjt.sc.gov.cn` (4), `dnr.sc.gov.cn` (3), `www.ndrc.gov.cn` (3), `wap.miit.gov.cn` (2), `zfxxgk.ndrc.gov.cn` (2), and `shxca.miit.gov.cn` (1). Reindexing document 98 was idempotent: document points stayed 4 and global Qdrant points stayed 393. Attachment text is not accepted at this checkpoint: all 52 downloads remain `parse_status=pending`, including one `requires_ocr=true` attachment.
- 2026-08-12 Phase C regression (historical checkpoint): the live evidence-sufficiency script preserved `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5`; backend `356 passed`, Ruff/mypy and frontend checks passed, all eight Compose services were healthy, and runtime dependencies were reachable. Black was unverified in that older Windows session; the later Phase M isolated-cache/source-scoped run supersedes it with `BLACK=PASS-LOCAL`. The minimal runtime image intentionally omits pip; the verified builder-stage `pip check` remains the dependency-consistency evidence.

- 2026-08-10 Phase B rerank and evaluation checkpoint: `RerankProvider` now returns validated ranking data plus safe usage/cost metadata; the engine has dedicated `ODIRAG_RERANK_TIMEOUT_SECONDS` and `ODIRAG_RERANK_FAILURE_POLICY=open|closed` settings. Default `open` preserves the exact fusion order on remote failures and exposes `rerank_applied=false`, stable redacted error codes, provider/model, candidate/reranked counts, latency, usage, and cost-measurement state. `closed` preserves the provider exception. Remote JSON, empty results, duplicate/out-of-range indices, non-finite/out-of-range scores, HTTP failures, transport timeouts, blank keys, and error redaction are covered by tests. No key, authorization header, provider response body, or secret is persisted.
- 2026-08-10 Phase B evaluation checkpoint: `POST /api/evaluations/run` now executes the requested `bm25`, `vector`, `hybrid`, or `hybrid_rerank` mode and actual top-k rather than storing a label. `POST /api/evaluations/matrix` resolves one verified question snapshot once and executes all four modes against it. Reports retain requested/executed mode and top-k, citation precision/recall denominators, answer-grounding denominators, and unsupported-answer denominators. A zero-denominator vector fixture is reported as unassessed, never as a quality success.
- 2026-08-10 Phase B PostgreSQL/container checkpoint: migration `0008_rerank_observability` non-destructively added `query_traces.rerank_metadata_json`; the real Compose PostgreSQL is at `0008_rerank_observability (head)` and `alembic check` reports no drift. Fresh backend image installed `alembic 1.18.5`; backend/worker/scheduler/frontend were recreated while PostgreSQL, Redis, Qdrant, and Nginx were preserved. All eight services are healthy; `/api/system/health` and `http://127.0.0.1:8080/` returned HTTP 200. A real authenticated `/api/search/debug` call returned 5 hits with `rerank_applied=false`, `provider=none`, and `rerank_provider_disabled` without reducing Hybrid availability.
- 2026-08-10 Phase B remote-rerank acceptance: **BLOCKED-LIVE**. The running container reports `rerank_provider=none`, `configured=false`, model `rerank-v3.5`, timeout `30.0`, and failure policy `open`. Therefore no remote rerank quality claim, latency/cost claim, or four-mode quality improvement claim is made. The only required external item is a reachable remote endpoint plus `ODIRAG_RERANK_PROVIDER=remote` and `ODIRAG_RERANK_API_KEY`; Phase C-F work that does not need it continues.
- 2026-08-09 Phase C bounded corpus checkpoint: the approved baseline remains 2 documents, 14 PostgreSQL chunks and 14 Qdrant points (8 documents total; 6 are rejected). Real Coze batch canaries were executed only through the normal authenticated API with `max_pages=1,max_articles=5`: task 24 (gov.cn JSON column) completed HTTP 200 with `0/0` discovered/fetched and `no_articles`; task 25 (JXT list) completed `1/1/1` but the sole directory page was rejected with quality `0.0`; task 26 (KJT list) likewise completed `1/1/1` and rejected the directory page; task 27 (existing KJT detail) failed with `COZE_CONTRACT_MISMATCH`. Raw and normalized invocation records remain persisted; no raw response or credential is copied here. The three list canaries plus the detail canary establish an external Coze contract blocker: the current deployment does not expand these official list pages and does not accept the KJT detail contract. Phase C therefore stops before creating a speculative corpus and before the 100-document cap; no fake/local provider or direct database insertion was used.
- 2026-08-10 Phase C generalized-crawl implementation checkpoint (historical): the local provider now performs deterministic same-site anchor normalization, explainable article candidate scoring, exclusion of navigation/assets, bounded pagination with visited-page/no-new guards, direct-detail fallback, common government detail selectors, attachment/image discovery, OCR-required metadata, SPA/JSON API hints and configured `site_rules`. `CrawlDiagnostics` persists page classification, candidate/normalized links, pagination events, API discovery and stable per-URL failure codes (`DETAIL_SCHEMA_UNKNOWN`, `PAGINATION_FAILED`, `SPA_API_NOT_DISCOVERED`, `SPA_API_REQUEST_FAILED`, `SOURCE_BLOCKED`, `RATE_LIMITED`, `ARTICLE_FETCH_FAILED`). Gov.cn retains its adapter and exposes the same diagnostics surface. Coze response parsing now canonicalizes relative article image/attachment URLs in a validation copy only; strict `BatchCrawlResponse` validation remains fail-closed and raw provider JSON is preserved unchanged. The historical backend regression was `356 passed`; the later Phase M Black result is `PASS-LOCAL`. This is VERIFIED-LOCAL/fixture-verified behavior only until a fresh authenticated live task returns real articles.
- 2026-08-10 Phase C live boundary (historical pre-generalization): task 24-27 evidence remains external workflow evidence. Task 27's exact contract error is six relative `image_urls` rejected by `HttpUrl`; no existing failed task was retroactively marked successful. At that time post-generalization C1 progress was `1/10`; the later 2026-08-12/13 canary and normal-path expansion superseded this historical gate.
- 2026-08-10 Phase C live canary checkpoint (historical): after the generalized backend rollout, normal authenticated Coze tasks 28-34 were run with `max_pages=1,max_articles=5`. Task 28 (KJT detail) returned strict schema-valid `1/1/1`, was manually approved, and produced document 9 (`government/official`, region `四川省`, quality `0.85`, HTML, word count `1619`). Its two attachments downloaded successfully but remain `parse_status=pending` with zero parsed text; attachment parsing is not claimed. Reindex generated 9 real `text-embedding-3-small` chunks/points; the repeat reindex returned 9 cache hits and Qdrant stayed at 23 points. Tasks 29/30/32 (JXT/KJT/KJT policy list pages) each produced one directory-page document and were rejected; tasks 31/33/34 (gov.cn JSON, MIIT list, gov.cn HTML) produced `0/0/0`; all invocations were HTTP 200/completed. Totals at that time were documents=10, approved=3, rejected=7, chunks=23, reviews=20, crawl_tasks=34, lineage=78, attachments=3. The later C1/C2/C3 checkpoints supersede the then-blocked C1 result.
- 2026-08-10 Phase C stop condition: independent list/API canaries across KJT, JXT, MIIT and gov.cn have now shown either directory-page misclassification or empty discovery. This is an external Coze deployment blocker, not a local crawler test failure. The minimum external action is to republish/deploy the batch workflow with list-to-detail expansion (or provide a compatible real detail-input contract); after that, rerun tasks through Source/CrawlTask, review, approve and index. C2/C3 remain pending and no speculative or fixture documents were added.
- 2026-08-10 Phase C redeploy canary (historical): task 35 reran the same KJT notification column (`source_column_id=3`) after the reported Coze republish with `max_pages=1,max_articles=5`. Invocation was HTTP 200/completed and strict `batch_crawl`, but it still returned exactly one article whose URL was the directory page `https://kjt.sc.gov.cn/kjt/gstz/newschild.shtml`; quality decision was rejected (`0.0`). No new document was created because the URL was already persisted. The required canary gate failed at that time; the later five-article endpoint canary resolved the deployment mismatch.
- 2026-08-10 Phase C raw-response confirmation (historical): task 36 repeated the same canary after the reported republish. The persisted raw `batch_result.articles` array itself contained exactly one item (not a local normalization loss), with `success=true`, `failed_urls=[]`, and the same directory URL; normalized output remained `1/1/1` and rejected. This was evidence of the then-current endpoint mismatch; no expansion or main-chain change was made at that checkpoint.
- 2026-08-10 Phase C endpoint alignment check (historical): task 37 used the correct KJT list source (`source_column_id=3`, expected `source_url`) but again persisted raw `articles` length 1 with the directory URL, `success=true`, and zero failed URLs. The task 36 and task 37 invocation records have identical endpoint/deployment identifiers and both report `workflow_version=batch_crawl-v1`. This recorded the then-current endpoint mismatch; no local code, environment secret, or main-chain behavior was changed.
- Historical Phase C blocker resolution required a republished batch workflow that discovered and fetched detail links from list pages. That blocker was resolved by the 2026-08-12 five-article endpoint canary and the subsequent C1/C2/C3 normal-path expansion; the failed tasks remain immutable negative evidence rather than the current status.
- 2026-08-09 Phase D source-discovery hardening: official candidate validation now requires an exact redirect host match (not merely a sibling/parent same-site match), an HTTP 2xx response, HTTPS, and a configured trusted suffix. Evidence persists `same_host` and `status_ok`; a sibling-subdomain redirect is rejected as `unverified`. Content-gap counts now exclude documents from disabled sources. Source-discovery unit/provider/API/scheduler regression is `19 passed`; the admin UI exposes official-validation evidence and fixture Playwright covers it. Brave Live remains **BLOCKED-LIVE** because `ODIRAG_SOURCE_DISCOVERY_API_KEY` is absent; no candidate or activated source was fabricated.
- 2026-08-10 Phase E supply-chain and deployment checkpoint: fresh builder image installed Alembic `1.18.5` and `python -m pip check` reported no broken requirements. Full and production-only `npm audit` both report 0 vulnerabilities. Docker Scout scanned current local images using SBOM metadata only: backend digest `b41a63d5b943` is `0C/0H/0M/0L` (133 packages); frontend digest `7dcc62cebccd` is `0C/0H/0M/3L` (Alpine libxml2 `2.13.9-r2`, CVE-2026-0989/CVE-2025-8732/CVE-2026-11979, no fixed version). Alembic is at `0008_rerank_observability (head)` with no drift; Compose config, PostgreSQL, Redis, Qdrant, worker ping, scheduler health, Nginx syntax, frontend, backend and all eight services passed locally. No high/critical vulnerability is claimed; the three low findings remain open pending a base-image fix. One real high latency alert remains open: RAG P95 `7184 ms` exceeds the `5000 ms` policy threshold.
- 2026-08-10 Phase F live matrix checkpoint: formal `POST /api/evaluations/matrix` created two verified `phase-f-live` questions and four persisted runs (BM25/vector/hybrid/hybrid_rerank) against the real MIIT official document, remote `text-embedding-3-small`, Qdrant and Direct `gpt-4.1-mini`. All modes retrieved the expected document/chunk; only `hybrid_rerank` returned the supported answer with one exact citation and correctly refused the no-evidence question. Its rerank provider was explicitly disabled, so this is not remote-rerank acceptance. BM25/vector/hybrid conservatively refused the supported question with `answer_contains_unsupported_relation`; their no-evidence refusal remained correct. The run is a two-question live plumbing check, not a representative quality/SLA benchmark. The persisted exact-answer-point string was stricter than the accepted generated wording, so answer-point coverage is `0.5`; the historical run was not rewritten to improve a metric.
- 2026-08-10 final Phase F regression: backend full suite `350 passed`; Ruff, Black (203 files), and mypy (155 source files) passed. Frontend lint, type-check, Vitest `18/18`, and the production build passed; Playwright reported `10 passed, 1 skipped` (the explicit live-stack skip is not a Live Acceptance claim). The current eight-service Compose stack remains healthy and both `http://127.0.0.1:8080/` and `/api/system/health` returned 200.

- 2026-08-09 Phase A Evidence Sufficiency PASS-LIVE: migration `0007_evidence_sufficiency` added a non-destructive `query_traces.evidence_decision_json` audit column and real PostgreSQL `alembic check` reports no drift. The gate runs after Hybrid/Rerank and before Grounding; only `supported_chunk_ids` reach Grounding/Direct LLM, every refusal returns zero citations, and post-answer validation rejects unsupported exact values, relations, scope targets, and answer shapes. Relation/entity and scope/applicability checks must bind inside the same chunk; official-only mode filters non-official context and citations. Chat/trace APIs, monitoring metrics, evaluation metrics, frontend inspection, and repeatable live scripts expose the decision without storing extra body text or credentials.
- 2026-08-09 Phase A supported-answer PASS-LIVE: trace `47c5b283-5e38-40f4-a7a3-1e684737671f` retrieved five real candidates, passed the gate, called Direct `gpt-4.1-mini` for 3,336 tokens, returned the correct MIIT APP-filing answer, and cited real chunk `0bf55b37-7bf1-5ce9-834a-f46754e84fec` with the exact official title and URL. `answer_support_validated=true` is persisted.
- 2026-08-09 Phase A non-empty-retrieval refusal PASS-LIVE: the Mars/dinosaur trace `b38598b2-89a3-4cd2-92b3-ee733b013f71` retrieved five candidates but scored evidence confidence `0.026316`; it returned `refusal=true`, reason `insufficient_evidence_relevance`, zero citations, zero Direct LLM tokens, and zero cost. Three additional live adversarial traces also retrieved five candidates and refused before Direct LLM: cancellation `e07f742b-fa91-4e52-bd5f-cd7de42d96fc` (`evidence_missing_required_relation`), original numeric question `APP备案罚款金额是多少？` trace `7b1434b2-a01f-4005-872c-bf98ce314667` (same reason; confirmed RAG rather than SQL), and unsupported WeChat mini-program scope `99cba6de-53db-42f1-8fbf-e127f9858fd9` (`evidence_missing_required_scope_target`). Historical rows were not altered.

- 2026-08-09 task 23 official-source PASS-LIVE: after the republished Coze deployment, source 9/column 9 used the real MIIT article URL with `max_pages=1`, `max_articles=5`. The real invocation returned HTTP 200 in one attempt/zero retries, persisted raw and normalized responses, `success=true`, strict string task ID `"23"`, `workflow_version=batch_crawl-v1`, 1 discovered, 1 fetched, 1 accepted article, 0 rejected/failed, and a non-empty `articles[]` array. Re-reading raw JSON from PostgreSQL inside the backend container and calling `parse_batch_crawl_response` passed the current Pydantic schema.
- 2026-08-09 official document evidence: document 6 (`868a6c55-5806-4237-875c-40163fa5b8e5`) is titled `工业和信息化部关于开展移动互联网应用程序备案工作的通知`, URL `https://www.miit.gov.cn/zwgk/zcwj/wjfb/tz/art/2023/art_920db564162e4312916a01bed6540ad8.html`, region `全国`, source metadata `government/official`, HTML extraction, `needs_ocr=false`, content length/word count 2,614, quality 0.95, and accepted. Existing `POST /api/reviews/6/approve` produced `manual_review_status=approve`, `final_status=approved`, task 23 completed, and pending review count 0.
- 2026-08-09 official indexing PASS-LIVE: first reindex generated 6 chunks, 6 real `text-embedding-3-small` embeddings, and 6 Qdrant points. Direct Qdrant scroll found payload `document_id/chunk_id/title/source_url/content/official_status=official`; task 23 acceptance-summary reports 1 document/6 chunks/collection exists/6 points. The second reindex returned 6 cache hits, 0 new embeddings, the same 6 point IDs, and unchanged counts. Global PostgreSQL/Qdrant now contain 14 indexed chunks/14 points across two approved documents.
- 2026-08-09 formal grounded-answer PASS-LIVE: query `存量APP备案阶段是什么时间？已完成网站备案手续的APP是否需要重复填报主办者真实身份信息？` produced BM25/vector/fusion/final counts 14/14/8/5, all final hits from the real official document. Formal `/api/chat` passed official grounding, called Direct `gpt-4.1-mini` with 3,205 prompt + 134 completion = 3,339 tokens, and returned `refusal=false`: `存量APP备案阶段为2023年9月至2024年3月；已完成网站备案手续的APP仅需补充完善APP信息，无需重复填报主办者真实身份信息；无网站备案信息的按规定履行备案手续。` Citation chunk `0bf55b37-7bf1-5ce9-834a-f46754e84fec`, title and URL exactly match the retrieval hit and real Qdrant payload.
- 2026-08-09 safe-refusal PASS-LIVE: both the prior zero-hit Guangdong query and the new non-empty-retrieval Mars/dinosaur regression now fail closed before answer generation. The latter proves retrieval count alone is not treated as evidence sufficiency.
- 2026-08-09 Phase A full regression: backend `324 passed`; Ruff passed, Black passed across 201 Python files, and mypy passed across 155 source files. Frontend lint/type-check/Vitest `18/18`/production build (1,850 modules) passed; fixture Playwright `9 passed + 1 skipped` and real 8080 live-stack `1 passed`. All eight Compose services are healthy, 8080 is reachable, task 23 acceptance-summary remains 1 document/6 chunks/6 points, and the existing 2 approved documents/14 chunks/14 Qdrant points remain usable through the formal cited-answer path.
- 2026-08-09 official-source rule audit (retained): grounding recognizes a hit as official only when indexed hit metadata contains the literal case-insensitive value `official_status="official"`. `organization_type`, domain suffix, and source-discovery evidence do not participate in the chat-time decision. Source discovery independently validates HTTPS/same-host/trusted suffix/official markers before activation, while manual `SourceCreate` accepts `official_status` without that validation; this remains a trust-model risk, not a reason to weaken grounding.
- 2026-08-09 official sources created through the authenticated Source API: source 6 `四川省科学技术厅政策法规` (`kjt.sc.gov.cn`, region `四川省`, government/official), source 7 `中华人民共和国工业和信息化部通知` (`www.miit.gov.cn`, region `全国`, government/official), source 8 `中国政府网最新政策` (`www.gov.cn`, region `全国`, government/official), and source 9 `工业和信息化部移动互联网备案通知` (`www.miit.gov.cn`, region `全国`, government/official). Browser inspection confirmed real body/list content and official government footers. PostgreSQL UTF-8 hex checks confirm the new region/name values are not `??`; no historical scsia.org row was modified.
- 2026-08-09 tasks 19-22 (historical pre-redeploy diagnostics): all four normal authenticated tasks returned HTTP 200 with persisted raw/normalized `NO_ARTICLES` responses and zero downstream records. They remain failure evidence for the prior deployment and are superseded for the same MIIT article by successful task 23.
- 2026-08-09 bounded selector diagnostic (historical pre-redeploy FAIL): the previous deployment ignored/failed the KJT selector and returned zero articles. The successful task 23 proves the republished article-input branch corrected the final blocker without local code changes.
- 2026-08-09 embedding/index/retrieval PASS-LIVE: after the local credential was corrected, document 3 reindex returned HTTP 200 with 8 chunks, 0 cache hits, 8 remote embeddings, model `text-embedding-3-small`, and 8 stable vector IDs. Direct Qdrant REST inspection found collection `odirag_chunks`, 8 points, and payloads containing `document_id`, `chunk_id`, `title`, `source_url`, and `content`; every payload `chunk_id` equals its point ID. The missing explicit `chunk_id` payload field found on first inspection was fixed in `vector_store/store.py` and covered by a direct adapter assertion. A second reindex returned 8 cache hits/0 new embeddings; PostgreSQL remained 8 distinct indexed chunks, Qdrant remained 8 points, and the sorted point-ID set SHA-256 was unchanged. Task 14 acceptance-summary now returns HTTP 200 with 5 documents, 8 chunks, `collection_exists=true`, and 8 points.
- 2026-08-09 retrieval/answer boundary (historical pre-Direct configuration; superseded by the final-gate entries above): real hybrid search for the fourth-batch software-product notice returned BM25/vector/fusion counts 8/8/8 and 5 final hits. The first `bm25+vector` hit is chunk `bd6cbbfc-6e6b-554e-b648-1a8bd63cf94d`, title `关于公布四川省 2026 年第四批软件企业及软件产品评估结果的通知`, URL `https://www.scsia.org/portal/new/7555`. Chat correctly refused with `official_source_required` because the source is explicitly `association`, not `official`. The key was absent at this historical checkpoint; it is configured now, and the provider-level strict AnswerResult call has passed. A query containing `四川省` returned zero hits because the persisted region metadata is the corrupted literal `??`; this remains an unchanged historical data-quality risk.
- 2026-08-09 runtime alignment (historical pre-Direct reload): worker and scheduler were recreated without touching PostgreSQL, Redis, Qdrant, or other services. Backend, worker, and scheduler use the same image `sha256:f6bf96c9385cecbe16938dc832427562e3d3440511366436696f4e4ac3d544b7`; current backend configuration now reports Direct LLM configured with `gpt-4.1-mini` and answer provider `llm`.
- 2026-08-09 embedding authentication failure (historical, superseded): before the local credential was corrected, `POST /api/documents/3/reindex` reached `https://api.openai.com/v1/embeddings` and received HTTP 401 on every provider retry. The API returned HTTP 503 `PROVIDER_UNAVAILABLE` without exposing credentials; PostgreSQL stayed at 0 chunks and Qdrant at 0 collections/points, with no deterministic fallback or partial vector write. This remains fail-closed evidence only; the successful PASS-LIVE result above supersedes it.
- 2026-08-08 pre-index checkpoint (historical): all eight services were healthy. Task 14 (`max_pages=1`, `max_articles=5`) reached task/current-stage/provider status `completed/completed/completed` with `provider_error=null`; Coze invocation was HTTP 200/completed with one attempt and zero retries, raw and normalized responses persisted, and strict `BatchCrawlResult` validation passed. It produced 5 discovered, 5 fetched and 5 documents: 1 accepted, 4 rejected, 0 pending and 0 failed. OCR re-extraction and quality re-evaluation were live-proven. At that checkpoint acceptance-summary correctly reported an empty index; the current indexed result is 8 chunks and 8 Qdrant points.
- 2026-08-06 Coze live diagnostic (NOT PASS-LIVE): the token is present only in the untracked local `.env`, and backend/worker/scheduler loaded `enabled=true`, `batch_workflow_configured=true`, `token_configured=true`, `contract=batch_crawl`. Task 4 reached the real endpoint and proved numeric `task_id` is rejected; task 5 proved the deployment returns `{"run_id":...,"batch_result":...}`; task 6 proved both local fixes against the real endpoint with HTTP 200 and a completed invocation. The inner result was `success=false`, warning `NO_ARTICLES`, and 0 discovered/fetched/documents/chunks/Qdrant points, so real content ingestion is still a failed acceptance result.
- 2026-08-07 Coze task 7 (REAL LIVE-DIAGNOSTIC, not content PASS-LIVE): the invocation returned HTTP 200 and `invocation_status=completed`; the persisted task reached `status=completed` with `provider_status=no_articles`, `accepted_count=0`, `discovered_count=0`, `fetched_count=0`, `success_count=0`, `failed_count=0`, `database_document_count=0`, `chunk_count=0`, and `qdrant_point_count=0`. The acceptance script reported `status=batch_result_empty` and exit code 1. This verifies the deployed transport and durable no-articles state, not successful source expansion.
- 2026-08-07 Coze task 8 (REAL LIVE-DIAGNOSTIC, not content PASS-LIVE): the new deployment returned HTTP 200 and invocation `completed` in 4,141 ms with one attempt and zero retries. The normalized response preserved string `task_id="8"` and `workflow_version=batch_crawl-v1`. The persisted task ended `partial_failed/provider_status=partial_failed` without a provider error; `pages_visited=1`, while discovered/fetched/accepted/rejected/pending/failed counts, persisted failures, documents, chunks, and Qdrant points were all zero. Warnings contain `SPA_API_NOT_DISCOVERED` and explicitly state that only base HTML was available and no API was discovered. Acceptance remained `batch_result_empty` with exit code 1.
- 2026-08-07 task 8 evidence cross-check: PostgreSQL contains one invocation and zero documents/chunks for the task; Qdrant still has zero collections; monitoring opened a `high_failure_rate` alert at severity `high` with observed `0.4` over threshold `0.2`. The focused regression suite passed `49` tests. Independent public-API checks returned HTTP 200 JSON with `total=69` and five rows for `https://scsia.org/portal/news/264?pageNum=1&pageSize=5`; the first row ID was `7587`, and `https://scsia.org/portal/new/7587` returned a data object whose `newsContent` length was 995. No article body is recorded in this repository.
- 2026-08-07 Coze task 9 (BOUNDED CRAWL PASS-LIVE): `raw_response_json=true` and `normalized=true`; normalized `task_id` is strict string `"9"`. Reading the raw response from PostgreSQL inside the current backend container and re-running `parse_batch_crawl_response` passed Pydantic validation with 5 articles, 5 discovered and 5 fetched. Results were 0 accepted, 5 rejected, 0 pending, 0 failed, and 0 provider failed URLs; task counters, normalized statistics and persisted result decisions agree. PostgreSQL contains 5 documents, 5 lineage rows, 0 chunks and 1 invocation.
- Task 9 content boundary: the first persisted document is titled “关于公布四川省2026年第六批软件企业及软件产品评估结果的通知” at `https://www.scsia.org/portal/new/7587`; it has `content_length=0`, `needs_ocr=true`, `extraction_method=image`, 9 images, decision `rejected`, and `index_status=pending`. Across all five documents, three are image/needs-OCR records with zero content length; the other two have content lengths 349 and 203. All five were rejected, no chunks were created, and Qdrant has zero collections/points. No body text or credentials are recorded here.
- Task 9 acceptance-summary boundary (historical): at that checkpoint `embedding_provider=remote` was configured without a key, but task 9 itself completed with `failed_count=0`; embedding was not part of crawl execution and was not used to relabel the crawl as failed. `live_accept_coze_batch.py` then received HTTP 503 because Qdrant returned 404 for the absent collection. The empty-collection mapping and later Embedding/indexing have both since been fixed and live-verified; qdrant-client 1.19 versus server 1.14 still emits a compatibility warning.
- 2026-08-08 task 13 historical race evidence: Coze returned HTTP 200, but local processing ended `TASK_STATE_CHANGED`. Source-column/row locking and queued-to-running handling were corrected; task 14 then completed. The `image_ocr` schema, duplicate-URL version refresh, and manual-review idempotency paths were also corrected.
- 2026-08-08 task 14 OCR/quality evidence: article metadata in order was `(0, image, needs_ocr=true, OCR_FAILED, rejected)`, `(0, image, needs_ocr=true, OCR_FAILED, rejected)`, `(5358, image_ocr, needs_ocr=false, ocr_performed, accepted, score=70)`, `(349, html, rejected, score=0)`, `(203, html, rejected, score=10)`. Document 3 changed from v1 length 0/image/rejected/score 0 to v2 length 5,358/image_ocr/accepted/score 0.70, proving OCR-triggered quality re-evaluation. Existing `POST /reviews/3/approve` made it approved; task 14 remained completed with pending count 0.
- 2026-08-08 indexing boundary (historical): two pre-credential reindex attempts returned HTTP 503 `PROVIDER_UNAVAILABLE`, followed by one credentialed-but-invalid HTTP 401 attempt on 2026-08-09. The corrected credential subsequently completed the live reindex, so neither missing configuration nor provider authentication is a current Embedding blocker.
- 2026-08-06：Docker Desktop 的 WSL 数据已迁移到 `D:\RAG\.docker\desktop-data`，`C:\Users\Lenovo\AppData\Local\Docker\wsl` 是指向该目录的 NTFS junction；原始静态备份和回滚副本均保留在 D 盘，未删除 VHD、Volume 或数据库。Docker Desktop 无损重启后 Linux Engine 恢复，八个 Compose 服务再次全部 healthy，8080 首页和 `/api/system/health` 均为 HTTP 200。
- 配置兼容：`ODIRAG_TRUSTED_PROXY_IPS` 现在在 pydantic-settings 2.14.2 下同时接受 JSON 字符串数组、历史逗号格式、空值和多余空格；非法 JSON、非字符串数组项和非法 IP/CIDR 以脱敏配置错误停止启动。宿主环境测试、`.env` 来源测试、最终镜像 CSV/JSON 容器测试和默认 Compose recreation 均通过。
- Alembic：正式依赖约束为 `alembic>=1.18,<1.19`，`backend/requirements.lock` 固定 `1.18.5`，Dockerfile 和 CI 都消费约束。fresh builder 实际安装 1.18.5，`pip check` 无破损；隔离 PostgreSQL 已完成 fresh upgrade/downgrade/upgrade；现有 PostgreSQL 已无损升级到 `0008_rerank_observability (head)` 且 `alembic check` 无漂移。
- 前端供应链：原 2 个 high 来自直接 dev dependency `@playwright/test` 经传递依赖 `playwright` 命中 GHSA-7mvr-c777-76hp（受影响 `<1.55.1`）；已精确升级至 1.55.1，无 major 升级。`npm audit` 和 `npm audit --omit=dev` 均为 0，`npm ls --all` 无 invalid/extraneous 必需依赖。
- 本轮最终测试：后端完整回归 `324 passed`；Ruff、Black（201 Python files）与 mypy（155 source files）通过；前端 lint、type-check、Vitest `18/18`、Vite build（1850 modules）通过；fixture Playwright `9 passed + 1 skipped`、真实 8080 live-stack `1 passed`。`81.33%` 仍是历史覆盖率基线，本轮未伪造新的覆盖率。Phase A 的正常回答、非空检索拒答和三类 adversarial 关系/范围拒答均已 PASS-LIVE。
- 供应链扫描历史基线（Phase A 前镜像）：backend `f6bf96c9385c` 与 frontend `2d41a3e3c971` 的 Docker Scout 结果为 `0C/0H/0M/0L`。该基线已被 2026-08-10 Phase E 的当前 digest 扫描取代：backend `b41a63d5b943` 为 `0C/0H/0M/0L`，frontend `7dcc62cebccd` 为 `0C/0H/0M/3L`；不可把旧结论套用于新镜像。
- 仍未通过的生产门禁：真实 Rerank 对照数据、Brave Live Acceptance、生产 TLS/secret manager、Redis ACL/failover、多副本/负载、CI green、签名 tag、registry provenance、附件解析/OCR 覆盖和完整人工 RAG 评估集。Phase C 的 100 篇阶段语料、知识库真实闭环及 Phase A 已通过；scsia.org 的 association 身份与损坏 region 元数据保持原样。
- 2026-08-05：Coze 批量抓取实现、数据库迁移 `0006_coze_task_operations`、失败 URL 重试、调用原始/规范化响应持久化、验收摘要 API 和前端任务详情已完成；本轮补齐共享 Redis 限流、显式 Local Provider worker 路径、可信代理边界、取消竞态保护、审核后 `waiting_review` 收敛、供应商 cost 防护、严格 Phase 16 事件顺序和镜像/SBOM 验收命令。
- 历史基线（已由 2026-08-06 最终复核替代）：后端曾记录 `210 passed`，前端曾记录 Vitest `16/16`；这些数字不代表当前门禁。
- 历史供应链基线（已解决）：旧 backend/frontend 镜像曾分别报告 2 critical/4 high 与 6 critical/27 high；当前镜像已改用 `python:3.12-alpine3.24`、`nginx:1.30.4-alpine-slim`，移除 runtime pip，并完成 Scout/npm 复扫。
- 最近一次本地 Compose 运行证据：2026-08-10 PostgreSQL、Redis、Qdrant、backend、worker、scheduler、frontend、Nginx 八个服务全部 healthy，8080 首页和健康接口均为 200；backend/worker/scheduler 使用同一镜像 `sha256:b41a63d5b943f200304f9ee6a1d208d7fee62ff3920b4f77a19c97f5f0ccf163`，frontend 为 `sha256:7dcc62cebccdf27f4283033b772d9cd38a4e9e1d1dd942f3baddb3a43314f04c`。这是 development 运行证据，不等于生产 TLS/registry acceptance。
- Coze current checkpoint：批量部署 URL 与 Token 只存在于本机未提交的 `.env`。Task 23 is the official-source PASS-LIVE checkpoint: one schema-valid MIIT document, accepted/approved/indexed, 6 chunks/6 task points, formal Direct citation and zero-hit refusal. Tasks 9/13/14 remain historical association/race/OCR evidence. Only broader production release gates remain open.
- 隔离 API 冒烟：临时 Uvicorn + SQLite + deterministic provider 下，`/api/system/health` 返回 HTTP 200（database healthy、Redis unavailable、Qdrant disabled），管理员登录、Coze 状态、来源列表和抓取任务列表均 HTTP 200；临时数据库与日志已清理。

## Assumptions

- The empty `D:\RAG` directory is the intended repository root.
- The initial host audit observed Python 3.14.6; the current repository-local backend venv used for final checks is Python 3.13.7, while the container runtime is based on Python 3.12. The package supports Python 3.11+.
- PostgreSQL remains the production business database; SQLite is permitted only for deterministic local tests and degraded development startup.
- External LLM, embedding, rerank, Qdrant, Redis, and live-site integrations must report unavailable until configured and must never return fabricated production results.
- The supplied master execution guide is the approved product design and phase plan.
- The required open-source license was selected as MIT because the guide mandates a LICENSE but does not prescribe a license family; this choice is recorded in `LICENSE` and can be changed before publication.

## Environment Audit

| Tool | Result |
| --- | --- |
| Repository contents | Empty at audit time |
| Python | Initial host 3.14.6; final backend venv 3.13.7; container base Python 3.12 |
| Node.js | 24.18.0 |
| npm | 12.0.0 |
| Git | 2.52.0; initialized after audit, but sandboxed `.git` writes require elevation |
| Docker | Docker Desktop 4.85.0 / Engine 29.6.2 / Compose v5.3.1; WSL data active on D drive through a junction; all eight development services healthy; current backend Scout 0 vulnerabilities and frontend Scout 3 unresolved low libxml2 CVEs |
| ripgrep | 15.2.0 |

## Phase Checklist

| Phase | Status | Implemented Features | Commands Run | Test Results | Coverage | Known Issues | Blocked External Integrations | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Repository Audit | Complete | Empty-workspace audit; Git initialization; toolchain verification; assumptions recorded | `Get-ChildItem -Force`; version checks; `git init` | Audit complete | N/A | Production credentials/config and `.git` checkpoint writes remain restricted | Production runtime evidence | Preserve baseline |
| 1 - Infrastructure and Core Backend | Complete | FastAPI factory; settings; SQLAlchemy async database; all required core models; Alembic migration; JWT admin auth; structured errors/logging; metrics; dependency health; Celery bootstrap; Docker/CI/deployment baseline | Ruff; Black; mypy; pytest with coverage; SQLite migration; local PostgreSQL `alembic current/heads/check`; Uvicorn health smoke | 32 unit tests passed; migration passed; smoke endpoint passed; lint/type checks passed | 81.76% | Production secret manager, backup/restore, and production topology remain unverified | Production credentials and release environment | Implement Phase 2 vertical slice |
| 2 - Source Management and Crawling | Complete | YAML source configuration; source CRUD/test; adapter registry; generic HTML and gov.cn JSON adapters; URL normalization; retries/timeouts/rate control; task state machine; Celery dispatch; fixture pagination/detail/attachment path; idempotent document persistence | Ruff; Black; mypy; unit/integration tests; fixture smoke | 41 tests passed; lint/type checks passed; fixture end-to-end crawl passed | 80.48% | Live gov.cn page and JSON endpoint were identified, but the 10-article run was blocked by external approval quota | Live 10-article verification | Implement Phase 3 parsing pipeline |
| 3 - Parsing, Cleaning, Deduplication, Versioning | Complete | HTML structure/table extraction; PDF pages/header-footer reduction/OCR flag; DOCX headings/tables/hyperlinks; XLSX sheets/Markdown/JSON rows; TXT decoding; ZIP metadata/path flags; cleaning; SHA256; SimHash; authoritative duplicate selection; document snapshots; changed fields; stale indexes; lineage | Ruff; Black; mypy; unit/integration tests | 50 tests passed; parser samples and version/lineage integration passed | 80.64% | OCR execution is not bundled; documents are flagged for OCR | OCR engine | Implement Phase 4 review pipeline |
| 4 - Filtering, LLM Review, Structured Knowledge | Complete | Configurable hard/soft filtering and reason codes; prompt immutability/versioning; Direct and Coze adapters; strict JSON; three-attempt retry; raw responses; manual review; 12 allowed structured fields; evidence-quote binding; provenance metadata | Ruff; Black; mypy; unit/integration tests | 56 tests passed; retry/raw response/evidence/manual review integration passed | 82.88% | Live LLM calls not verified without credentials | Coze/direct LLM credentials | Implement Phase 5 indexing pipeline |
| 5 - Chunking, Embedding, Indexing | Complete | YAML-configured heading/paragraph/list/table-aware chunking with semantic fallback; document and parsed-attachment/page chunks; stable versioned UUID point IDs; batching, cache, retry, rate/cost metadata; Redis cache adapter; Qdrant collection creation, dimension validation, payload indexes, filters, idempotent upsert/deletion and retryable cross-store cleanup; chunk/vector lineage; JSON BM25 snapshots and rebuild command | Ruff; Black; mypy across 108 source files; unit/integration tests; SQLite Alembic smoke; `scripts/rebuild_bm25.py` smoke | 62-test phase checkpoint plus current OpenAI/Qdrant live reindex | 82.82% historical phase coverage | Selected remote Embedding, Redis cache, PostgreSQL chunks and Qdrant upsert/payload/idempotency are live-verified; live delete/compensation and backup/restore remain | Production topology and failure drills | Implement Phase 6 retrieval engine |
| 6 - Retrieval Engine | Complete | Shared provider runtime; BM25 snapshot loading; query normalization, term analysis and inferred/explicit metadata filters; BM25/vector/hybrid/hybrid+rerank modes; normalized BM25 scores; Qdrant and in-memory filter parity; bounded RRF; validated rerank outputs; thresholds/final context selection; stage timings, warnings and config snapshots; authenticated search and admin debug APIs; document reindex/chunk APIs connected to shared live indexes | Ruff; Black; mypy across 114 source files; unit/integration/API tests | 68-test phase checkpoint plus current hybrid BM25/vector/fusion 8/8/8 live result | 85.02% historical phase coverage | Embedding/Qdrant retrieval is live-verified for the selected path; live rerank and provider failure/latency drills remain | Rerank credential and target failure drills | Implement Phase 7-8 routing and grounded answers |
| 7 - SQL / RAG / Composite Router | Complete | Deterministic query classification; inferred and explicit validated filters; SQLAlchemy-only approved-document count templates; no generated SQL; RAG and SQL+RAG execution; authenticated chat API | Ruff; Black; mypy; unit/integration/API tests | SQL, RAG, and composite routes passed including date/region filters and injection-resistant whitelist behavior | 85.11% shared checkpoint | Structured SQL support currently covers approved-document counts required by the guide example | None | Extend analytics only when verified use cases require it |
| 8 - Grounded Answering and Citations | Complete + Phase A hardened | Independent Evidence Sufficiency Gate; same-chunk entity/relation and scope binding; strict corpus-count routing; supported-chunk and official-only filtering; conflict/freshness policy; fail-closed refusal; strict Direct AnswerResult; per-claim post-answer exact-value/relation/scope/citation validation; persisted gate trace and metrics | 324-test backend suite; A-H plus adversarial evidence/router/claim cases; real task 23 formal `/api/chat`; Mars/cancellation/penalty/scope non-empty-retrieval regressions; direct trace/Qdrant mapping | Direct `gpt-4.1-mini` returned a schema-valid official answer with one exact citation; four insufficient queries each had 5 candidates but refused before LLM with 0 citations/tokens/cost | 81.33% historical coverage baseline | Deterministic gate still needs broad human evaluation across the staged corpus | Phase B/F evaluation corpus | Preserve Phase A invariants while expanding retrieval evaluation |
| 9 - Evaluation and Benchmark | Complete | Persisted manually verified questions; real ChatService-backed benchmark runner; document/chunk hit rate, Recall@1/5/10, MRR, nDCG@10, answer-point coverage, citation accuracy/completeness, refusal accuracy, explicitly scoped hallucination rate, P50/P95 latency, token and cost metrics; per-question errors; atomic JSON/CSV/Markdown/chart-ready reports; authenticated run/list/detail/report APIs; fixed local demo benchmark | Ruff; Black; mypy across 132 source files; full unit/integration suite; real reindex -> evaluation API integration | 83 tests passed; verified metrics and all four report artifacts generated from actual traces; no hard-coded metric values | 83.43% shared checkpoint | Hallucination measurement is explicitly limited to citation claims validated against stored chunk quotes; the demo benchmark uses document/answer-point relevance while chunk-specific relevance is covered by indexed API tests | Live LLM token/cost and provider behavior require configured credentials | Implement Phase 10 experiments |
| 10 - Experiments and Regression | Complete | Strict YAML experiment configuration; independent per-variant chunking, overlap, embedding, BM25/vector indexes, top-k, RRF, metadata filters, rerank, score threshold and prompt-version application; baseline/candidate evaluation runs linked to experiments; metric deltas, regression gates, failed cases and conclusions; atomic JSON/Markdown/chart reports; create/list/detail/run/compare APIs; trusted runner plugin loading; executable local demo runner | `python scripts/run_experiment.py --config data/experiments/chunk_600_vs_800.yaml`; Ruff; Black; mypy; unit/integration/API tests | Guide example command completed and produced real comparison artifacts; API regression test detected an intentionally degraded metadata-filter candidate | 83.43% shared checkpoint | Remote model variants fail honestly when credentials/providers are unavailable; generated experiment run artifacts are ignored by Git | Remote embedding, rerank and LLM credentials | Implement Phase 11 observability |
| 11 - Trace, Lineage, Monitoring, Alerts | Complete | Full query trace including prompt snapshots; answer-to-citation-to-chunk-to-document-version-to-crawl-task-to-source traversal; crawl and index lineage propagation; evaluation-run lineage for retrieved chunks; crawler, knowledge, RAG, dependency and cost metrics; persisted alerts for crawl failure, index failure, unavailable services, latency regression, evaluation regression and abnormal cost; acknowledge/resolve lifecycle; scheduled alert refresh | Ruff; Black; mypy across 136 source files; targeted observability/evaluation integration tests; full unit/integration suite; `alembic upgrade head` fresh-database smoke through `0002_observability_alerts` | 85 tests passed; lineage traversal, prompt snapshots, operational metrics, all six alert types, lifecycle transitions and evaluation-run lineage verified | 82.98% | Repeated refresh intentionally reopens an active condition after manual resolution; alert thresholds are environment-configurable | Live dependency availability and provider cost telemetry require configured services/credentials | Build Phase 12 Vue console |
| 12 - Vue Frontend | Complete | Vue 3 + TypeScript management console; typed API client; auth/session handling; dashboard, sources, crawl tasks, documents, review, chat/citations/evidence-decision inspection, evaluations, experiments, monitoring, activity, and source-discovery views | npm lint; type-check; Vitest; production build; fixture Playwright; explicit live-stack gate | 18 Vitest tests passed; 9 fixture Playwright tests passed; real 8080 live-stack 1 passed with the official MIIT cited answer; Vite build passed | N/A | HTTPS/target production browser policy remains unverified | Production TLS/target host | Preserve official and refusal browser regressions |
| 13 - Feedback Loop | Complete | Helpful/not-helpful feedback API; validation; feedback-to-verified-evaluation conversion; helpful feedback conflict guard; frontend feedback controls and activity integration; logout token revocation | Backend unit/integration suite; frontend Vitest; real browser feedback flow | Feedback persistence and conversion passed; positive-feedback conversion rejected with 409; logout behavior covered | 82.87% shared checkpoint | Positive feedback is intentionally not convertible to a regression case | None | Preserve feedback regression tests |
| 14 - Security, Reliability, Performance | Complete | Shared Redis fixed-window rate limiting with Lua-atomic counter/expiry and fail-closed 503; bounded Redis connect/read timeouts; IP-only identity with explicit trusted-proxy CIDRs; unified 429 responses; JWT token-version rotation/revocation; production configuration checks; SSRF-safe DNS and redirect validation; streamed response limits; atomic crawl task claims and stale recovery that excludes manual `waiting_review`; atomic local/Coze cancellation guards with CAS on both worker stages and cancel requests; Celery late-ack/recovery settings; crawl uniqueness migration; bounded route/DB latency metrics; authenticated load-test reports; frontend DB P95 and route latency views | Ruff; Black; mypy; 210-test full suite; rate-limit tests with fake Redis/proxy cases; migration smoke; frontend lint/type/test/build; authenticated async load test; mobile/desktop browser QA; local Compose Redis key/header check | 210-test full backend suite passed; Redis limiter contract, timeout propagation, forged-token resistance, trusted-proxy handling and fail-closed behavior passed; local and Coze cancellation race regressions passed, including stale-cancel CAS; waiting-review recovery and review convergence passed | Coverage baseline remains historical; live Redis ACL/failover and multi-instance fairness remain unverified | Production Redis ACL, failover, ingress policy and remote model providers remain unverified; generic distributed locks are still DB-based | Run target Redis failure/ACL/failover and multi-replica tests |
| 15 - Docker, CI/CD, Handoff | Complete locally; external release gates pending | Auto-migration/non-root writable backend image; persistent Compose dependencies; shared Redis rate-limit configuration; worker/scheduler health and migration ordering; real API demo initializer; startup scripts; CI/deployment/docs handoff; honest demo seed; Python 3.12 Alpine/Nginx 1.30.4 base-image hardening; runtime pip removal; constrained builder; SBOM/CVE checklist | final backend/runtime and builder builds; `pip check`; `docker compose config --quiet`; eight health checks; PostgreSQL/Redis/Qdrant checks; worker ping; 8080/Nginx/API; npm audit; Docker Scout | final builder installs Alembic 1.18.5 and has no broken requirements; CSV/JSON config passes in container; all eight services healthy; npm audit 0; backend Scout 0 vulnerabilities and frontend Scout has 3 unresolved low libxml2 CVEs | Coverage baseline remains historical; GitHub Actions was not executed in this workstation checkpoint | Production secret/TLS, registry provenance/signing, CI green, target-host persistence and disaster recovery remain unverified | Production credentials, target host, registry/CI permissions | Execute target release pipeline and retain signed digest/provenance evidence |
| 16 - Production Readiness and Autonomous Source Discovery | Complete in code/local/fixture verification; official-source live closed loop 5/5; Phase A hardened | Full Phase 16 chain plus Coze batch contract, raw/normalized audit, OCR, manual review, real embedding/Qdrant, Hybrid/Direct citation, independent evidence gate and safe refusal | 356-test regression; PostgreSQL/Compose; task 23; real OpenAI/Qdrant/Hybrid/Direct traces; non-empty-retrieval and adversarial relation/scope refusal traces | Eight services healthy; 101 approved docs/821 chunks/821 points; official citation and evidence sufficiency both PASS-LIVE | **PASS-LIVE 5/5 + Phase A** | Rerank, Brave, attachment parsing/OCR and production/release gates remain; association and historical `??` unchanged | Complete external gates | Overall release still not accepted |
| Production C - staged official corpus (bounded to 100) | **C1/C2/C3 PASS-LIVE** | Normal Coze batch path, manual review and real reindex path; no speculative insertion | Formal 5/5 endpoint canary; authenticated tasks through 221; direct PostgreSQL/Qdrant audit; repeat reindex; 5/5 regression | Exactly 100 clean government/official approved documents; 821 indexed chunks/points; 0 approved URL/content duplicates; 10 domains | 46 documents still await manual review; 123 attachments are not accepted as parsed; three Coze network failures remain; API/embedding cost telemetry is incomplete | Preserve checkpoint and address external gates | Preserve main-chain and Data Quality Gate |
| Production D - source discovery trust | VERIFIED-LOCAL / **BLOCKED-LIVE** search | Exact-host/2xx/HTTPS/suffix validation, disabled-source gap exclusion, approval before activation, UI evidence | 19 focused backend tests; fixture Playwright | Local contract passes; real Brave run was not fabricated | Brave key absent; manual Source API can still set `official_status` and remains a governance risk | `ODIRAG_SOURCE_DISCOVERY_API_KEY` plus approved live run | Retain manual approval and audit evidence |
| Production E - deployment and supply chain | VERIFIED-LOCAL | Fresh builder `pip check`; Alembic head/check; npm audit; current Scout; Compose health | 350 backend tests; frontend lint/type/Vitest/Playwright; eight live local services | Backend `0C/0H/0M/0L`; frontend `0C/0H/0M/3L`; high RAG latency alert remains open | Target TLS/secrets/CI/registry/provenance and base-image low-CVE fix unavailable locally | Target environment and release credentials | Do not close the latency alert without measured remediation |
| Production F - live evaluation matrix | PASS-LIVE plumbing / quality-limited | Formal four-mode matrix over two verified official-document questions | Runs 1-4 plus persisted traces, reports and lineage | Hybrid-rerank mode returned exact official citation and safe refusal; rerank provider was disabled | Three modes conservatively refused the support query; n=2 cannot establish quality or SLA | Human-reviewed representative corpus and remote rerank if required | Keep results as baseline, not a release-quality claim |

## Command Log

- `Get-ChildItem -Force`
- `python --version`
- `py -0p`
- `pip --version`
- `node --version`
- `npm --version`
- `docker --version`
- `docker compose version`
- `git --version`
- `git rev-parse --show-toplevel`
- `rg --version`
- `backend/.venv/Scripts/ruff.exe check app tests`
- `backend/.venv/Scripts/black.exe --check app tests`
- `backend/.venv/Scripts/mypy.exe app`
- `backend/.venv/Scripts/pytest.exe tests/unit -q --cov=app --cov-report=term-missing`
- `ODIRAG_DATABASE_URL=sqlite+aiosqlite:///./phase1-check.db alembic upgrade head`
- Uvicorn process smoke test against `GET /api/system/health`
- Phase 2 Ruff, Black, and mypy checks across 77 source files
- Phase 2 unit/integration suite: 41 passed, 80.48% coverage
- Fixture crawl smoke: list -> details -> attachment -> persistence -> repeated-run deduplication
- Phase 3 parser, cleaning, deduplication, versioning, and lineage suite: 50 passed, 80.64% coverage
- Phase 4 filtering, prompt, LLM review, manual review, and structured knowledge suite: 56 passed, 82.88% coverage
- Phase 5 Ruff and Black checks; mypy across 108 source files
- Phase 5 unit/integration suite: 62 passed, 82.82% coverage
- Phase 5 approved document -> attachment-aware chunks -> embeddings -> vector store -> BM25 snapshot integration
- Phase 5 SQLite migration plus `scripts/rebuild_bm25.py` command smoke
- Phase 6 Ruff and Black checks; mypy across 114 source files
- Phase 6 unit/integration suite: 68 passed, 85.02% coverage
- Phase 6 API smoke: approved document -> reindex -> BM25/vector/RRF/rerank -> debug trace
- Phase 7-8 Ruff and Black checks; mypy across 118 source files
- Phase 7-8 unit/integration suite: 72 passed, 85.11% coverage
- Phase 7-8 API smoke: SQL/RAG/composite chat -> evidence checks -> citations/refusal -> stored trace
- Phase 9-10 Ruff and Black checks across 159 application/test files; script checks passed
- Phase 9-10 mypy across 132 source files
- Phase 9-10 unit/integration suite: 83 passed, 83.43% coverage
- Phase 9 real demo API: approved document -> reindex -> verified questions -> actual chat traces -> JSON/CSV/Markdown/chart reports
- Phase 10 API: independent baseline/candidate indexes -> evaluation runs -> metric deltas -> regressions/failed cases/conclusion
- `backend/.venv/Scripts/python.exe scripts/run_experiment.py --config data/experiments/chunk_600_vs_800.yaml` completed with generated comparison artifacts
- Phase 11 fresh migration smoke: `0001_core_schema -> 0002_observability_alerts`
- Phase 11 targeted integration: prompt snapshot and complete answer lineage; operational metrics and six persistent alert types; evaluation-run-to-retrieved-chunk lineage
- Phase 11 Ruff and Black checks across 167 application/test/migration files; mypy across 136 source files
- Phase 11 unit/integration suite: 85 passed, 82.98% coverage
- Phase 12 frontend: lint, type-check, 6 Vitest tests, production build, and authenticated mobile/desktop browser QA
- Phase 13 feedback: persistence, negative-feedback conversion, helpful-feedback conflict, and logout revocation verification
- Phase 14 fresh migration smoke: `0001_core_schema -> 0002_observability_alerts -> 0003_crawl_reliability`, downgrade to `0002`, then re-upgrade
- Phase 14 backend suite: 119 passed, 82.87% coverage; Ruff/Black passed; mypy passed across 143 source files
- Phase 14 load test: 20 search and 20 chat requests at concurrency 4 with zero errors; search P95 29.49 ms, chat P95 345.95 ms, DB P95 183.83 ms
- Phase 14 monitoring browser QA: DB P95 and route P95 verified at 390x844 and 1280x720 with no horizontal overflow
- Phase 15 documentation audit: 26 required documents present; all 12 numbered learning documents contain the required 12 sections, five interview Q&A, five defense Q&A, code-reading route, and exercise; relative links and referenced project paths resolve
- Phase 15 seed smoke: default nested SQLite parent creation and idempotency passed; no fabricated chunks, traces, alerts, evaluation metrics, or completed experiment conclusions are inserted
- Phase 15 real deterministic demo: two approved documents -> six chunks -> BM25/vector runtime -> RAG chat -> stored citations/trace -> one-question evaluation report; Recall@1/5/10, MRR, nDCG, answer coverage, citation accuracy/completeness, and refusal accuracy all measured at 1.0; P50/P95 4 ms
- Phase 15 final backend regression: 120 passed, 82.89% coverage; frontend 6 tests passed and production build passed
- Phase 15 migration smoke: fresh `0001 -> 0002 -> 0003`, downgrade to `0002`, then re-upgrade to `0003` passed
- Phase 15 static deployment smoke: Compose service set and CI YAML parsed; PowerShell/shell startup and container entrypoint were syntax-checked
- Phase A backend static checks: Ruff passed; Black passed for 201 Python files; mypy passed for 155 source files; full suite 324 passed.
- Coverage baseline regression: 257 passed with `81.33%` total coverage (`--cov=app --cov-report=term`); the current non-coverage full regression is 265 passed.
- Focused crawler/source regression: `tests/unit/test_sources_and_crawler.py`, 8 passed; unsafe inline crawl returns structured 422 and persists a failed task.
- Explicit Local Provider worker-contract fixture and legacy Coze column-task guard: 3 passed.
- Phase 16 targeted source-discovery/config/API checks: 28 passed
- Phase A Alembic: formal dependency remains constrained to `>=1.18,<1.19` and locked at `1.18.5`; existing PostgreSQL upgraded non-destructively to `0007_evidence_sufficiency (head)` and `check` passed. The prior isolated round-trip remains valid historical evidence.
- Phase 16 frontend: lint, type-check, 18 Vitest tests, Vite build (1850 modules) passed; task acceptance summary and independent legacy/batch status assertions included
- Phase 16 Playwright: serial 9 fixture tests passed, 1 live-stack test skipped without `E2E_LIVE=1`; concurrent first run had one worker-resource failure and was not used as the acceptance result.
- Phase 16 historical local Compose acceptance (previous base images): PostgreSQL/Redis/Qdrant/backend/frontend/Nginx/worker/scheduler were all healthy; Redis PONG, backend Redis ping=True, shared `odirag:ratelimit:*` keys, worker inspect ping and real `ping.delay()` passed; scheduler emitted recovery/monitoring tasks; Qdrant health passed but had zero collections; Nginx `/healthz`, `/`, and `/api/system/health` returned 200 with security headers. This evidence does not verify the current hardened images.
- 2026-08-05 current Compose recovery: stopped only the unresponsive Docker Desktop processes, `wsl --shutdown` then succeeded, Docker Desktop restarted from its discovered user installation, and Docker Engine became ready without data deletion. Restored missing `postgres`/`redis`/`qdrant` service aliases on `odirag_default`; all eight services then became healthy and remained healthy in the final stability check. PostgreSQL/Alembic, Redis, Qdrant health, worker ping, scheduler dispatch, Nginx/frontend/API, authenticated browser login/dashboard and acceptance-summary checks passed with no browser console warning/error; Qdrant collections remain 0. This recovery does not count as a clean one-command `up -d` acceptance because dependency aliases required repair.
- 2026-08-05 fresh image checkpoint (historical): pydantic-settings 2.14 initially rejected the Compose CSV proxy value and the temporary workaround used JSON. The compatibility implementation and normal CSV recreation were completed on 2026-08-06.
- 2026-08-05 Alembic dependency A/B (historical): fresh Alembic 1.19.0 showed constraint-name drift while 1.18.5 did not; the formal `<1.19` constraint and lockfile now prevent that unverified toolchain from entering the build.
- 2026-08-05 isolated PostgreSQL restore: a 156,455-byte custom-format dump was restored into a `--network none` temporary PostgreSQL container backed by a uniquely labeled temporary volume. Nine critical table counts matched; SHA-256 was recorded under ignored `data/reports/acceptance/`; the temporary container and volume were confirmed absent afterward.
- 2026-08-05 real Compose Playwright: login, sources, documents and chat navigation succeeded; cited-answer assertion failed because `embedding_provider=remote` has no configured key and the UI returned `A required provider is unavailable`. This is a provider/corpus acceptance blocker, not a fabricated browser pass.
- 2026-08-05 supply-chain gate (historical): fresh frontend builder output reported 2 high vulnerabilities and external scans were deferred pending authorization. Authorization was subsequently granted; the 2026-08-06 final npm/Scout results are zero.
- 2026-08-06 compatibility remediation: pydantic-settings 2.14.2 accepts JSON, CSV, empty, and whitespace-trimmed trusted-proxy values through `NoDecode` plus a redacting validator; targeted environment/dotenv/container tests passed and normal Compose recreation uses the historical CSV value successfully.
- 2026-08-06 migration remediation established the 1.18.5 constraint and isolated round-trip through `0006`; on 2026-08-09 the existing database advanced to `0007_evidence_sufficiency (head)` and still has no generated operations.
- 2026-08-09 final code regression (historical): backend 265 passed in 47.61 seconds; Ruff/Black/mypy passed (206 formatted files including migrations/154 typed source files). Frontend lint/type-check/Vitest 18/build passed and fixture Playwright 9 passed plus 1 explicit live skip. Coverage was not rerun; 81.33% remains the historical 257-test baseline. Historical reindex failures confirm fail-closed behavior; the corrected real reindex and current Phase M Black gate now pass.
- 2026-08-06 supply-chain remediation: direct dev dependency `@playwright/test` and transitive `playwright` were pinned to 1.55.1, closing GHSA-7mvr-c777-76hp without a major upgrade. Both npm audit modes report zero. Final backend builder `pip check` passed with Alembic 1.18.5. Docker Scout reports 0C/0H/0M/0L for final backend digest `dd27a657d1bf` (133 packages) and frontend digest `2d41a3e3c971` (26 packages); builder digest is `cd7bcad2eceb`.
- 2026-08-06 Docker data relocation: active WSL VHDs are on D through a verified NTFS junction; initial backup, rollback snapshot, and failed blank-disk quarantine are retained under ignored `D:\RAG\.docker`. Current active data survived Docker Desktop stop/start and eight-service recreation; no Docker data, project volume, or database was deleted.
- Coze batch current evidence: task 14 completed with strict schema-valid 5 discovered/fetched/documents, 1 accepted and 4 rejected. The third document's refreshed OCR version changed from empty image/rejected to length 5,358 image_ocr/accepted and was then approved. Task 9 remains the historical first bounded persistence PASS-LIVE checkpoint; task 13 remains the historical HTTP-200-then-`TASK_STATE_CHANGED` race checkpoint.
- Phase 16 reports/checklist generated: `PRODUCTION_READINESS_REPORT.md` and `PRODUCTION_ACCEPTANCE_CHECKLIST.md`; production verdict remains NOT ACCEPTED pending live evidence
- scsia.org example: task 14 persisted five current documents. Two image records still report `OCR_FAILED` and remain rejected; the third was re-extracted by OCR to length 5,358 and accepted, while the two HTML records of lengths 349/203 remain rejected. This remains association-path OCR evidence; task 23 separately completed official indexing and cited-answer acceptance.

2026-08-06 unattended source-discovery scheduler: added opt-in Beat gap scans with CSV/JSON/empty topic parsing, case-insensitive topic deduplication, a five-minute minimum interval, active/recent-run guards, queue-failure audit events, safe error-type logging, and SQLite integration coverage. The task remains proposal-only and never auto-activates a source; real Beat delivery and Brave-backed runs remain unverified.

## Known Issues

## Phase K checkpoint (2026-08-13)

- Historical real RAG traces: 69; all-RAG P50/P95/P99-max = `1556/7184/8041 ms`; answered = `5873/7424/7424 ms`; refused = `1465/5099/8041 ms`. `RAG_P95_LT_5000MS=FAIL-LIVE`; no optimization was applied without a human-verified evaluation denominator.
- Added non-invasive `query_traces.stage_timings_json` and migration `0010_query_trace_stage_timings`. New traces record routing, retrieval stages, Evidence Sufficiency, Grounding, Direct LLM, citation validation and total latency. SQLite upgrade/downgrade/upgrade/check and 12 targeted tests pass; Ruff, mypy (158 files) and source-scoped Black pass.
- Real PostgreSQL migration, no-drift check, minimal backend rebuild and supported/refusal trace persistence are **PASS-LIVE**. Existing 5/5 data and all corpus/index counts remain unchanged.

## Phase L checkpoint (2026-08-13)

- Development Compose runtime is verified locally: 8 services healthy, 8080 HTTP 200, dependency health healthy, Redis PONG/AOF healthy, PostgreSQL/Qdrant counts preserved, D: approximately 106.7 GiB free.
- Production engineering status is **PARTIAL / NOT PRODUCTION ACCEPTED**. Missing or unverified: automated encrypted PostgreSQL backups/PITR, Qdrant snapshots and restore, Redis recovery/HA, retention, resource limits, log rotation/central collection, external alert routing, production TLS/secret manager/network ACLs, and failure drills.
- Details: [`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md), [`DISASTER_RECOVERY_REPORT.md`](DISASTER_RECOVERY_REPORT.md), [`SECURITY_READINESS_REPORT.md`](SECURITY_READINESS_REPORT.md).

## Phase M checkpoint (2026-08-13)

- Final verdict: **NOT PRODUCTION ACCEPTED**; `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE` remains intact.
- Backend full regression is `370 passed`; Ruff, Ruff format, mypy and Black pass (158 typed source files; 227 Ruff-formatted files; Black checked 219 backend files plus the two changed scripts). SQLite and real PostgreSQL migration checks through `0010_query_trace_stage_timings` pass. Frontend lint/type-check, Vitest `18/18`, production build, Playwright `10 passed/1 expected skip`, and both npm audit modes pass/zero vulnerabilities. The local Git checkpoint is blocked by `.git` ACLs rather than an active lock.
- Final acceptance blockers and exact evidence are in [`FINAL_ACCEPTANCE_REPORT.md`](FINAL_ACCEPTANCE_REPORT.md). No credentials or active data were exposed or modified.

## Phase G checkpoint (2026-08-13)

- **Data Debt Cleanup: PASS-LOCAL.** Migration `0009_attachment_parsing_audit` is applied to the real PostgreSQL database and `alembic check` reports no drift.
- The cleanup did not create CrawlTasks, modify the approved Phase C corpus, change grounding, or alter source trust. `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`, 101 approved documents, 821 chunks, and 821 Qdrant points remain the verified baseline.
- Pending-review outcome: 0 automatic approvals, 1 deterministic hard rejection, 46 `HUMAN_REVIEW_REQUIRED`. This preserves the mandatory manual approval gate.
- Attachment outcome: 123 terminal records, with 77 failed, 46 unsupported, 0 parsed, and 0 pending. The single OCR-required record is explicitly `OCR_UNAVAILABLE`; no text or OCR success was fabricated.
- Historical metadata: 16 `region='??'` observations were written to immutable unresolved correction-audit rows; historical document values and the `scsia.org` association classification remain unchanged.
- Verification: Phase G targeted tests 12 passed; full backend suite 364 passed; Ruff and mypy passed; eight Compose services are healthy; 8080 and dependency health returned 200/healthy.
- Black was **UNVERIFIED-LOCAL** at this historical Phase G checkpoint; the later Phase M isolated-cache/source-scoped check is `PASS-LOCAL`. D drive free space was 106.7 GiB, above the 50 GiB stop threshold.
- Detailed evidence: [`DATA_QUALITY_REPORT.md`](DATA_QUALITY_REPORT.md).

- **Phase H configuration audit:** host Settings, Compose configuration and the running backend all select `none` with no remote rerank credential. Until a real remote call succeeds, status is `BLOCKED-EXTERNAL-RERANK-KEY`; neither disabled nor deterministic results are PASS-LIVE. Provider/failure-policy regressions include explicit 429/500/503 cases and pass 82 tests in the current checkpoint.
- **Phase I configuration audit:** the real Compose backend selects Brave but its credential is absent. Status is `BLOCKED-EXTERNAL-BRAVE-KEY`; fixture contract tests are not PASS-LIVE. Provider normalization/errors, content-gap flow, official validation, redirect/HTTPS defenses, manual approval/activation gate, retry/scheduler behavior, and API contracts passed 25 tests.
- **Phase J evaluation draft:** 100 real-corpus candidates across 18 required categories, 93 distinct persisted document/chunk IDs, and 11 official domains. The artifact is explicitly `DRAFT_EVAL_SET`, with `human_verified=0`; formal metrics remain null and status is `BLOCKED-HUMAN-EVAL-REVIEW`. Targeted evaluation regression passed 11 tests. See [`RAG_EVALUATION_REPORT.md`](RAG_EVALUATION_REPORT.md).

- Docker WSL data relocation remains intact on D drive with retained rollback evidence and no data deletion. As of the 2026-08-10 checkpoint Docker Desktop/Engine responds and all eight Compose services are healthy; backend/worker/scheduler use the same current image `sha256:b41a63d5b943f200304f9ee6a1d208d7fee62ff3920b4f77a19c97f5f0ccf163`. This is development evidence, not production TLS/secret/registry acceptance.
- Real Coze batch, OpenAI embedding, and Direct LLM credentials are supplied only in the ignored local `.env`; they were never printed or committed. Embedding and the Direct strict AnswerResult provider call are live-verified. Brave, rerank, and production secret/TLS acceptance remain absent.
- Git history contains implementation baseline `85d4bdb`, audit checkpoint `14bbf40`, and Docker recovery acceptance checkpoint `9cea9bd`. A clean reviewed release checkpoint, signed release tag, CI result, SBOM and registry provenance remain release gates.
- The live 10-article gov.cn crawl could not be executed after the external approval service rejected further network access due zero quota; the adapter contract is covered by local tests.
- PDF pages with insufficient extracted text are flagged for OCR; no OCR engine is installed locally.
- Coze batch discovery/fetch/schema/DB persistence, OCR review, remote embedding, and hybrid retrieval are PASS-LIVE for the bounded scsia.org association path. Direct LLM provider execution is configured and strict-schema live-verified; formal chat still requires a normally ingested eligible official source.
- Qdrant collection creation, remote embedding, Redis cache reuse and idempotent upsert are live-verified for 8 chunks and 8 points. Live deletion/compensation failure recovery, backup/restore and target production topology remain unverified.
- Acceptance-summary empty and non-empty collection handling are both live-verified: the historical pre-index state returned HTTP 200 with `collection_exists=false` and zero points; task 14 now returns HTTP 200 with `collection_exists=true`, 8 chunks and 8 points.
- Task 8 generated a real open `high_failure_rate` alert at severity `high` (`observed=0.4`, `threshold=0.2`). This verifies local monitoring reaction to the failed crawl, not production alert delivery, acknowledgement, escalation, or recovery.
- The selected remote Embedding and Direct LLM paths are live-verified at their provider boundaries. Remote rerank and alternative model experiment variants remain unavailable; the committed demo benchmark uses deterministic local providers and labels that scope explicitly.
- API rate limiting uses the shared Redis-backed fixed-window limiter by default outside tests and fails closed when Redis is unavailable; target Redis ACL/failover, ingress policy, and multi-instance fairness remain unverified.
- The recorded load-test numbers are deterministic local engineering measurements and are not production capacity or SLA claims.
- The current Compose stack and Nginx 1.30.4 pass local health checks on final application images; worker/scheduler reuse the single backend image build. Normal recreation now accepts the historical CSV trusted-proxy value. Production persistence recovery, worker failure/retry drills, and Nginx TLS/ingress target-host evidence remain external gates.
- A release candidate must be cut from a clean, reviewed checkpoint; create a signed release tag only after the external acceptance gates pass.
- The two frontend high findings were dev-only Playwright findings and are fixed at 1.55.1; current all-dependency and production-only audits are zero. Future lockfile changes must rerun both audits.
- Alembic is constrained to the verified 1.18.x range and locked to 1.18.5 for Docker/CI. Production database downgrade is still an operator-approved destructive exercise and was not performed on the business database; the isolated fresh PostgreSQL round-trip passed.
- The local outbound proxy maps `scsia.org` to `198.18.0.208`; the backend intentionally rejects that non-public target. A target host with ordinary DNS or an explicitly approved proxy-aware egress path is required for live crawl acceptance. The detail pages are predominantly image resources, so selectors and OCR/image extraction still require validation.

## Blocked External Integrations

- Real Brave source discovery and remote rerank verification require their own credentials and reachable endpoints. Direct LLM strict structured output and the formal official cited-answer route are live-verified through task 23.
- The local crawler still correctly rejects synthetic proxy DNS addresses, while cloud Coze crawl, OCR re-evaluation, Embedding, Qdrant indexing, Hybrid Retrieval, formal Direct citation, and zero-hit refusal are verified. The scsia association identity and corrupted historical `region="??"` remain unchanged. Two other documents remain legitimately OCR_FAILED/rejected.

## Reports and Acceptance

- [`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md): requirement-to-code matrix, fixture boundary, risks, and release gates.
- [`PRODUCTION_ACCEPTANCE_CHECKLIST.md`](PRODUCTION_ACCEPTANCE_CHECKLIST.md): exact target-environment commands and expected results.
