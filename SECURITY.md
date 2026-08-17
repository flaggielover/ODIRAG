# Security

## Implemented Controls

- JWT access and refresh tokens carry a persisted token version. Refresh rotates the version;
  replayed refresh tokens and old access tokens fail, and logout revokes the current family.
- Production/staging settings reject debug mode, default/short signing keys, plaintext admin
  passwords, disabled rate limiting, and wildcard or non-HTTPS CORS origins.
- Protected endpoints require bearer authentication; administrative operations require the
  superuser dependency.
- Error responses use stable codes and request IDs. Raw provider reasons are logged but not exposed
  to clients.
- The crawler accepts only HTTP(S), rejects URL credentials, localhost, private/link-local/
  reserved/multicast/unspecified IPs, resolves DNS before requests, revalidates each redirect, and
  enforces timeout, redirect, `Content-Length`, and streamed byte limits.
- Attachment extensions, sizes, safe names, and storage containment are validated. ZIP parsing
  records unsafe paths rather than extracting arbitrary archive content.
- SQL query routing uses fixed SQLAlchemy templates; no model-generated SQL is executed.
- Citations are constructed from stored document/chunk identities and stored source URLs.
- Vue renders operational/document/chat values as escaped text. No arbitrary source HTML is
  inserted into the DOM.
- Crawl tasks use database-backed atomic claims, uniqueness constraints, idempotent state
  transitions, late acknowledgements, bounded retries/time limits, and stale-worker recovery.
- Backend containers run as non-root UID 10001 and receive a dedicated writable `/app/data` volume.
- Source discovery uses the Brave API only for candidate hints; every homepage and redirect passes
  the same public-DNS/SSRF policy as crawling. Trusted suffix, HTTPS, same-site, marker, and HTTP
  evidence are persisted before a candidate can reach `pending_approval`.
- Candidate columns are trial-crawled with bounded URL/document/byte limits. Activation is a
  separate authenticated action after manual approval, and append-only stage events make rejected,
  failed, and activated outcomes inspectable.

## Rate Limiting

Authentication, expensive search/chat/evaluation operations, and default API traffic have separate
fixed-window limits. Production and other non-test environments use the shared Redis-backed limiter
and fail closed when Redis is unavailable; the in-memory implementation is test-only. A 429
response includes `Retry-After` and `X-RateLimit-*` headers. Any future multi-replica deployment
must revalidate shared-counter capacity, trusted-proxy identity, and ingress behavior.

## Secrets

Never commit `.env`, real database URLs/passwords, JWT keys, provider tokens, private source data,
TLS private keys, or authentication headers. `.env.example` contains development-only values.
Production must inject a high-entropy signing key, a precomputed administrator password hash, and
provider credentials through an orchestrator secret or secret manager. Vite variables are public
build inputs and must never contain secrets.

Rotate credentials if they appear in logs, CI output, an image layer, generated artifacts, or Git
history. Disable plaintext admin bootstrap after the first controlled setup.

## Network and Deployment

Only the TLS ingress should be public. PostgreSQL, Redis, Qdrant, backend management ports, and
worker traffic belong on private networks with service authentication/TLS where supported. Keep
CORS origins exact; CORS is not authorization.

`ODIRAG_TRUSTED_PROXY_IPS` is an allowlist of peer IP addresses/CIDRs, not a proxy URL setting.
It accepts a JSON string array, the legacy comma-separated form, or an empty value. Invalid values
fail closed during configuration loading, and validation output suppresses the supplied value so
an accidentally pasted proxy credential is not copied into startup logs.

Source-discovery and attachment fetching can combine trusted DoH resolution with a pinned
transport so the validated public IP is the connection target. That protection is path- and
configuration-scoped; general crawling and other outbound integrations still require review.
An egress proxy/firewall that blocks private and cloud-metadata ranges remains defense in depth.

Source-discovery official status is a policy signal, not a legal attestation: a trusted domain suffix
and reachable homepage do not prove that every linked document is authoritative. Operators must
review candidates and configure an appropriate suffix allowlist for their jurisdiction. One bounded
Brave campaign was live-verified, but every future campaign still depends on external API/network
availability, search quality, jurisdiction policy, and an accountable reviewer. Missing credentials
are surfaced as `503`, never replaced by fixture results.

The root Compose file is a development/reference topology. The accepted production topology in
`deploy/production/compose.yml` adds TLS ingress, protected runtime configuration, resource limits,
private service networking, Redis authentication, backup/restore controls,
Prometheus/Grafana/Alertmanager, shared Redis rate limiting, immutable release/rollback controls,
CI, SPDX SBOMs, and BuildKit provenance. See
[`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md). Production remains single-node
rather than highly available, and the crawler egress boundary above remains applicable.

## Data, Logs, and Privacy

Do not log passwords, tokens, authorization headers, provider keys, or unrestricted document
bodies. Define retention and access policies for source evidence, attachments, user queries,
feedback, traces, and evaluation artifacts. Back up PostgreSQL and accepted source evidence;
snapshot Qdrant when useful, while retaining the ability to rebuild vectors from approved chunks
and recorded provider versions. Redis is not the source of truth.

## Vulnerability Reporting

Until a dedicated security contact is published, send exploitable details privately to the
repository owner. Include the affected revision, impact, minimal reproduction, and mitigation.
Do not publish credentials or a working exploit in a public issue before coordinated remediation.
