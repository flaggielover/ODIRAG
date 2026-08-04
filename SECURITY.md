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
fixed-window limits. A 429 response includes `Retry-After` and `X-RateLimit-*` headers. The current
limiter is in-process. Before running multiple API replicas, use a Redis-backed limiter or enforce
equivalent limits at a trusted ingress so counters are shared.

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

Application URL checks reduce SSRF risk but cannot completely eliminate DNS rebinding between
validation and connection. Production crawling should also use an egress proxy/firewall that
blocks private and cloud metadata ranges and, ideally, pins the validated destination IP while
preserving TLS SNI.

Source-discovery official status is a policy signal, not a legal attestation: a trusted domain suffix
and reachable homepage do not prove that every linked document is authoritative. Operators must
review candidates and configure an appropriate suffix allowlist for their jurisdiction. Brave API
availability, search ranking quality, and live government-site reachability remain external gates;
missing credentials are surfaced as `503`, never replaced by fixture results.

The Compose file is a development/reference topology. Before production use, add TLS termination,
external secret injection, resource limits, authenticated stateful services, backup/restore
automation, centralized logs/metrics, distributed rate limiting, image/dependency scanning, and a
deployment-specific security review.

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
