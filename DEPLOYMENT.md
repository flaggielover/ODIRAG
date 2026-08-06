# Deployment

## Verification Status

Compose, CI, shell/PowerShell startup logic, Alembic upgrade/downgrade, demo API flow, and container
configuration have been statically or locally validated. Docker is installed on the implementation
workstation, and the previous-base-image stack completed a historical local multi-service run. The
current hardened images have not been rebuilt or started because Docker Desktop cannot mount its WSL
data VHD (`WSL_E_USER_VHD_ALREADY_ATTACHED`). Do not reuse the historical result as evidence for the
current images; recover WSL, rebuild serially, and rerun the production acceptance checklist.

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

## Backup Baseline

- Schedule PostgreSQL snapshots/logical backups and perform restore drills.
- Back up accepted raw evidence and attachments according to retention policy.
- Snapshot Qdrant with collection/version metadata when recovery time matters; vectors can also be
  rebuilt from approved chunks if provider versions remain available.
- Preserve selected evaluation/experiment artifacts needed for release evidence.
- Redis persistence supports recovery but does not replace PostgreSQL backups.

No platform-specific backup command is certified by this repository; production operators must
document and test their own recovery objectives.

## Production Configuration

Use `ODIRAG_ENVIRONMENT=production`, JSON logs, an external secret manager, a high-entropy JWT key,
a precomputed admin password hash, exact HTTPS CORS origins, TLS ingress, private service networks,
authenticated Redis/Qdrant where supported, resource limits, and distributed rate limiting.

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
response. Pin and review image tags before release even though the development template exposes
overrides for convenience.

Live source discovery additionally requires:

```text
ODIRAG_SOURCE_DISCOVERY_PROVIDER=brave
ODIRAG_SOURCE_DISCOVERY_SEARCH_URL=https://api.search.brave.com/res/v1/web/search
ODIRAG_SOURCE_DISCOVERY_API_KEY=<secret>
ODIRAG_SOURCE_DISCOVERY_QUALITY_THRESHOLD=0.65
ODIRAG_SOURCE_DISCOVERY_OFFICIAL_SUFFIXES=[".gov.cn", ".gov", ".edu.cn"]
```

The API must return `503 PROVIDER_UNAVAILABLE` when the Brave key/network is absent. Validate a
deployment with a controlled gap run, inspect `/api/source-discovery/runs/{id}/events`, confirm the
candidate remains `pending_approval`, approve it manually, then activate it and verify the created
source/columns. This workstation validated the Brave response contract with an HTTP fixture and the
workflow with SQLite; it did not execute a live Brave search or PostgreSQL/Redis worker delivery.

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

## Production Gate

Before public exposure, require:

- successful full Compose startup and demo smoke on the target platform;
- migrations and restore rehearsal;
- TLS and private dependency networking;
- secret rotation and non-default credentials;
- Redis/Qdrant authentication or equivalent network isolation;
- shared rate limiting and crawler egress controls;
- a reviewed official-domain suffix policy, Brave credential, and manual source-approval owner;
- centralized logs/metrics and alert routing;
- dependency/image scanning and signed/tagged release artifacts;
- representative evaluation and load measurements on production-like data.
