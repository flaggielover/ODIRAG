# Attachment Production Closure Baseline

Date: 2026-08-15

Scope: current PostgreSQL attachment rows only. No CrawlTask, download, parser,
OCR, index, migration, or provider operation was started while collecting this
baseline.

## Evidence Source

The baseline was freshly read in two independent ways: the authenticated backend
repository API queried all 182 current PostgreSQL documents and their attachments,
and a direct PostgreSQL `REPEATABLE READ / READ ONLY` transaction reproduced the
same aggregate at `2026-08-15 14:00:34 +08:00`. PostgreSQL is `16.14`, Alembic is
`0011_attachment_download_audit`, and no historical report number was used as the
source of truth. The Docker app-data attachment directory also contains zero files.

## Terminal State Baseline

| Metric | Count | Definition |
| --- | ---: | --- |
| TOTAL_ATTACHMENTS | 123 | All current Attachment rows |
| PENDING | 0 | `parse_status=pending` |
| PARSED | 0 | `parse_status=parsed` |
| FAILED | 77 | `parse_status=failed` |
| UNSUPPORTED | 46 | `parse_status=unsupported` |
| NEEDS_OCR | 1 | `requires_ocr=true` |
| OCR_SUCCESS | 0 | `ocr_status=success` |
| OCR_FAILED | 1 | `ocr_status=failed` |
| TERMINAL_STATE_RATE | 123/123 (100%) | parsed, failed, or unsupported |

All rows are terminal, but terminal-state completeness is not parser success.
There is currently no parsed attachment text.

## Download Baseline

| Metric | Count | Definition |
| --- | ---: | --- |
| URL_ONLY | 123 | `local_path` is empty |
| LOCAL_BYTES_AVAILABLE | 0 | Database-linked local path is present |
| FILE_HASH_AVAILABLE | 0 | `file_hash` is present |
| DOWNLOAD_ATTEMPTED | 123 | Historical download status is not pending |
| DOWNLOAD_SUCCEEDED | 47 | `download_status=completed` |
| DOWNLOAD_FAILED | 76 | `download_status=failed` |
| DOWNLOAD_ATTEMPT_COVERAGE | 123/123 (100%) | Attempted / current attachments |
| DOWNLOAD_STATUS_SUCCESS_RATE | 47/123 (38.21%) | Completed / attempted |
| REUSABLE_LOCAL_BYTES_RATE | 0/123 (0%) | Linked bytes / current attachments |

The 47 historical `completed` rows do not have a local path or content hash and
must not be treated as reusable downloaded bytes. They comprise 46 unsupported
types and one JPG that later failed with `OCR_UNAVAILABLE`.

## Type And MIME Baseline

No row currently has a persisted MIME value. File extension, parser, extraction
method, type-detection source, and OCR provider audit fields are also empty for all
123 rows. The historical `file_type` distribution is:

| Type | Count | Current parse state |
| --- | ---: | --- |
| PDF | 53 | failed |
| DOCX | 22 | failed |
| XLSX | 1 | failed |
| JPG/JPEG | 1 | failed, OCR required |
| DOC | 16 | unsupported |
| XLS | 2 | unsupported |
| WPS | 13 | unsupported |
| OFD | 7 | unsupported |
| JSP | 4 | unsupported |
| SHTML | 2 | unsupported |
| ET | 1 | unsupported |
| MP4 | 1 | unsupported |
| PNG / WEBP / TXT / HTML / UNKNOWN | 0 | no current row |

The 76 currently parser-eligible document rows are PDF 53, DOCX 22, and XLSX 1.
All 76 failed at the download boundary before parser execution. The two SHTML and
four JSP rows require fresh response MIME/signature detection before deciding
whether they are HTML or unsupported. DOC and XLS remain legacy-format candidates
and must not be counted in DOCX/XLSX parser denominators.

## Failure Distribution

| Terminal state | Error code | Retryable | Count |
| --- | --- | --- | ---: |
| failed | `DOWNLOAD_SSRF_BLOCKED` | false | 76 |
| failed | `OCR_UNAVAILABLE` | false | 1 |
| unsupported | `UNSUPPORTED_FILE_TYPE` | false | 46 |

The 46 unsupported rows are distributed as DOC 16, XLS 2, WPS 13, OFD 7,
JSP 4, SHTML 2, ET 1, and MP4 1. Their historical generic code must be reclassified
only when fresh type detection proves a more specific terminal reason.

## OCR Baseline

- `OCR_PROVIDER_CONFIGURED=false`; the root `.env` contains no OCR provider key or
  provider selection.
- The single known OCR-eligible row is JPG attachment 52. It is honestly failed
  with `OCR_UNAVAILABLE`, has no local bytes, no provider, and no extracted text.
- Scanned-PDF eligibility is currently unknowable because all 53 PDFs failed before
  download and text-layer inspection.

## Audit Findings Before Design

1. `scripts/process_attachments.py` creates a default `HttpFetcher` without the
   configured trusted validation DNS and pinned transport. Current root `.env`
   does have trusted validation DNS configured. This is the leading explanation
   for the 76 historical Fake-IP `DOWNLOAD_SSRF_BLOCKED` outcomes.
2. The downloader already delegates URL validation, redirect validation, public-IP
   checks, response-size limits, and timeouts to the shared `HttpFetcher`; these
   controls must remain unchanged.
3. No production OCR adapter exists. Only the OCR protocol and test fixtures are
   present, so OCR success cannot be claimed without adding and configuring a real
   provider.
4. PDF, DOCX, XLSX, TXT, and HTML parsers already exist. PDF low-text detection
   already marks text-sparse paged files as OCR-required.
5. Attachment-aware chunking, deterministic vector IDs, attachment foreign keys,
   and lineage already exist. Parsing can close first without changing the index
   architecture or silently changing Qdrant.
6. Existing audit fields cover source URL, filename, MIME, type, hash, extraction
   method, parser, OCR provider, attempt time, and errors. Parser version, completed
   time, and OCR latency are not currently persisted.

## Frozen Core Invariants

The following are out of scope and must remain unchanged unless an explicitly
reported attachment-index increment is later approved: documents 182, approved
101, rejected 35, pending 46, chunks 821, Qdrant green/821 points, Human Gold,
Gold Quality, RAG validators, P95 work, Remote Rerank, and Brave Source Discovery.
