# Coze Batch Crawl Implementation Plan

Date: 2026-08-04

## Scope

Implement the local half of the approved dual-contract Coze integration while
leaving the existing `legacy_single_article` deployment unchanged. The batch
deployment URL is optional until the user publishes it; missing configuration
must produce an explicit status rather than startup or HTTP 500 failure.

## Work order

1. Add redacted, backward-compatible Coze settings and configuration-status
   tests in `backend/app/config.py`, `.env.example`, and Compose configuration.
2. Add strict batch input/result schemas and the `CrawlProvider` interface,
   `CozeCrawlProvider`, and `LocalCrawlProvider` boundary under
   `backend/app/crawl_providers/`.
3. Add `Source.crawl_provider`, provider-aware task fields, invocation
   persistence, indexes, constraints, model exports, and Alembic migration
   `0005_coze_batch_crawl.py`.
4. Extend task state transitions, repository operations, worker recovery, raw
   response persistence, normalization, document/review/attachment creation,
   idempotency, cancellation, and error classification.
5. Expose redacted configuration status, separate Coze/local connectivity,
   provider-aware source responses, task detail/invocation responses, and the
   Live Acceptance creation path.
6. Update Vue API types, source controls, task statuses/details, status labels,
   UTF-8 tests, Vitest fixtures, and Playwright critical journey fixtures.
7. Add `docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md`, ten Coze console cases, four
   sample responses, and a local Live Acceptance script/command.
8. Run Alembic upgrade/downgrade checks, targeted backend tests, full backend
   lint/type/test/coverage, frontend lint/type/Vitest/build/Playwright, and local
   Compose checks available without the new deployment URL.
9. Update `IMPLEMENTATION_STATUS.md`, `PRODUCTION_READINESS_REPORT.md`, and
   `PRODUCTION_ACCEPTANCE_CHECKLIST.md` with verified/fixture/unverified labels.

## Acceptance boundary

Fixture success verifies client behavior and local persistence only. The batch
workflow remains below PASS-LIVE until a new `COZE_BATCH_API_URL` returns a
real strict batch response for at most five articles and one page and produces
real persisted documents. Tasks 4-7 now provide live-diagnostic transport
evidence, but task 7 returned `NO_ARTICLES` and zero documents for a populated
dynamic SPA. The current local image adds strict task-ID validation and
fail-closed response matching without fabricating another live result. No test
may send the new batch payload to the legacy deployment or expose its token.
