# Attachment / OCR Production Closure Report

Date: 2026-08-15

Scope: only the 123 Attachment rows already present in PostgreSQL. No CrawlTask,
corpus expansion, attachment reindex, Gold/RAG change, or OCR provider call was made.

## Before / After

| Metric | Before | After |
| --- | ---: | ---: |
| Total | 123 | 123 |
| Parsed | 0 | 60 |
| Failed | 77 | 8 |
| Unsupported | 46 | 55 |
| Pending | 0 | 0 |
| Local files | 0 | 69 |
| Byte-verified downloads | 0 | 70 |
| Historical SSRF outcomes | 76 blocked | 69 downloaded, 7 real HTTP 404 |
| OCR success | 0 | 0 |
| Chunks / Qdrant points | 821 / 821 | 821 / 821 |

Alembic is at `0012_attachment_processing_audit`; `alembic check` reports no drift.

## Download

- Eligible/current URLs: 123.
- Attempted: 123/123 (100%).
- Status-level completed: 115/123 (93.50%).
- Completed with byte-derived SHA-256: 70/123 (56.91%).
- Local reusable files: 69/123 (56.10%). One legacy DOC was byte-verified but is not
  persisted as a parser input.
- Failed: 8/123 (6.50%), all `DOWNLOAD_HTTP_404` and nonretryable.
- The remaining 45 historical `completed` unsupported rows have no local file/hash,
  so they are not counted as verified byte success.

Downloads use trusted DNS, public-IP validation, pinned connection IPs, redirect
revalidation, DNS rebinding protection, timeouts, and size limits. Files are written
to a same-directory temporary path, fsynced, size/hash verified, then atomically
replaced. The final attachment volume has 69 files and zero `.tmp` residue.

## Parsing

The end-to-end denominator contains only formats supported by the current parser
stack; legacy and other unsupported formats are excluded.

| Type | Eligible | Parsed | Download-stage failed | Coverage |
| --- | ---: | ---: | ---: | ---: |
| PDF | 53 | 46 | 7 | 86.79% |
| DOCX | 13 | 13 | 0 | 100% |
| XLSX | 1 | 1 | 0 | 100% |
| TXT / HTML | 0 | 0 | 0 | N/A |
| Total | 67 | 60 | 7 | 89.55% |

All 60 attachments that reached a supported parser succeeded: parser-stage success is
60/60 (100%). Nine downloads advertised as DOCX were proven by magic bytes to be OLE
legacy files and were correctly reclassified as unsupported rather than parser
failures. The Alpine runtime now includes `libstdc++`, required by PyMuPDF; the real
10-page sample PDF then extracted 4,696 persisted characters.

## OCR

- Provider configured: false.
- Eligible: 1 current image attachment.
- Reached OCR/provider attempt: 0; its remote URL returned HTTP 404 before OCR.
- Success: 0; OCR-stage failure: 0; success rate is N/A (0 attempts).
- Stored `ocr_status=failed`: 1 historical/current row, but its terminal cause is now
  `DOWNLOAD_HTTP_404`, not a fabricated provider attempt.

Images and low-text PDFs route to the existing OCR protocol. Tests prove the
`failed + OCR_PROVIDER_UNAVAILABLE + requires_ocr=true` state contract when bytes are
available but no provider is configured. No OCR text or success was fabricated.

## Provenance And Quality

For parsed attachments, byte hash, parser/version, processed timestamp, local path,
MIME, detection source, and extraction method are complete in 60/60 rows. Empty text
is 0/60 and HTML/JS markup contamination is 0/60. A directed ten-item sample covering
PDF, DOCX, and XLSX passed title/body consistency, non-garbled text, nonempty content,
and provenance inspection (10/10).

## Terminal State And Failures

- Terminal states: 123/123 (100%); pending: 0.
- Parsed: 60/123 (48.78%).
- Failed: 8/123 (6.50%), all explicit `DOWNLOAD_HTTP_404`.
- Unsupported: 55/123 (44.72%): 45 historical `UNSUPPORTED_FILE_TYPE` and 10
  byte-proven `UNSUPPORTED_LEGACY_FORMAT`.
- Failed and unsupported rows have nonempty codes, sanitized messages, and explicit
  retryability. Residual eligible rows after the one batch: 0.

## Idempotency And Regression

Repeating attachment 2 produced a download cache hit. Its byte hash,
`parse_attempted_at`, `processed_at`, and extracted length were unchanged. No chunk or
Qdrant point was added: attachment chunks remain 0, PostgreSQL chunks 821, and Qdrant
green with 821 points.

- Targeted attachment/parser/OCR/SSRF evidence: 83/83 passing after isolating a known
  Windows pytest temp-directory ACL issue; the four affected tests passed with the
  repository fixture.
- Final backend regression: 518/518 passed.
- Ruff check: PASS; Ruff format: 245/245; mypy: 169 files; compileall: PASS;
  Alembic check: PASS.
- Black: `--version` timed out at the bounded 30-second Windows limit; no residual
  Black/Python process remained. No PASS is claimed for Black in this session.

## Final Status

- `ATTACHMENT_DOWNLOAD=PARTIAL` (100% attempted; 8 real 404; 45 historical completed
  rows lack verifiable bytes).
- `ATTACHMENT_PARSING=PASS-LIVE` for the reached parser stage; end-to-end format
  coverage is 89.55% because seven PDFs could not be downloaded.
- `ATTACHMENT_OCR=PARTIAL` (provider unavailable; the sole current image is 404).
- `ATTACHMENT_PROVENANCE=PASS-LIVE` for 60/60 parsed rows.
- `ATTACHMENT_TERMINAL_STATE=PASS-LIVE` (123/123, pending 0).
