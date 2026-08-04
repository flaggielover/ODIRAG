# Coze Batch Crawl Integration Design

Date: 2026-08-04

## Goal

Keep the existing single-article Coze deployment unchanged and add a separate
batch-crawl deployment for the RAG system. The new deployment owns column
discovery, pagination, article/detail extraction, attachment discovery, image
content detection, and per-article quality decisions. The local application
owns task orchestration, durable persistence, review, document processing,
embedding, vector storage, search, and RAG.

## Contracts

The provider supports two deployment contracts behind one interface:

- `legacy_single_article`: the existing `COZE_LEGACY_API_URL` deployment. It
  receives the old article-level JSON directly and remains available only for
  compatibility and regression checks.
- `batch_crawl`: the new `COZE_BATCH_API_URL` deployment. It receives the
  source/task batch input directly as JSON and returns the strict batch result
  object described in `docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md`.

The deployment URL form is intentionally supported because the reference
implementation uses `https://<deployment>.coze.site/run`. A future OpenAPI
workflow endpoint may be added behind the same provider without changing the
business service. The batch URL is optional at startup; when absent, the
application reports `batch_workflow_not_published` and keeps the legacy/local
paths usable.

## Architecture

`CrawlProvider` exposes `test_connection`, `start_crawl`, `get_task_status`,
`cancel_task`, and `normalize_result`. `CozeCrawlProvider` owns HTTP
authentication, timeout, exponential retry, deployment-contract selection,
response capture, and schema normalization. It never logs or returns tokens.
`LocalCrawlProvider` wraps the existing crawler as an explicit fallback and
diagnostic path; it is not the default source provider.

The worker creates a local task, claims it, records an invocation before the
request, calls the selected provider, persists the raw response regardless of
normalization success, then normalizes and saves each article independently.
The batch deployment is synchronous today, so `coze_running` covers the remote
HTTP execution. The task model still stores `coze_execution_id` and polling
metadata so an async deployment can be added without changing the API or UI.

## Persistence and state

`Source.crawl_provider` defaults to `coze`. `CrawlTask` gains the provider,
contract, execution ID, stage/error fields, accepted/rejected/pending-review
counters, and durable retry metadata. `CozeInvocation` stores request JSON,
raw response JSON, normalized response JSON, status/timing/HTTP/retry/token
usage metadata, and error details in separate columns. Secrets are excluded
from both request persistence and logs.

The state machine accepts:

`pending -> queued -> calling_coze -> coze_running -> normalizing ->
saving_documents -> waiting_review -> completed | partial_failed | failed |
cancelled`.

Accepted and pending-review articles become reviewable local documents; rejected
articles and per-article failures remain queryable with reasons and URLs but do
not enter the vector store. URL/title/content/attachment fingerprints provide
idempotency for repeated tasks.

## API and frontend

The backend exposes separate Coze and local connectivity checks, a redacted
Coze configuration status endpoint, provider-aware source/task responses, and a
task detail endpoint with execution and invocation metadata. The frontend
labels legacy availability, batch-not-published, batch availability, invalid
token, timeout, contract mismatch, no articles, partial success, complete
success, and invalid JSON separately. It never calls Coze directly.

## Error handling

Timeouts, connection failures, 429, and 5xx use bounded exponential backoff.
401/403, invalid workflow/deployment configuration, and schema mismatches are
non-retryable configuration or contract errors. A failed article does not erase
successful articles. A batch with at least one successful article and failures
is `partial_failed`; malformed top-level results are `failed` while retaining
the raw response.

SSRF validation remains unchanged and `198.18.0.0/15` is never allowlisted.
Local connectivity failures are diagnostic only and cannot imply Coze
unavailability.

## Verification

Fixture tests cover both deployment contracts, retries, schema failures,
idempotency, UTF-8, task state recovery, and frontend status rendering. The
repository includes an explicit Live Acceptance command using
`max_articles=5` and `max_pages=1`, but it remains unverified until the new
Coze batch URL is configured and a real response is observed. The existing
single-article endpoint is not used to claim batch-crawl acceptance.
