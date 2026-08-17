# ODIRAG Production Phase 5 Report

Evidence window: 2026-08-17 (Asia/Shanghai), with external service timestamps recorded in UTC.

## Result

`PHASE_5_OVERALL=PASS-LIVE`

`PRODUCTION_READINESS=PASS-LIVE`

The final public production endpoint is:

<https://rag.suzheodirag.top/>

The launch used the existing single-node production stack. No PostgreSQL data,
Redis state, Qdrant collection, attachment byte, Docker volume, backup artifact,
or rollback release was deleted or overwritten.

## Gate Matrix

| Gate | Status | Live evidence |
| --- | --- | --- |
| DOMAIN | PASS-LIVE | `rag.suzheodirag.top` is the active production hostname. |
| DNS | PASS-LIVE | Production host, Google DoH, and Cloudflare DoH resolved the A record to `45.192.110.8`. |
| PUBLIC_FIREWALL | PASS-LIVE | UFW is active; only 80, 443, and management SSH 22022 are allowed inbound. |
| PUBLIC_NGINX | PASS-LIVE | Host Nginx is active, its configuration validates, and it proxies only to `127.0.0.1:8080`. |
| TLS | PASS-LIVE | Publicly trusted Let's Encrypt certificate, valid chain and hostname, TLS 1.2/1.3 accepted. |
| TLS_RENEWAL | PASS-LIVE | Certbot timer active; staging renewal succeeded; root-owned reload hook passed. |
| HTTPS | PASS-LIVE | Independent workstation reached `45.192.110.8:443`; trusted HTTPS root and health probes returned 200. |
| HTTPS_REDIRECT | PASS-LIVE | Public HTTP returned 308 to the exact HTTPS hostname without a loop. |
| SECURITY_HEADERS | PASS-LIVE | HSTS, CSP, frame protection, nosniff, referrer and permissions policies appear exactly once. |
| PUBLIC_FRONTEND | PASS-LIVE | Real headless Chrome loaded the final HTTPS frontend with trusted TLS and no page/CSP errors. |
| PUBLIC_API | PASS-LIVE | Browser session reached `/api/auth/me`, `/api/chat`, exact Trace endpoints, and received HTTP 200. |
| PUBLIC_RAG | PASS-LIVE | Public browser path exercised Bailian, BM25, Qdrant vector retrieval, fusion, Cohere, DeepSeek, citation and answer-support validation. |
| PUBLIC_REFUSAL | PASS-LIVE | Public out-of-scope query refused for `insufficient_evidence_relevance`, with no citation, token cost, or Direct LLM call. |
| EXTERNAL_UPTIME | PASS-LIVE | Two continuous public-HTTPS Blackbox targets are up; independent workstation DNS/TCP/TLS/HTTP probe passed. |
| MONITORING_REGRESSION | PASS-LIVE | Prometheus, Grafana and Alertmanager healthy; 12/12 targets up; three public alert rules loaded. |
| DR_REGRESSION | PASS-LIVE | Server backup manifest 7/7 and off-host copy 7/7 verified; no restore or destructive drill was repeated. |
| ROLLBACK_REGRESSION | PASS-LIVE | Phase 4 real rollback evidence retained; R6 current, R4 previous, journal absent, previous descriptor/images validated. |
| ATTACK_SURFACE | PASS-LIVE | External scan found only 80/443/22022 reachable; all internal and monitoring ports were unreachable. |
| PRODUCTION_REGRESSION | PASS-LIVE | 531 backend tests and full static/frontend/config checks passed; real production Provider regression passed. |
| DATA_INTEGRITY | PASS-LIVE | Frozen PostgreSQL/Qdrant/attachment invariants and exact ID equality passed after public E2E. |
| PHASE_5_OVERALL | PASS-LIVE | All critical public-production Gates have real execution evidence. |
| PRODUCTION_READINESS | PASS-LIVE | Production Phases 1 through 5 are accepted with the residual risks listed below. |

## DNS and Network

- Domain: `rag.suzheodirag.top`.
- Expected and observed IPv4: `45.192.110.8`.
- Independent resolvers: Google DoH and Cloudflare DoH returned the same address;
  the production host also returned the same address.
- The Windows workstation's ordinary DNS is subject to a local fake-IP layer and
  was not used as authoritative DNS evidence.
- UFW public rules: TCP 80, TCP 443, and TCP 22022, for IPv4 and IPv6.
- Host public listeners: Nginx 80/443 and sshd 22022.
- Host loopback listeners: 8080, 3000, 9090, and 9093.
- Docker publishes no wildcard port. Application gateway and monitoring UIs remain
  bound to `127.0.0.1`; database, Redis, Qdrant, backend, and exporters have no host
  publication.

The independent workstation probe found these ports reachable: `80`, `443`, and
`22022`. It found `22`, `8080`, `3000`, `9090`, `9093`, `8000`, `5432`, `6379`,
`6333`, `6334`, `9100`, `9115`, `9121`, and `9187` closed or filtered.

## Nginx and TLS

Host Nginx terminates TLS and proxies the final public hostname to the existing
container gateway at `127.0.0.1:8080`. The container gateway keeps backend,
frontend, and stateful services on Docker-private networks. Forwarded client and
scheme headers are overwritten at the trusted host boundary before they reach the
container gateway.

Active host configuration:

```text
/etc/nginx/sites-enabled/odirag-public
  -> /etc/nginx/sites-available/odirag-public-final
configuration_sha256=cedb5f013aaeda3bd7c957f5adbce119dea672c5b3b7dea0e795eafb0e6ce710
```

Certificate evidence:

```text
subject=CN=rag.suzheodirag.top
SAN=DNS:rag.suzheodirag.top
issuer=C=US, O=Let's Encrypt, CN=YR2
notBefore=2026-08-16T18:04:46Z
notAfter=2026-11-14T18:04:45Z
sha256_fingerprint=3A:9F:A6:70:A1:C7:01:50:0E:CD:25:07:E7:50:9D:5D:8B:BC:1C:E4:39:9F:D2:42:2D:7F:7B:F0:B2:19:3F:35
```

TLS 1.0 and 1.1 were rejected. TLS 1.2 and 1.3 succeeded with certificate-chain
and hostname verification enabled. Certbot's staging renewal completed
successfully. The installed deploy hook validated and reloaded Nginx. The target
Certbot 1.21 does not support `--run-deploy-hooks` during dry-run, so the staging
renewal and the exact installed hook were tested sequentially.

HTTP returned `308` to `https://rag.suzheodirag.top/`. HTTPS returned `200` for
`/`, `/health/live`, `/health/ready`, and `/healthz`. Unknown HTTP Host traffic was
closed by the default server.

Final browser-compatible security headers:

```text
Strict-Transport-Security: max-age=86400
Content-Security-Policy: default-src 'self'; base-uri 'self'; frame-ancestors 'none'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' ws: wss:;
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), geolocation=(), microphone=()
```

The edge hides duplicate upstream security headers. Each final header was observed
exactly once.

## Release and Public E2E

R6 production identity:

```text
release=v0.1.0-r6
source_commit=31694f725cbe7f1ee9efcb4291175e734de1d3c9
backend=ghcr.io/flaggielover/odirag-backend@sha256:144d2107497ed338ca7d18d7cd4354ff79eed7285dd8e870c4b0771431bd5ae8
frontend=ghcr.io/flaggielover/odirag-frontend@sha256:db49c94c0effd455a07a9670c620b312905f561e63370aa3e9e41e524de010a2
current=/opt/odirag/releases/v0.1.0-r6
previous=/opt/odirag/releases/v0.1.0-r4
journal=absent
```

Release workflow `31967143208` produced the immutable images, SPDX SBOMs, and
BuildKit provenance. Production deployment workflow `31968570946` completed in
4m57s; the release transaction recorded 245.315 seconds. Its data and Provider
Gates passed before the current pointer was committed. The ephemeral self-hosted
runner deregistered and exited after the job.

The public browser used trusted TLS and a five-minute access JWT transferred only
through process memory. It did not record screenshots, video, browser trace, token,
answer, citation text, Prompt, or full Query Trace. No login password or refresh
credential was created. The token-signing query ran in a read-only database
transaction.

Public Grounded RAG evidence:

```text
HTTP chat=200, trace=200
query_type=rag
citations=1
BM25=20
vector=20
fusion=8
rerank=8
final=5
rerank_adapter=remote
rerank_service=cohere
rerank_model=rerank-v3.5
llm_model=deepseek-v4-flash
answer_support_validated=true
```

Public refusal evidence:

```text
HTTP chat=200, trace=200
reason=insufficient_evidence_relevance
citations=0
BM25=20
vector=20
rerank=8
direct_llm_called=false
tokens=0
cost=0
```

The successful browser run wrote two normal production Query Traces. An earlier
Grounded request also completed server-side before a client assertion discovered
that the generic Trace adapter name is `remote`, not the service name `cohere`.
No data was deleted to hide this evidence. The exact Phase 5 acceptance write
boundary is therefore three Query Traces: two Grounded attempts and one refusal.
Credential database writes were zero.

## External Uptime and Monitoring

A root-owned monitoring bundle was installed at:

```text
/opt/odirag/monitoring/releases/phase5-20260817T202500Z
/opt/odirag/monitoring/current -> that release
/opt/odirag/monitoring/previous -> retained Phase 3 configuration
```

Only Prometheus was recreated to bind the versioned configuration. The named TSDB
volume `odirag-monitoring-prometheus` was preserved. Promtool validated the
Prometheus file and eight rule files.

Persistent host-origin Blackbox probes use the real public HTTPS hostname for `/`
and `/health/ready`. Both report:

```text
probe_success=1
probe_http_status_code=200
probe_http_ssl=1
probe_http_redirects=0
certificate_expiry_greater_than_21_days=true
```

Prometheus has 12/12 targets up. Rules `PublicHttpsProbeScrapeDown`,
`PublicHttpsProbeFailed`, and `PublicTlsCertificateExpiringSoon` are loaded.
Prometheus, Grafana, Alertmanager, and Blackbox administration remain private.

The independent workstation supplied the required outside-host DNS, TCP 443,
trusted TLS, root, and readiness verification. No existing third-party uptime or
paging account was available; no paid service or fabricated third-party monitoring
was created.

## Monitoring, DR, and Rollback Regression

- Prometheus, Grafana, and Alertmanager returned healthy/ready responses.
- Twelve Prometheus targets and both public probes were up.
- Server backup manifest: 7/7 artifacts matched size and SHA-256.
- Off-host workstation backup: 9 files, 119,923,885 bytes; 7/7 manifest artifacts
  matched size and SHA-256.
- Restore-test entries: 0. Partial backup files: 0.
- A destructive restore drill was not repeated; Phase 2's isolated live drill and
  RPO/RTO evidence remain authoritative.
- Phase 4's real authenticated R5 to R4 rollback remains authoritative.
- Current rollback state is R6 current, R4 previous, no journal; the R4 descriptor,
  local immutable image identities, Compose model, and migration compatibility
  validated without activating it.

## Tests and Production Regression

Final validation results:

```text
backend pytest: 531 passed in 26.25s
Ruff: all checks passed
Black: 247 files unchanged
mypy: 171 source files, no issues
release integrity tests: 5 passed
frontend lint: passed
frontend type-check: passed
frontend Vitest: 18 passed
frontend fixture Playwright: 10 passed; 1 explicit live-stack skip
frontend production build: 1850 modules transformed
Compose config: 3 models passed
actionlint: passed
git diff --check: passed
Nginx validation: public container syntax and host syntax passed
```

The parallel fixture Playwright run initially timed out one login navigation after
nine other tests passed. The exact failed `knowledge.spec.ts` was rerun unchanged
with one worker and passed in 1.7 seconds. The separate real public browser E2E is
the authoritative live-stack evidence.

The final no-write production Provider regression reported:

```text
embedding_provider=bailian
embedding_model=text-embedding-v4
embedding_latency_ms=549.855
vector_length=1536
BM25=20
vector=20
fusion=8
rerank=8
final=5
rerank_provider=cohere
rerank_model=rerank-v3.5
llm_provider=deepseek
llm_model=deepseek-v4-flash
direct_llm_latency_ms=2351.819
citations=1
tokens_positive=true
answer_support_validated=true
out_of_scope_refusal=true
refusal_direct_llm_called=false
transaction_read_only=true
production_trace_writes=0
```

## Data Integrity

```text
documents=182
chunks=821
parsed_attachments=60
attachment_files=69
live_attachment_sha256_matches=69
duplicate_chunk_id=0
duplicate_document_chunk_index=0
active_collection=odirag_chunks_bailian_v4
active_qdrant_status=green
active_qdrant_points=821
active_qdrant_dimensions=1536
active_qdrant_distance=cosine
rollback_collection=odirag_chunks
rollback_qdrant_status=green
rollback_qdrant_points=821
rollback_qdrant_dimensions=1536
rollback_qdrant_distance=cosine
duplicate_active_qdrant_payload_chunk_id=0
point_payload_ids_equal=true
postgres_qdrant_id_set_equal=true
```

The active and rollback Qdrant collections remain present. The closed attachment
pipeline was not modified. Live attachment bytes matched the accepted Phase 2
69-file checksum list.

## Representative Commands Executed

The following command families were actually executed. Secret values were never
placed in command output or reports.

```text
ssh rag-prod sudo -n whoami
dig/getent/resolvectl plus Google and Cloudflare DoH resolution
ufw status / ufw allow 80,443 with explicit comments
nginx -t / systemctl reload nginx
certbot certonly --webroot ...
certbot renew --dry-run ...
openssl s_client protocol/chain checks
curl --resolve public HTTP/HTTPS and health probes
gh workflow run/view/watch for R6 release and deployment
verify-release.sh ... --providers
promtool check config
docker compose ... up -d --no-deps ... prometheus
Prometheus query and rules APIs
verify-backup-manifest.sh
external TCP reachability checks against the explicit port list
python -m pytest / ruff / black / mypy
npm lint / type-check / test / Playwright / build
docker compose config --quiet
actionlint
```

## Repository and Host Changes

Repository production changes for Phase 5 include:

- `deploy/production/.env.example`
- `deploy/production/nginx.conf`
- `deployment/nginx.conf`
- `deploy/production/public-nginx-bootstrap.conf`
- `deploy/production/public-nginx.conf`
- `deploy/production/scripts/reload-public-nginx-after-renewal.sh`
- `deploy/production/tests/validate-nginx-configs.sh`
- `deploy/production/monitoring/prometheus.yml`
- `deploy/production/monitoring/rules/public.yml`
- CI/release validation changes for the public Nginx configuration
- `PRODUCTION_PHASE_5_REPORT.md`
- `PRODUCTION_READINESS_REPORT.md`

Host changes include Ubuntu Nginx/Certbot packages, the root-owned public site,
Let's Encrypt material, renewal hook, UFW 80/443 rules, the versioned monitoring
bundle, and the R6 immutable release. Secret-bearing runtime configuration remains
outside Git and was never printed.

## Final Cleanup and Privilege Revocation

The exact Phase 5 remote temporary scripts, archive transfer, ephemeral Runner
work/diagnostic contents, protected pre-Phase-5 environment backup, and temporary
Nginx security-header backup were removed after their rollback windows closed.
Local Phase 5 orchestration scripts, release-transfer copies, Playwright artifacts,
and generated frontend build output were also removed using verified workspace paths.
Release directories, the monitoring TSDB volume, production data volumes, both
Qdrant collections, backup artifacts, certificate material, and SSH authorized keys
were retained.

The final temporary passwordless sudo file was then removed:

```text
/etc/sudoers.d/99-rag-deploy-production -> removed
sudo -n true -> non-zero
SSH public-key login as deploy -> retained
```

After revocation, the three loopback health endpoints remained HTTP 200. The
independent workstation again observed HTTP 308 and trusted HTTPS 200 for the root,
liveness, readiness, and gateway health paths.

## Residual Risks

These are explicit operating risks, not fabricated blockers:

1. The service is single-node. Phase 2 proves recovery, not high availability.
2. No third-party persistent SLA/paging account was available. Continuous
   host-origin public Blackbox and independent workstation verification exist.
3. SSH 22022 is key-only and Fail2ban-protected, but UFW allows it from any source
   because no stable management CIDR was supplied. Restrict it when such a CIDR is
   operationally available.
4. The Python Qdrant client reports a compatibility warning because client 1.19.0
   is newer than server 1.14.1. All accepted operations pass, but the versions
   should be aligned in a controlled future release.
5. HSTS starts conservatively at one day without `includeSubDomains`; increase it
   only after a longer observation window and domain-wide review.
6. The accepted corpus still contains historical unsupported/failed attachment
   outcomes and no production OCR provider. Parsed provenance and the closed
   attachment pipeline remain accepted at the documented 60/69 boundary.
7. The Phase 5 final configuration and reports are committed locally on
   `codex/phase5-final-acceptance`. Both direct `master` push and isolated-branch
   push were rejected by the local approval boundary, so `origin/master` remains
   at the R6 source commit until the user explicitly authorizes remote sync.

No remaining risk above invalidates the live public launch or the frozen production
data invariants.
