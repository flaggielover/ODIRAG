# Security Readiness Report

> Historical checkpoint: this 2026-08-13 pre-production security audit is intentionally retained
> unchanged below. Its `PRODUCTION-SECURITY-NOT-ACCEPTED` verdict was superseded by the live Phase
> 1-5 acceptance in `PRODUCTION_READINESS_REPORT.md` and `PRODUCTION_PHASE_5_REPORT.md`. Residual
> risks documented by the later reports, including single-node architecture, SSH CIDR, Qdrant
> version alignment, conservative HSTS, external paging, and attachment/OCR boundaries, remain.

Date: 2026-08-13
Status: **DEVELOPMENT-STACK-VERIFIED / PRODUCTION-SECURITY-NOT-ACCEPTED**

## Verified controls

- Backend runs as non-root UID 10001.
- Stateful ports are bound to loopback in the local Compose reference topology.
- Nginx provides request-size limits, proxy headers, health checks and baseline security headers.
- Application logging uses structured events and request IDs; health errors are normalized rather than exposing dependency responses.
- Provider credentials are injected from ignored local environment configuration and only `configured=true|false` is reported.
- Repository history does not include `.env`; no API key value is included in the generated reports.
- Existing authentication, rate limiting, SSRF controls, official-source Grounding, Evidence Sufficiency and citation validation remain enabled.
- Full and production-only `npm audit` most recently reported zero package-manager vulnerabilities.
- Latest recorded Scout scan: backend `0C/0H/0M/0L`; frontend `0C/0H/0M/3L`. The three low Alpine `libxml2` findings had no fixed package at the recorded scan and remain open, not resolved.

## Production blockers

| Area | Current state | Required production evidence |
|---|---|---|
| TLS | local HTTP only | TLS 1.2+, trusted certificate, HTTP redirect, production-only HSTS, tested CSP |
| Secrets | local `.env` injection | external secret manager/Docker secrets, rotation, least privilege and audit |
| Environment | `development`, JSON logs disabled, bootstrap admin enabled | hardened production configuration and bootstrap disabled after provisioning |
| Stateful access | local loopback exposure; no production ACL evidence | private network plus PostgreSQL/Redis/Qdrant authentication and authorization |
| Container resources | no CPU/memory limits | measured limits/reservations, OOM policy and capacity test |
| Logging | Docker default `json-file`, no size/age limits | rotation, centralized collection, retention and access controls |
| Alert delivery | database/API alerts only | external notification route, ownership, escalation and test alert |
| Supply chain | local digests/SBOM scans recorded | immutable registry digest, signed provenance and protected release workflow |
| Backup data | no automated encrypted backups | encryption, off-host retention, restore audit and access controls |

## Live external gates

- Remote rerank: `BLOCKED-EXTERNAL-RERANK-KEY`.
- Brave Search source discovery: `BLOCKED-EXTERNAL-BRAVE-KEY`.
- Production TLS/DNS and registry credentials: `BLOCKED-PRODUCTION`.
- Human verification of the 100-case evaluation draft: `BLOCKED-HUMAN-EVAL-REVIEW`.

Disabled/deterministic providers and fixture tests are not counted as live provider acceptance. The historical `association` source classification and corrupt `region='??'` values were not rewritten to improve acceptance status.
