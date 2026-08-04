# Frontend end-to-end tests

The default Playwright suite is fixture-backed. It intercepts `/api/*` requests
inside the browser and verifies frontend routing, rendering, request payloads,
and critical interactions without requiring PostgreSQL, Redis, Qdrant, Celery,
or model providers.

Fixture-backed success is **not** evidence that a production integration works.
It verifies the browser application contract only.

## Fixture-backed suite

```powershell
npm install
npx playwright install chromium
npm run test:e2e
```

Expected result: all fixture-backed tests pass and the live-stack test is
reported as skipped.

## Live-stack acceptance gate

Start a complete stack with seeded, indexed knowledge that can answer the test
query with at least one citation. Then run:

```powershell
$env:E2E_LIVE = '1'
$env:E2E_BASE_URL = 'https://odirag.example.com'
$env:E2E_USERNAME = '<acceptance-user>'
$env:E2E_PASSWORD = '<acceptance-password>'
$env:E2E_QUERY = '企业研发投入有哪些支持措施？'
npm run test:e2e -- e2e/live-stack.spec.ts
```

Expected result: one live-stack test passes. It performs real login and verifies
the dashboard, sources, documents, a cited chat answer, and monitoring without
request interception. An external `E2E_BASE_URL` disables Playwright's local
Vite `webServer`; the target must already be reachable.
