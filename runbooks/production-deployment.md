# Production bootstrap deployment runbook

This file records the original Phase 1 bootstrap. New production releases must
use `runbooks/release-deployment.md` and `runbooks/rollback.md`; do not repeat
the source-build command below for a Phase 4+ deployment.

## Layout

The server release is placed under `/opt/odirag/releases/<release-id>` and the
`current` symlink points at the active release. Runtime configuration is kept
outside the release at `/etc/odirag/production.env` with mode `0600`.

## Preflight

Run the following from the release directory. The commands do not print the
contents of the runtime environment file.

```sh
sudo -n whoami
docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml config --quiet
docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml ps --all
```

Confirm that only Nginx publishes a host port and that the four named volumes
are the expected `odirag-prod-*` volumes. Do not run `down -v`, prune, or remove
unknown containers/volumes.

## Historical first boot only

```sh
docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml up -d
docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml ps
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/health/live
curl --fail http://127.0.0.1:8080/health/ready
```

Only the backend service runs Alembic migrations. Worker and scheduler use the
same image and data volume but set `ODIRAG_RUN_MIGRATIONS=false`. Do not seed,
crawl, reindex, or delete data during this first boot.

## Integrity checks

Capture container health, volume mappings, image digests, migration head,
PostgreSQL document/chunk counts, attachment counts, and Qdrant collection
status/point count. Compare them with the frozen pre-deployment evidence. Redis
is a cache/queue and is intentionally started empty.

## Smoke tests

Use the existing API contract and a non-secret test account or token. Check a
known approved document search, a grounded RAG query, and refusal behavior for
an out-of-scope question. A provider call is `PASS-LIVE` only when its real
request and response evidence is captured; configuration-only validation is
`PASS-CONFIG`.

## Rollback and closeout

If the fresh SSH connection or an application health check fails, stop the
change and restore the exact SSH backup or previous Compose release. Never
delete unknown volumes. After the final evidence is captured, remove the
temporary sudo drop-in and verify that `sudo -n true` fails on a fresh SSH
connection.
