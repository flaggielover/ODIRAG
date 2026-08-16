# Attachment and OCR Production Closure Design

Date: 2026-08-15
Status: Approved for implementation (Option A)

## Objective

Close the production processing path for the 123 attachments that already exist in
PostgreSQL. Real, safely downloadable files supported by the current parser stack
must reach an auditable terminal state. Image and low-text PDF inputs must enter the
OCR branch, but this environment has no configured production OCR provider, so OCR
work must terminate honestly as unavailable rather than report fabricated success.

The frozen Gold, RAG, rerank, Brave, P95, document, chunk, and Qdrant baselines are
outside this implementation.

## Approved Scope

The implementation will:

- Reuse the existing trusted DNS resolver, public-address validation, pinned
  connection transport, redirect revalidation, DNS rebinding protection, timeout,
  and response-size controls for attachment downloads.
- Process only Attachment rows already present in PostgreSQL. It will not create a
  CrawlTask or expand the corpus.
- Reuse the existing PDF, DOCX, XLSX, TXT, and HTML parsers.
- Route supported images and low-text PDFs into the existing OCR protocol.
- Record `OCR_PROVIDER_UNAVAILABLE` when no provider is configured.
- Preserve provenance and terminal-state audit data.
- Make download and parsing retries deterministic and version-aware.
- Run with bounded concurrency, defaulting to one worker on this machine.
- Leave attachment indexing explicit. The implementation will not automatically
  alter the current 821 database chunks or 821 Qdrant points.

The implementation will not:

- Add Tesseract or another OCR runtime/provider.
- Weaken or duplicate the SSRF validator.
- Add a parallel parse-status state machine.
- Claim that legacy DOC/XLS, corrupt files, blocked URLs, or unavailable OCR parsed
  successfully.
- Redesign attachment versioning, ingestion, search, or citation architecture.
- Change Gold evaluation, evidence validation, RAG, source discovery, reranking, or
  performance behavior.

## Baseline

The read-only production snapshot contains 123 attachments:

- parsed: 0
- failed: 77
- unsupported: 46
- pending: 0
- local bytes: 0
- URL-only: 123
- download status completed: 47, but none has reusable local bytes
- download failed: 76, all currently `DOWNLOAD_SSRF_BLOCKED`
- OCR required: 1 image
- OCR success: 0
- OCR failed: 1, currently `OCR_UNAVAILABLE`

The 76 parser-eligible rows are 53 PDF, 22 DOCX, and 1 XLSX. They all failed at
the download boundary before parser execution.

## Architecture

The processing path is:

```text
Existing Attachment URL
  -> trusted DNS resolution
  -> public IP validation
  -> pinned connection transport
  -> redirect revalidation
  -> bounded download to a temporary file
  -> size, type, hash, and safety checks
  -> atomic rename into attachment storage
  -> parser dispatch or OCR dispatch
  -> extracted text and provenance
  -> parsed, failed, or unsupported terminal state
```

### Hardened Fetcher Factory

An attachment-specific factory will compose the existing `DohHostResolver`,
`PinnedAsyncHTTPTransport`, `HttpFetcher`, and existing URL validator. It will use
the attachment download size limit instead of the source-discovery response limit.
No URL class, network range, redirect rule, or DNS rebinding check will be relaxed.

The factory owns and closes its HTTP client. A trusted DNS endpoint is required for
the real reprocess command. A missing trusted DNS configuration is a configuration
failure, not permission to fall back to unsafe or split-resolution networking.

### Atomic Storage

Downloaded bytes are written inside the configured attachment storage root to a
unique temporary file. The path is derived from the document and attachment
identity, not only from the untrusted filename.

The worker performs the configured maximum-size check, file-type detection, and
SHA-256 calculation from the actual downloaded bytes. URL, filename, ETag, and
other response metadata may be saved as auxiliary evidence but never replace the
byte-derived content hash.

Only after checks succeed is the temporary file atomically renamed to the final
path. Any exception, timeout, cancellation, failed type check, or parser crash
removes the temporary file. Existing completed content is not destroyed by a
failed forced retry.

### Type Detection

Detection evaluates:

1. non-generic HTTP Content-Type;
2. Content-Disposition filename;
3. magic bytes or container signature;
4. attachment filename suffix;
5. URL path suffix.

Generic `application/octet-stream` does not override stronger evidence. The
detector handles Chinese and percent-encoded filenames, queries, missing suffixes,
and bounded/sanitized filenames. Conflicting MIME, signature, and suffix evidence
is resolved by the approved precedence and the winning `type_detection_source` is
persisted for audit; a generic MIME never masks magic bytes.

Supported outcomes are PDF, DOCX, XLSX, TXT, HTML, JPEG, PNG, and WebP. DOC and
XLS terminate as `unsupported` with `UNSUPPORTED_LEGACY_FORMAT`. Other unsupported
formats retain an explicit reason.

### Parsing and OCR

The existing parser registry remains the dispatcher. Parsers receive only files
that passed the download maximum-size check; parsing rechecks the actual local file
size before reading it. Parser exceptions become explicit, sanitized error codes
and never execute Office macros, embedded objects, or file-contained code.

PDF first extracts its text layer. A paged PDF whose effective text density is
below the existing threshold is marked `needs_ocr=true` and enters the OCR branch.
JPEG, PNG, and WebP enter the same branch directly.

This environment has no production OCR adapter. Therefore the OCR branch uses the
existing `parse_status=failed` terminal state with:

- `error_code=OCR_PROVIDER_UNAVAILABLE`
- `requires_ocr=true`
- `ocr_status=failed`
- `ocr_provider=NULL`
- `retryable=false` for this run, because no configured provider exists and a
  repeated row-level attempt cannot succeed without an environment change

The report classifies attachment OCR as PARTIAL. A later provider configuration is
an external-state change that makes these rows operationally eligible again; it
does not require a new parse status.

### Provenance and Audit

Successful extracted text remains on the Attachment and is not merged into the
Document body. The auditable record includes:

- attachment and document IDs;
- source/attachment URL and filename;
- response content type and detected file type;
- byte-derived SHA-256 hash and file size;
- detection source and extraction method;
- parser name and parser version;
- OCR provider/version when applicable;
- OCR page count, text length, and latency when attempted;
- parse attempt and processed timestamps;
- terminal status, sanitized error code/message, and retryability.

A minimal migration adds only missing audit fields required by this contract. It
does not add an attachment history table or change chunk/index schemas.

## Cache and Idempotency

Download identity is the SHA-256 hash of actual downloaded bytes. A URL, filename,
or ETag by itself is never a cache identity.

Parsing is reusable only when all applicable identity fields match:

```text
content_hash + parser_name + parser_version
```

For OCR-produced text, the cache identity additionally includes:

```text
ocr_provider + ocr_version
```

A matching successful result is `CACHE_HIT/UNCHANGED` and does not parse, OCR,
chunk, embed, or add a Qdrant point again. A changed content hash or processor
version reprocesses the file. A failed forced download preserves the previous valid
file/result but records the failed attempt consistently; a subsequent cache check
must not return a successful status from a contradictory row.

Because this closure does not trigger reindexing, duplicate chunk and Qdrant point
counts must remain zero and the frozen 821/821 baseline must not change.

## Worker and Eligibility

The command supports an explicit attachment-ID sample and an eligible-only batch.
Selection is ordered and paged rather than repeatedly taking the first N rows.
Default concurrency is one, with a small explicit upper bound.

Eligible rows are current attachments that are:

- pending;
- retryable failed;
- historical `DOWNLOAD_SSRF_BLOCKED` rows requiring revalidation under the hardened
  transport; or
- OCR-required rows.

Known nonretryable corrupt files, confirmed legacy formats, policy-level URL
denials, and terminal unsupported formats are excluded from the batch. Historical
SSRF outcomes are not automatically trusted or unblocked; every URL is fully
validated again.

The controlled sample is executed once before the batch and contains two PDFs, one
DOCX, one XLSX, one image, one historical SSRF-blocked row, and one legacy Office
row. Some roles may be represented by the same row only where the report states the
overlap explicitly.

## Error Contract

Every processed row ends as `parsed`, `failed`, or `unsupported`. No row is left
permanently pending, and no failed/unsupported row lacks a reason.

The closure distinguishes at least:

- safe-download denial and transport failures;
- too-large files and timeouts;
- type-detection failure;
- corrupt or empty content;
- unsupported legacy and other unsupported formats;
- parser failure;
- OCR provider unavailable;
- OCR execution failure.

Messages saved to the database are sanitized and contain no credentials or secret
configuration. Provider secrets are never persisted or printed.

## Verification

Targeted tests cover the 24 required cases: text PDF, scanned PDF, DOCX, XLSX,
image OCR routing, Chinese and encoded filenames, no suffix, octet-stream,
MIME/suffix conflict, corrupt files, legacy DOC/XLS, oversized files, timeout,
private IP blocking, Fake-IP validation separation, private redirect, DNS
rebinding, cache hit, changed hash, OCR unavailable, OCR failure, and provenance.

Additional assertions cover:

- cache invalidation when parser or OCR version changes;
- byte-derived content hashes;
- temporary-file cleanup and atomic replacement;
- no successful cache response from a contradictory failed row;
- bounded sample/batch selection;
- unchanged chunks and Qdrant point counts.

Execution is limited to one targeted test pass, one real sample, one eligible batch,
and one final regression. The final regression includes backend pytest, Ruff check,
Ruff format check, mypy, compileall, Alembic check, and the documented bounded
Windows Black attempt.

## Acceptance and Reporting

Metrics use distinct denominators for download, parser eligibility, and OCR
eligibility. The report includes before/after totals, per-type parse success,
terminal-state coverage, failure/unsupported distributions, security regression,
cache/idempotency evidence, and quality inspection of ten parsed attachments or all
parsed attachments if fewer than ten exist.

Final statuses are reported independently for attachment download, parsing, OCR,
provenance, and terminal-state closure. OCR remains PARTIAL when the production
provider is unavailable, even if all OCR rows have correct terminal states.

Frozen core acceptance verifies that the 5/5 live closed loop, reranker, Brave,
Human Evaluation, Gold artifacts, document counts, chunks, and Qdrant baseline did
not silently change.
