# Fresh Runtime Compatibility and Supply-Chain Acceptance Design

Date: 2026-08-05  
Status: Approved by user

## Scope

This change fixes only failures exposed by the fresh production-readiness build:

1. Preserve JSON-array, historical comma-separated, whitespace-trimmed, and empty-value support for list settings under pydantic-settings 2.14.
2. Constrain the production Alembic toolchain to `alembic>=1.18,<1.19` and update the repository's resolved dependency evidence.
3. Identify and remediate the two current frontend high-severity advisories without an unreviewed major upgrade or `npm audit fix --force`.
4. Keep remote embedding acceptance blocked without credentials while verifying explicit failure and deterministic/Mock contracts.
5. Rebuild and re-run the complete local acceptance suite, including Docker Scout under the user's metadata-only upload authorization.

No source-discovery, crawl, RAG, UI, or provider feature is added.

## Configuration Design

List-valued settings that intentionally support legacy CSV input bypass pydantic-settings' automatic JSON decoding and are normalized by application validators. The parser accepts:

- a JSON array of strings;
- a comma-separated string;
- an empty string or empty JSON array;
- an already parsed list.

Items are trimmed and empty entries removed. Invalid JSON-shaped input, non-string elements, and invalid proxy IP/CIDR values raise a field-scoped configuration error. Error text names the field and invalid value category but never prints secrets or unrelated environment content.

Environment-source tests instantiate `Settings()` from patched process environment instead of passing constructor values directly. A container regression starts with the historical Compose CSV default, proving that startup no longer depends on the temporary JSON override.

## Dependency Design

`backend/pyproject.toml` declares `alembic>=1.18,<1.19`. The resolved production dependency artifact is updated so fresh images install an Alembic 1.18.x release. Validation covers:

- the existing PostgreSQL database: `current`, `heads`, and `check`;
- a uniquely named fresh PostgreSQL acceptance database: upgrade to head, downgrade to the selected prior revision, re-upgrade to head, and final `check`;
- cleanup limited to the uniquely named acceptance database.

No generated migration is accepted merely to accommodate Alembic 1.19's changed constraint-name comparison.

## Frontend Advisory Design

The npm audit payload is limited to package names, versions, and dependency relationships. The audit result is classified by direct/transitive and production/development scope. Remediation order is patch/minor update, lockfile refresh, scoped override, then replacement of a development-only dependency. Major upgrades and force fixes are excluded. Lint, type checking, Vitest, build, and Playwright must pass after any lockfile change.

## Provider Boundary

Remote embedding remains the production configuration. With no key, search/chat must return the existing structured provider-unavailable error and must not switch to deterministic vectors. Deterministic and Mock providers remain test-only. Live cited-answer acceptance stays blocked until a real key and representative indexed content are supplied.

## Supply-Chain Boundary

Before Scout/npm calls, commands and generated inputs are checked for credential, `.env`, source, prompt, document, crawl-result, and database content. Allowed outbound metadata is limited to component names, versions, dependency edges, and SBOM fields. A tool requesting broader content stops the scan and records the reason.

## Acceptance

Completion requires:

- targeted and full backend tests;
- frontend lint, type check, Vitest, production build, fixture Playwright, and honest live-stack result;
- fresh backend/frontend and builder builds;
- eight healthy Compose services plus PostgreSQL, Redis, Qdrant, worker, scheduler, Nginx, frontend, and port 8080 checks;
- Alembic existing/fresh database validation;
- pip check, npm audit, Docker Scout SBOM/CVE evidence;
- placeholder-secret scan without printing secret values;
- updated status, readiness report, acceptance checklist, clean worktree, and local Git checkpoint.

External embedding, Coze, Direct LLM, rerank, and Brave success remains unverified unless real credentials and endpoints are independently supplied.
