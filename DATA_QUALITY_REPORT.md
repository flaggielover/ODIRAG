# Data Quality Report

> Historical checkpoint: this Phase G report predates the attachment production closure. Its
> corpus cleanup evidence remains valid, but attachment outcome counts in the body were superseded
> by `ATTACHMENT_OCR_REPORT.md` and the latest section of `IMPLEMENTATION_STATUS.md`: 60 parsed,
> 8 failed, 55 unsupported, 0 pending, and 69 stored attachment files. No historical row below has
> been rewritten.

Last updated: 2026-08-13

## Scope and verdict

Phase G audited the existing Phase C corpus without creating CrawlTasks or adding documents. The existing `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5 PASS-LIVE` evidence remains intact.

Status: **PASS-LOCAL for deterministic data-debt cleanup; BLOCKED-HUMAN for 46 document decisions; BLOCKED-EXTERNAL for unavailable attachment bytes/OCR.**

## Corpus gate

| Measure | Before | After | Verification |
| --- | ---: | ---: | --- |
| Documents | 182 | 182 | PostgreSQL live query |
| Approved | 101 | 101 | No approval was automated |
| Rejected | 34 | 35 | One empty document met the hard rejection rule |
| Pending manual review | 47 | 46 | The remaining records retain the manual gate |
| Chunks | 821 | 821 | PostgreSQL live query |
| Qdrant points | 821 | 821 | Existing Phase C live evidence retained |

The 100 qualifying official Phase C documents remain approved and indexed. URL/content duplicate count for that accepted set remains zero; Phase G did not alter source trust classifications or grounding rules.

## Pending-review audit

- Automatic approval: **0**. Coze `accepted` is intentionally mapped to `pending_manual_review`; the cleanup does not bypass the configured reviewer gate.
- Deterministic automatic rejection: **1** (`document.id=138`): empty content, below `hard_minimum_chars=40`, and no attachment evidence.
- Human review required: **46**.
- Audit records: 47 `data_debt_audit/human_review_required` plus one `data_debt_hard_reject/reject`.
- Principal causes include incomplete body/attachment evidence, incomplete body without a confirmed attachment, Coze-accepted records awaiting manual approval, one historical quality-assessment failure, and other ambiguous review cases.

Replaying the simple rule filter was not used as an approval decision: length and keyword checks cannot prove that an attachment-dependent body is complete.

## Attachment outcomes

All 123 historical attachments now have a terminal, auditable outcome instead of remaining `pending`:

| Outcome | Count | Meaning |
| --- | ---: | --- |
| `parsed` | 0 | No attachment had trustworthy local bytes or upstream extracted text |
| `failed` | 77 | 76 `ATTACHMENT_NOT_DOWNLOADED`; 1 `OCR_UNAVAILABLE` |
| `unsupported` | 46 | `UNSUPPORTED_FILE_TYPE` |
| `pending` | 0 | Phase G terminal-state requirement met |
| OCR success / partial / failed | 0 / 0 / 1 | No OCR text was fabricated |

Every attempted attachment records `file_type`, `extracted_text_length`, `parser`, `ocr_status`, `error_code`, `retryable`, and `parse_attempted_at`. A failure is isolated to the attachment and does not invalidate its document.

## Historical metadata

Sixteen documents retain historical `region='??'`. Phase G created 16 immutable `document_metadata_corrections` rows with `status=unresolved`, the old value, reason, evidence source, and timestamp. No document region was silently changed because the persisted Coze/request lineage does not contain a trustworthy replacement value.

The historical `scsia.org` association classification is also unchanged. It remains ineligible for official-only grounding, as required by the existing policy.

## Implementation and verification

- Migration: `0009_attachment_parsing_audit` applied to real PostgreSQL; `alembic check` reports no generated operations.
- Targeted Phase G tests: 12 passed.
- Full backend regression: 364 passed in 43.55 seconds.
- Ruff: PASS.
- mypy: PASS across 157 source files.
- Black: **UNVERIFIED-LOCAL**; the Windows executable did not exit within a controlled 25-second check and was stopped without changing files.
- Runtime: all eight Compose services healthy; `http://127.0.0.1:8080/` and `/api/system/health` returned HTTP 200; database, Redis, and Qdrant health were healthy.
- Disk gate: D drive had 106.7 GiB available at the Phase G boundary, above the 50 GiB stop threshold.

## Remaining actions

1. A human reviewer must decide the remaining 46 records.
2. Attachment download bytes must be recovered before PDF/DOC/DOCX/XLS/XLSX parsing can produce text.
3. A configured OCR provider is required for the one image/OCR case.
4. Region corrections require trustworthy source evidence and an explicit audited correction action.
