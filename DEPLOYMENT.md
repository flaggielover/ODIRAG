# Deployment

## Verification Status

The root Compose stack remains the development/demo topology. The production topology in
`deploy/production/compose.yml` is live and accepted at release `v0.1.0-r6`, with 8/8 application
services healthy and public HTTPS, provider, monitoring, recovery, and release gates passing live
verification. See [`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md) for current
evidence. The historical workstation WSL failure remains in implementation history and is not the
current production status.

## One-Command Development Demo

```powershell
.\scripts\start_demo.ps1
```

```bash
sh scripts/start_demo.sh
```

Both commands start the `ui` and `async` profiles, wait for the backend health check, seed the demo
database, authenticate through the live API, and reindex only approved `demo-*` documents. This
refreshes Qdrant and the running API process's BM25 index. Use `-SkipSeed` in PowerShell or
`--skip-seed` in the shell script to start without demo initialization.

The scripts force the reproducible demo provider set:

- deterministic 64-dimensional embeddings;
- Redis embedding cache;
- Qdrant collection `odirag_demo_chunks_v1`;
- deterministic token-overlap reranking;
- extractive grounded answers unless overridden.

Set `ODIRAG_ADMIN_PASSWORD` before startup to replace the development default.

## Manual Compose Workflow

```bash
cp .env.example .env
# Review every development credential and provider setting.
docker compose build backend
docker compose build frontend
docker compose --profile ui --profile async up -d --no-build
docker compose ps
```

The backend entrypoint creates writable data directories and retries `alembic upgrade head` before
starting Uvicorn. Worker and scheduler set `ODIRAG_RUN_MIGRATIONS=false` and wait for the healthy
backend, avoiding concurrent migration races.

Useful commands:

```bash
docker compose logs -f backend worker scheduler
docker compose exec backend python -m alembic current
docker compose exec -T backend /app/deployment/initialize-demo.sh
docker compose --profile ui --profile async down
```

`down` preserves named volumes. Do not add `--volumes` unless deletion is intentional and a
recoverable backup exists.

## Services and Data

| Service | Responsibility | Persistent volume |
| --- | --- | --- |
| PostgreSQL | business records and lineage | `postgres-data` |
| Redis | cache, broker, task result state | `redis-data` |
| Qdrant | rebuildable vector points | `qdrant-data` |
| Backend | API, migrations, BM25/artifacts/files | `app-data` |
| Worker | crawl and source-discovery task execution | shared `app-data` |
| Scheduler | stale-task recovery and alert refresh | shared `app-data` |
| Frontend | static Vue bundle | image filesystem |
| Nginx | `/api` proxy and frontend ingress | configuration bind mount |

The backend image runs as UID/GID 10001. `/app/data` contains attachments, raw/parsed files, BM25,
evaluation/experiment reports, and scheduler state and is created with non-root write permission.

## Migrations and Rollback

For controlled deployments, run migrations as a separate release step or allow exactly one API
container to run the entrypoint migration:

```bash
docker compose run --rm -e ODIRAG_RUN_MIGRATIONS=true backend \
  python -m alembic upgrade head
docker compose run --rm -e ODIRAG_RUN_MIGRATIONS=false backend \
  python -m alembic current
```

Review every revision and take a PostgreSQL backup before schema changes. Downgrade is a migration
smoke tool, not a universal production rollback. Restore the previous application image and a
tested database backup when a migration is not safely reversible.

The accepted production release path uses immutable GHCR digests, versioned release directories,
transaction journals, provider/data verification, and authenticated deploy/rollback workflows.
Use [`runbooks/release-deployment.md`](runbooks/release-deployment.md) and
[`runbooks/rollback.md`](runbooks/rollback.md); do not replace that transaction with an ad hoc tag
switch or `docker compose down`.

## Production Backup and Recovery

Production backup and isolated recovery validation are `PASS-LIVE` for PostgreSQL
logical/physical/PITR recovery, Qdrant, Redis, attachments, manifest verification, an off-host copy,
and measured RPO/RTO. Use [`runbooks/backup-and-restore.md`](runbooks/backup-and-restore.md),
[`runbooks/disaster-recovery.md`](runbooks/disaster-recovery.md), and the scripts under
`deploy/production/scripts/`; [`PRODUCTION_PHASE_2_REPORT.md`](PRODUCTION_PHASE_2_REPORT.md) is the
authoritative execution record.

Redis remains runtime state rather than the source of truth. The first verified off-host copy is a
recovery sink, not immutable/object-locked storage. No restore procedure may overwrite production
data without a separately approved recovery operation; accepted drills restore into isolated
PostgreSQL volumes, temporary Qdrant collections, temporary Redis resources, and temporary
attachment directories.

## Production Configuration

Use `ODIRAG_ENVIRONMENT=production`, JSON logs, protected external runtime secret files, a
high-entropy JWT key, a precomputed admin password hash, exact HTTPS CORS origins, TLS ingress,
private service networks, Redis authentication, Qdrant network isolation/authentication where
supported, resource limits, and shared Redis rate limiting.

The rate limiter always uses an IP bucket at middleware time; it deliberately does not derive a
bucket from an unverified Bearer token before FastAPI authentication runs. For the supplied Compose
topology, Nginx has the fixed `ODIRAG_NGINX_PROXY_IP` (`172.30.0.10` by default) and backend trusts
only that value through `ODIRAG_TRUSTED_PROXY_IPS`. Nginx replaces `X-Forwarded-For` with its direct
peer address, so client-supplied forwarding chains cannot select another bucket. When changing the
Compose subnet/IP, update both settings together. A directly exposed backend must leave
`ODIRAG_TRUSTED_PROXY_IPS` empty.

`ODIRAG_TRUSTED_PROXY_IPS` accepts either a JSON string array such as
`["172.30.0.10", "10.0.0.0/8"]` or the historical comma-separated form
`172.30.0.10,10.0.0.0/8`. Surrounding whitespace is removed, and an empty value disables
forwarded-address trust. Every non-empty item must be an IP address or CIDR; malformed JSON,
non-string JSON entries, and invalid network values stop backend startup with a redacted
configuration error.

Remote embedding/LLM/rerank keys must be backend secrets. If a provider is intentionally absent,
leave its feature unavailable and rely on health/error reporting; never insert a fake production
response. Production releases use immutable image digests; tag overrides remain development
conveniences and are not release identity.

Live source discovery additionally requires:

```text
ODIRAG_SOURCE_DISCOVERY_PROVIDER=brave
ODIRAG_SOURCE_DISCOVERY_SEARCH_URL=https://api.search.brave.com/res/v1/web/search
ODIRAG_SOURCE_DISCOVERY_API_KEY=<secret>
ODIRAG_SOURCE_DISCOVERY_QUALITY_THRESHOLD=0.65
ODIRAG_SOURCE_DISCOVERY_OFFICIAL_SUFFIXES=[".gov.cn", ".gov", ".edu.cn"]
```

The API must return `503 PROVIDER_UNAVAILABLE` when the Brave key/network is absent. A bounded live
Phase Z campaign verified Brave search, official-domain validation, trial crawling, manual approval,
and explicit activation. That evidence does not mean autonomous discovery is enabled in the current
production release: every deployment still needs its own credential, network approval, suffix
policy, review owner, and event review. Historical and current evidence is recorded in
`IMPLEMENTATION_STATUS.md`.

Unattended gap scanning is opt-in and remains a bounded proposal workflow. Set
`ODIRAG_SOURCE_DISCOVERY_AUTO_ENABLED=true` together with a JSON array (or comma-separated list) in
`ODIRAG_SOURCE_DISCOVERY_AUTO_TOPICS`. Celery Beat then runs
`odirag.source_discovery.scan_gaps` at `ODIRAG_SOURCE_DISCOVERY_AUTO_INTERVAL_SECONDS` (minimum
five minutes; the compatibility alias `ODIRAG_SOURCE_DISCOVERY_AUTO_MIN_INTERVAL_SECONDS` is also
accepted). Existing `pending`, `running`, or `awaiting_approval` runs for the same topic are
skipped, and any recent run for that topic is held until the interval expires; a new run is queued
only when the database still reports a gap. Candidates never activate automatically. Leave the flag false or the topic list empty until the Brave credential,
official suffix policy, review owner, and alert routing are ready.
Run exactly one Celery Beat scheduler for this task. The active/cooldown check limits duplicate
work but is not an atomic distributed lock across multiple Beat replicas.

## Production Acceptance and Regression Gate

The current public `v0.1.0-r6` release is `PASS-LIVE`; authoritative gate evidence is recorded in
[`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md). Future releases must preserve
the accepted HTTPS/private-network boundary, secret handling, resource limits, shared rate limiting,
backup/restore and rollback evidence, monitoring, immutable image identity, SBOM/provenance,
provider smoke tests, frozen data invariants, and engineering regression checks.

The current 100-question Gold quality result is still `PARTIAL / FAIL-LIVE-QUALITY`. Single-node
architecture, external paging, Qdrant version alignment, SSH CIDR, attachment/OCR, and outbound-path
egress defense remain limitations. Source-discovery and attachment pin validated connections when
trusted DNS is configured; other outbound paths still require review and network-layer controls.
