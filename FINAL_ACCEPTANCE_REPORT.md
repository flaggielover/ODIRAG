# Phase N-Q Final Acceptance Report

> Historical scope report: Phase N-Q and the later Attachment/OCR closure are preserved below.
> Older production-security, provider, and human-evaluation blockers in this file were superseded
> by subsequent live work. The current overall verdict is Phase 1-5 and
> `PRODUCTION_READINESS=PASS-LIVE` in `PRODUCTION_READINESS_REPORT.md`; the Gold quality and OCR
> limitations remain as documented rather than being promoted to pass.

## Attachment / OCR Production Closure (2026-08-15, latest authoritative)

This section supersedes older attachment, backend-test, backend-image, and
migration statements below. It does not alter the frozen Gold, RAG, P95, Remote
Rerank, Brave, or Human Evaluation conclusions.

The closure processed only the 123 existing Attachment rows. A new attachment
worker reuses trusted DNS, public-address validation, pinned connections, redirect
revalidation, rebinding protection, and download limits. It writes byte-hashed
content through verified temporary files and atomic replace. Parser/OCR cache keys
are processor-version aware. No CrawlTask or attachment index operation occurred.

The real Before/After result is:

- parsed `0 -> 60`;
- failed `77 -> 8`;
- unsupported `46 -> 55`;
- pending `0 -> 0`;
- local files `0 -> 69`, with zero temporary-file residue;
- historical SSRF results `76 blocked -> 69 downloaded + 7 HTTP 404`.

Download attempt coverage is 123/123. Status completion is 115/123, but only 70
rows have a byte-derived hash; the conservative byte-verified success rate is
56.91%. Eight terminal failures are real nonretryable HTTP 404 responses.

The true parser-format denominator is 67: PDF `46/53`, DOCX `13/13`, and XLSX
`1/1`, for end-to-end coverage `60/67 = 89.55%`. All 60 attachments that reached a
supported parser succeeded. Nine responses labeled DOCX were OLE legacy files and
are now explicit `UNSUPPORTED_LEGACY_FORMAT`. Parsed provenance is complete 60/60
and a ten-item content/provenance sample passed 10/10.

No production OCR provider is configured. The only current image URL returns 404,
so OCR eligible/attempt/success is `1/0/0`; OCR remains PARTIAL and no result was
fabricated. Tests cover the required existing failed-state contract
`OCR_PROVIDER_UNAVAILABLE + requires_ocr=true` for available bytes.

Idempotency passed with a real DOCX cache hit: byte hash and parse/processed
timestamps did not change. Chunks remain 821, attachment chunks 0, and Qdrant
remains green with 821 points.

Final engineering evidence is pytest `518/518`, Ruff check PASS, Ruff format
`245/245`, mypy `169` source files, compileall PASS, and Alembic drift PASS. Black
`--version` timed out at the controlled 30-second Windows limit; no residual
process remained, so Black is not claimed PASS. Alembic head is
`0012_attachment_processing_audit`.

Backend, worker, and scheduler all run final image
`sha256:6d1b89444b4ef9fda3885521f6e3fbbee61c0a8fc41e3dd450352dfcd0cbacb9`.
All eight Compose services are healthy, and API database, Redis, and Qdrant
dependencies are healthy. Frozen core counts remain documents
182, approved 101, rejected 35, pending 46, chunks 821, and Qdrant 821. Human Gold
and run16 failure-matrix hashes are unchanged.

Final attachment statuses:

- `ATTACHMENT_DOWNLOAD=PARTIAL`
- `ATTACHMENT_PARSING=PASS-LIVE` at the reached-parser stage
- `ATTACHMENT_OCR=PARTIAL`
- `ATTACHMENT_PROVENANCE=PASS-LIVE`
- `ATTACHMENT_TERMINAL_STATE=PASS-LIVE`

Remaining attachment constraints are the eight HTTP 404 URLs, 45 historical
unsupported rows without byte evidence, and the absent OCR provider. The next
project phase remains Production Engineering; this closure did not enter it.

## Gold Quality Closure - final run 16 (2026-08-15, latest authoritative)

This section supersedes every older Gold-run, quality-guard, backend-regression,
and migration count below where they differ. Historical sections remain for audit.

The checkpoint was restored without data loss. Final image
`odirag/backend:local` has manifest list
`sha256:70b8e21a15aa2b2f1f3fccfccb56ce6aa3e68d36b1119384d43e59632e55f7c5`;
backend, worker, and scheduler were recreated from that same image. PostgreSQL,
Redis, Qdrant, frontend, nginx, and all volumes were preserved.

Final Live Guard run 15 covered 23 affected/QA supported cases and all 10 Gold
refusal cases. Supported result was `14 answer / 9 refuse`, with all 14 answers
grounded. Refusal safety was `10/10`, citations `0`, unsupported answers `0`, and
execution errors `0`. The fixed QA14 subset passed `5/8`, so the guard is
`FAIL-LIVE-QUALITY` even though its safety contract passed. Remote Rerank applied
to 20/33 guard traces; 13 HTTP 429 responses used the configured fail-open path.

The one permitted final 100-case run is run 16. It completed 100/100 with zero
execution errors: Recall@5/10 `0.885/0.885`, MRR `0.840667`, nDCG@5/10
`0.806227/0.806227`, exact citation precision/recall `0.288069/0.433333`, grounded
answer rate `0.948276`, refusal accuracy `0.68`, unsupported-answer rate `0`,
Evidence Sufficiency Accuracy `0.96`, and Supported Answer Recall `0.644444`.
Confusion is Gold supported `58 answer / 32 refuse` and Gold refusal
`0 answer / 10 refuse`. Therefore `GOLD_EVALUATION_QUALITY=PARTIAL`; no validator,
threshold, or Gold label was changed after this run.

Final backend regression is `501 passed`; Ruff check, Ruff format (237 files),
mypy (167 files), compileall, Alembic head/check, and `git diff --check` pass.
Black's only controlled production-source check timed out after 120 seconds on
Windows, so `BLACK=UNVERIFIED-WINDOWS-TIMEOUT`, not PASS. Runtime is 8/8 healthy,
homepage HTTP 200, API/dependencies healthy, PostgreSQL accepting, Redis PONG,
Qdrant green/821, and corpus data remains 182 documents, 101 approved, 35
rejected, 46 pending, and 821 chunks.

Provider boundary results remain
`KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`,
`REMOTE_RERANK_PROVIDER=PASS-LIVE`, `REMOTE_RERANK_FULL_RAG=PASS-LIVE`, and
`BRAVE_SOURCE_DISCOVERY=PASS-LIVE`. The final run-wide Remote Rerank coverage is
separately `PARTIAL-LIVE` at `67 applied / 33 HTTP 429 fail-open`.

Overall verdict remains **NOT PRODUCTION ACCEPTED**. Current blockers are Gold
supported-answer quality, run-wide Remote Rerank capacity/reliability, the existing
P95 performance gate, attachment/OCR, production backup/PITR and recovery,
TLS/secret management, monitoring/release provenance, and cloud deployment.

## Phase AD Gold evaluation closure (2026-08-14, latest authoritative checkpoint)

Human review is complete through the formal importer. The user reviewed all 100
rows in `data/evaluation/eval_human_review.xlsx`; live-PostgreSQL dry-run and apply
returned `TOTAL=100 / REVIEWED=100 / UNREVIEWED=0 / PASS=100 / FIX=0 /
REJECT=0 / VERIFIED=100 / TRACEABILITY_ERRORS=0`. The final verified artifact is
`data/evaluation/phase_j_human_verified.json`, with status
`HUMAN_REVIEW_INFRASTRUCTURE=PASS-LOCAL / HUMAN_EVALUATION=PASS-HUMAN /
HUMAN_REVIEW_COMPLETE=true`.

Formal Gold run `6` executed all 100 questions through the real evaluation API with
zero execution errors. Retrieval metrics were Recall@5=`0.885`, Recall@10=`0.885`,
MRR=`0.809`, nDCG@5/10=`0.789022`; citation precision=`0.067513`, citation
recall=`0.116667`, grounded-answer rate=`1.0` over 20 assessed answers, refusal
accuracy=`0.3`, unsupported-answer rate=`0.0` over 10 intended refusals, and
evidence-sufficiency accuracy=`0.56`. P50/P95 latency was `3896/8121 ms`.

The independent run `7` quality guard used two supported and two refusal questions.
Both refusal cases passed the refusal contract, but both supported cases refused,
so the authoritative result is `GOLD_EVALUATION=COMPLETE-WITH-QUALITY-FAILURE`
and `QUALITY_GUARD=FAIL-LIVE-QUALITY` (2/4 passed). No threshold, validator,
grounding, citation, or refusal rule was weakened. Run `5` was a failed preflight
caused by unsupported metadata filters and is excluded from Gold metrics.

The authoritative Phase AB before/after artifacts are
`data/performance/phase-ab-before-20260814T074402Z.json` and
`data/performance/phase-ab-after-20260814T084535Z.json`. Across 20 fixed draft
questions and three complete runs, P50 improved `2582 -> 1638 ms`, P95
`8763 -> 6774 ms` (-22.7%), and P99 `10082 -> 9129 ms`. Query-embedding caching
reduced warm embedding P95 below 3 ms, but Direct LLM remained the slowest stage
at P95 `6737.128 ms`; Remote Rerank P95 was `1580.243 ms`. The best run P95 was
`6056 ms`, so `RAG_PERFORMANCE_P95=PARTIAL` rather than PASS-LIVE.

The prior performance-only four-case artifact remains historical. The authoritative
human-gold quality guard is `data/evaluation/gold_quality_run_7/`; its refusal cases
were safe, while its supported cases failed as described above.

The prior full engineering baseline is `450 passed`; current Human Review/Gold
helpers pass their targeted Ruff, mypy, compile, and diff checks. Production
Alembic remains at the previously verified `0010` head; Gold evaluation required no
migration. All eight Compose services are healthy, homepage/system health return
HTTP 200, and core state is unchanged at documents `182`, approved `101`, rejected
`35`, pending manual review `46`, chunks `821`, and Qdrant green/optimizer OK with
`821` points.

Retained completed gates are
`KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`,
`REMOTE_RERANK_PROVIDER=PASS-LIVE`, `REMOTE_RERANK_FULL_RAG=PASS-LIVE`, and
`BRAVE_SOURCE_DISCOVERY=PASS-LIVE`. Remote Rerank and Brave are not remaining
blockers. Overall verdict remains **NOT PRODUCTION ACCEPTED** because supported-
answer quality, the P95 target, attachment/OCR, production backup/PITR, Qdrant
snapshots, Redis recovery/HA, retention/resource/logging/alert routing, TLS/secret
management, and release provenance remain open.

## Phase Z Brave Source Discovery final acceptance (2026-08-14, authoritative)

`BRAVE_SOURCE_DISCOVERY=PASS-LIVE`.

Real Brave run `4` produced candidate `7` for the Sichuan Provincial Department
of Economy and Information Technology at
`https://jxt.sc.gov.cn/scjxt/index.shtml`. Official validation passed with HTTPS,
HTTP 200, exact host/site, `.gov.cn`, government markers, and score `1.0`. Six
bounded columns fetched `30` real details. The verified announcement panel accepted
two DIRECT software-policy documents and rejected three unrelated documents; the
other five columns accepted none. Aggregate trial result was `2 accepted / 28
rejected`, accepted average length `798`, and candidate quality `0.7667` against
the unchanged `0.65` threshold.

The governance state machine was proven on real state. Before approval, activation
returned HTTP `409` `INVALID_SOURCE_CANDIDATE_STATE`. After the explicit human
decision, the formal API recorded `pending_approval -> approved` for `admin` at
`2026-08-14T06:01:58.993737Z`, then `approved -> activated`. Activation created
enabled official government Source `46` and only the qualified announcement
SourceColumn `191`; five `0/5` candidate columns remain audit-only. Automatic
discovery remained disabled with no topics, and no CrawlTask was created.

The legacy run aggregate still exposes zero `approved_count` and `activated_count`;
the candidate/source/event records above are the authoritative, internally
consistent governance evidence.

Final Brave gates are all `PASS-LIVE`: Search Provider, SSRF, Official Validation,
Column Discovery, Trial Crawl, Manual Governance, Source Activation, and end-to-end
Source Discovery. Post-activation core counts remain documents `182`, approved
`101`, rejected `35`, pending manual review `46`, chunks `821`, and Qdrant green
with `821` points. `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE` remains intact.
Remote Rerank remains `REMOTE_RERANK_PROVIDER=PASS-LIVE` and
`REMOTE_RERANK_FULL_RAG=PASS-LIVE`; Phase Z did not call Cohere.

Remaining work is unchanged outside these completed provider paths: complete the
100-item human evaluation review, close the P95 performance target, complete real
attachment parsing/OCR coverage, and finish production backup/restore, retention,
resource/logging, alert-routing, TLS/secret, and disaster-recovery acceptance.

## Phase W-X-Y closure (2026-08-14, latest authoritative checkpoint)

This section supersedes older Phase T-U provider conclusions where they differ. The
historical sections remain below for auditability.

### Remote Rerank

`REMOTE_RERANK_PROVIDER=PASS-LIVE` and
`REMOTE_RERANK_FULL_RAG=PASS-LIVE`. The earlier failure in trace
`f9a44597-a18e-46ae-8aa5-5d36632cddc1` came from caller-side UTF-8 corruption: the
stored query contained 40 literal ASCII `?` characters. It was not a backend
relation-validator defect, and no Answer Validation, evidence, citation, relation,
or grounding control was relaxed.

With correctly encoded input, trace `70906f7f-648f-4356-a0ee-47829afae7c1`
returned a supported official answer, while trace
`e0e57258-4d19-44a9-94d4-ea8430a6f2c4` returned the
supported filing-stage answer: September 2023 through March 2024 for existing APP
filing and April through June 2024 for supervision and inspection. Both passed
unchanged validation and cited real chunk
`0bf55b37-7bf1-5ce9-834a-f46754e84fec` with its traceable title and source URL.
Broad multi-fact trace `b48ca4d8-1f40-49c8-b98e-f4c057851963` safely refused with
`insufficient_evidence_relevance`; no-evidence trace
`47570efd-6352-4213-8abf-ce0fbc3408c7` safely refused before the answer LLM.

### Brave Source Discovery

The prior SSRF failure was caused by local fake-IP DNS returning `198.18.0.0/15`.
The correction keeps the policy fail-closed: DoH resolves the validation address,
the vetted IP is pinned at actual socket connection while the original Host and TLS
SNI are retained, redirects are revalidated, and IPv6 site-local plus all existing
private/fake/mixed/rebinding/link-local/reserved/loopback cases are rejected. Only
`backend`, `worker`, and `scheduler` were rebuilt/recreated, and all three returned
healthy. Stateful services, frontend/nginx, and Docker volumes were not recreated.

Real Brave run 3/candidate 6 evaluated
`https://jxt.sc.gov.cn/scjxt/index.shtml`. Official validation passed at HTTP 200
with exact HTTPS host, `.gov.cn` evidence, and score 1.0; 12 columns were
discovered. The bounded trial then fetched 60 pages and accepted 0 relevant detail
documents. All trial results were `NO_RELEVANT_DETAIL_DOCUMENTS`; quality was 0.5
against threshold 0.65. The candidate was rejected and the run failed before the
manual gate. No approval, activation, Source, or CrawlTask was created.

Current statuses are:

- `BRAVE_SEARCH_PROVIDER=PASS-LIVE`
- `SSRF=PASS-LIVE`
- Official Validation: `PASS-LIVE`
- Column Discovery: `PASS-LIVE`
- Trial Crawl / Quality: `FAIL-LIVE`
- `MANUAL_SOURCE_APPROVAL_REQUIRED=NO`

### Core and regression

Final read-only verification returned HTTP 200 for 8080 and system health, with
healthy PostgreSQL, Redis, and Qdrant dependencies. PostgreSQL remains at 182
documents, 101 approved, 35 rejected, 46 pending manual review, and 821 chunks;
Qdrant `odirag_chunks` is green with 821 exact points. Targeted Phase W-X-Y
regression passed `127` tests, plus scoped Ruff lint/format, Black, strict mypy,
and `git diff --check`. The retained status is confirmed as
`KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE`. Overall verdict remains
**NOT PRODUCTION ACCEPTED** because broader
human-evaluation, performance, disaster-recovery, and production-security gates are
separate and still open.

Date: 2026-08-14
Overall verdict: **NOT PRODUCTION ACCEPTED**
Knowledge-base closed loop: **`KNOWLEDGE_BASE_LIVE_CLOSED_LOOP = 5/5 PASS-LIVE`**

## Current closure snapshot

### Phase T-U live provider result

- `REMOTE_RERANK_PROVIDER=PASS-LIVE`: provider `remote`, model `rerank-v3.5`, five
  real requests, five applied results, zero provider errors. Observed persisted Chat
  rerank latency is 1109.401-1282.509 ms.
- `REMOTE_RERANK_FULL_RAG_GATE=PARTIAL`: supported evidence and Direct LLM execution
  succeeded, but unchanged Answer Validation safely refused with
  `answer_contains_unsupported_relation` and zero citations. The no-evidence request
  correctly refused with zero citations and zero answer-LLM tokens.
- `BRAVE_SEARCH_PROVIDER=PASS-LIVE`: two real searches; the valid Unicode query
  returned five real Sichuan government candidates.
- `BRAVE_SOURCE_DISCOVERY=BLOCKED-LOCAL-SSRF-PROXY-RESOLUTION`: all five candidates
  failed official-validation fetch as `UnsafeUrlError`; no column/trial/quality or
  manual approval gate was reached, and no source was activated.
- The core 5/5 corpus remains unchanged at 182 documents, 101 approved, 821 chunks,
  and 821 Qdrant points.

### Phase S-V provider attempt (2026-08-14)

Both credentials are present in the ignored local configuration, and the non-secret
Rerank provider setting is now `remote` with model `rerank-v3.5` and failure policy
`open`. However, the minimal backend/worker/scheduler recreation and approved
external network execution were stopped by the local approval service before they
ran. The live backend remains `provider=none`; a debug request returned
`rerank_applied=false` and `rerank_provider_disabled`.

No Cohere or Brave response was accepted in this attempt. Current statuses are:

- `REMOTE_RERANK=BLOCKED-LOCAL-RUNTIME-RELOAD-AND-NETWORK`
- `BRAVE_SOURCE_DISCOVERY=BLOCKED-LOCAL-RUNTIME-RELOAD-AND-NETWORK`

No external PASS-LIVE claim, candidate, source activation, trial crawl, or manual
approval result was fabricated. Contract regression passed (`29 + 19` tests), and
the core database/Qdrant counts remain `182 documents / 101 approved / 821 chunks /
821 points`.

The Phase N-Q local closure is complete within its safe boundary. The main RAG,
Embedding, Qdrant, Hybrid Retrieval, Direct LLM, Grounding and Coze paths were not
redesigned. Existing counts remain `documents=182`, `approved=101`, `rejected=35`,
`pending_manual_review=46`, `chunks=821`, and Qdrant exact points `821`.

- Attachment parsing: `PASS-LOCAL` terminal-state gate (`123 total, 0 pending, 77
  failed, 46 unsupported`); attachment OCR: `PARTIAL` (`0 success`, `1
  OCR_UNAVAILABLE`, `123 URL-only`, no real OCR provider).
- Performance: three real runs over six measured samples yielded P50 `734.236 ms`,
  P95 `5121.708 ms`, P99 `5121.708 ms`; target `<5000 ms` is not met, so
  `RAG_PERFORMANCE_P95=PARTIAL`.
- Human evaluation: workbook and importer are `PASS-LOCAL` infrastructure, but
  `REVIEWED=0/100`, `VERIFIED=0/100`, and status is `BLOCKED-HUMAN`.
- Regression: backend `399 passed`; application Ruff/format and mypy pass. Frontend
  audit is zero vulnerabilities; fresh Vite/Compose execution was blocked by local
  process/named-pipe approval and is not represented as a new pass.

## What is actually live

| Area | Evidence | Status |
|---|---|---|
| Official corpus | 100 qualifying government/official documents; 31 source rows; 10 domains; valid region metadata | PASS-LIVE |
| PostgreSQL | current audit: 182 documents, 101 approved, 35 rejected, 46 pending manual, 821 chunks | VERIFIED-LOCAL / LIVE DATA RETAINED |
| Qdrant | `odirag_chunks`, green, 821 exact points, 1536-vector collection | PASS-LIVE |
| Embedding | OpenAI `text-embedding-3-small` used for accepted indexed corpus | PASS-LIVE for selected path |
| Hybrid retrieval | real BM25/vector/fusion and official-source filtering | PASS-LIVE for selected path |
| Evidence Sufficiency | supported and adversarial/no-evidence refusals | PASS-LIVE for verified scenarios |
| Direct LLM | OpenAI `gpt-4.1-mini`, strict `AnswerResult`, grounded citation | PASS-LIVE for verified scenarios |
| QueryTrace stages | PostgreSQL migration `0010`; supported/refusal traces with non-empty numeric stage maps | PASS-LIVE |
| Front door | 8080 HTTP 200; `/api/system/health` healthy; all 8 services healthy after backend-only rebuild | VERIFIED-LOCAL |
| Disk guard | D: approximately 106.6 GiB free, above 50 GiB stop threshold | PASS |

## Current blockers

- `BLOCKED-EXTERNAL-RERANK-KEY`: host, Compose and backend all use `rerank_provider=none`; no remote call was made. Deterministic/disabled rerank is not remote acceptance.
- `BLOCKED-EXTERNAL-BRAVE-KEY`: no real Brave request or source-discovery run was fabricated.
- `BLOCKED-HUMAN-EVAL-REVIEW`: 100-case evaluation artifact is `DRAFT_EVAL_SET`, human verified 0/100, and formal quality metrics remain null.
- `BLOCKED-PRODUCTION-DR`: no scheduled encrypted PostgreSQL/PITR, Qdrant snapshots, Redis HA/recovery drill, or measured RPO/RTO.
- `BLOCKED-PRODUCTION-SECURITY`: production TLS/DNS, external secret manager, stateful ACL/private topology, resource limits, log rotation, external alert routing and signed registry provenance are not accepted.
- `BLOCKED-LOCAL-GIT-PERMISSION`: `.git/index.lock` is absent and there is no active Git process, but inherited explicit deny ACLs prevent index writes. The single controlled `git add --all` attempt failed before staging; no stale lock was deleted and no permission was forced, and the full diff is retained.

## Historical Phase M verification

- Backend full suite at the Phase M checkpoint: `370 passed` (the current Phase Q run is `399 passed`, recorded above).
- Ruff and Ruff format at that historical checkpoint: pass.
- Black at that historical checkpoint: source-scoped `PASS-LOCAL`; the current strict Black run reports formatter differences on a subset and is not a global pass.
- mypy at that historical checkpoint: pass; the current run passes 164 application files.
- Remote rerank focused suite: 24 tests; explicit 429/500/503 mapping included.
- SQLite Alembic: fresh upgrade, downgrade to `0009`, upgrade to `0010`, and `alembic check`: pass at the historical checkpoint.
- Real PostgreSQL Alembic: revision `0010_query_trace_stage_timings`, `alembic check` no drift at the historical checkpoint; current closure advances additively to `0011_attachment_download_audit`.
- QueryTrace supported case: five real retrieval hits, sufficient evidence, real Direct LLM call, 2,907 tokens, one complete citation, 5,198 ms total; all persisted stage values are numeric and non-negative.
- QueryTrace insufficient case: five retrieved candidates failed Evidence Sufficiency, `refusal=true`, zero citations and zero answer-LLM tokens, 1,355 ms total; only actually executed stages were persisted.
- Frontend lint/type-check pass; Vitest `18/18`, Vite production build (1,850 modules), and Playwright `10 passed, 1 expected skip` pass outside the restrictive spawn sandbox. `npm audit --omit=dev` and full `npm audit`: `0 vulnerabilities`.
- Python compile and Git diff checks: pass.
- Runtime: all 8 Compose services healthy, homepage 200, dependency health healthy, Qdrant collection green with 821 points, PostgreSQL at 182 documents/821 chunks.
- No API key, token, cookie, authorization header, `.env` content, prompt secret, or provider response body was output or committed.

## Data and safety invariants

- No approved Phase C document, historical association classification, or `region='??'` value was rewritten.
- No pending document was counted as approved.
- No mock, fixture, deterministic provider or extractive fallback was used to claim a live external provider.
- No active volume was deleted, compacted, reset, downgraded or pruned.
- Existing 5/5 evidence and 821 Qdrant points remain the baseline.

## Final numbers

- documents `182`; approved `101`; rejected `35`; pending manual review `46`
- chunks `821`; Qdrant `odirag_chunks` points `821`
- QueryTrace rows `83`; latest migration `0010_query_trace_stage_timings`
- backend tests `370 passed`; frontend Vitest `18/18`; Playwright `10 passed, 1 expected skip`

## Completion

- `CORE_RAG_COMPLETION = 100%` for the verified 5/5 closed loop
- `LOCAL_ENGINEERING_COMPLETION = 98%` (all local verification gates pass; only the Git checkpoint is blocked by repository ACLs)
- `ANSWERABLE_DEMO_READINESS = 100%` for the verified official MIIT path
- `PRODUCTION_READINESS = 60%` as a gate-weighted engineering estimate: core data/RAG/runtime/local regression gates pass, while external provider/evaluation and production security/operations gates remain unaccepted
- `PRODUCTION_ACCEPTED = NO`

## Release decision

The project is functionally usable on the local development stack and has a real, traceable official-document RAG closed loop. Local Phase M technical closure is complete except for the Git checkpoint permission issue. It is not production-ready until the external provider, human evaluation, disaster-recovery, security-hardening and release-provenance blockers above are independently accepted. No further corpus expansion or business implementation is required by this checkpoint.
