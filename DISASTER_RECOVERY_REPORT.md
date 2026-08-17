# Disaster Recovery Report

> Historical checkpoint: this 2026-08-13 read-only audit records the state before Production
> Phase 2. Its `PRODUCTION-DR-NOT-ACCEPTED` verdict and missing-restore statements are superseded by
> `PRODUCTION_PHASE_2_REPORT.md`, which live-verified PostgreSQL logical/physical/PITR, Qdrant,
> Redis, attachment, manifest, off-host-copy, and cross-component recovery. The body below is
> preserved as before-state evidence.

Date: 2026-08-13
Status: **LOCAL-RUNTIME-VERIFIED / PRODUCTION-DR-NOT-ACCEPTED**

## Current persistence state

| Component | Persistence | Live evidence | Recovery status |
|---|---|---|---|
| PostgreSQL | `odirag_postgres-data` | accepting connections; 182 documents and 821 chunks | Isolated small-data `pg_dump`/`pg_restore` procedure documented and previously PASS-LOCAL; no scheduled backup/PITR |
| Qdrant | `odirag_qdrant-data` | `odirag_chunks` green, 821 points | snapshot list empty; no isolated restore drill |
| Redis | `odirag_redis-data`, AOF enabled | PONG; AOF last write/rewrite status OK | no isolated AOF restore, replication or failover drill |
| Application artifacts | `odirag_app-data` | shared by backend/worker/scheduler | no retention, archive or restore automation |

All eight Compose services were healthy, the 8080 root returned HTTP 200, and `/api/system/health` reported PostgreSQL, Redis and Qdrant healthy at the read-only audit checkpoint. D: had approximately 106.7 GiB free, above the 50 GiB stop threshold.

## PostgreSQL

- `fsync=on` and `synchronous_commit=on`.
- `wal_level=replica`, but `archive_mode=off` and `archive_command` is disabled.
- No repository-managed scheduled backup, encryption, off-host copy, retention job, backup failure alert, or Point-in-Time Recovery evidence exists.
- The acceptance checklist contains a safe isolated custom-format dump/restore and table-count comparison. Its historical result is local development evidence, not production-scale RPO/RTO acceptance.

## Qdrant

- The live collection is green and PostgreSQL chunk count equals Qdrant point count (`821`).
- The live snapshot list is empty.
- Vectors can be rebuilt from approved chunks only when the exact embedding provider/model/version and credentials remain available; this is not equivalent to a tested restore.
- Snapshot creation/restore was not run against the active 5/5 stack because it is a state-changing operation and requires an isolated recovery environment.

## Redis

- AOF persistence is enabled and current persistence status is healthy.
- Redis is not the relational source of truth, but it carries cache, broker and task result state.
- Sentinel/managed Redis, ACL, replication, failover, queue replay and isolated AOF recovery are unverified.

## Recovery objectives and blockers

Production RPO and RTO are **UNDEFINED / BLOCKED-PRODUCTION**. They cannot be inferred from local dataset size or container restart health.

Minimum production acceptance work:

1. Define RPO/RTO per PostgreSQL, Qdrant, Redis and application artifacts.
2. Schedule encrypted, checksummed PostgreSQL backups with off-host retention and failure alerts; add WAL archiving if the selected RPO requires PITR.
3. Schedule Qdrant snapshots and prove isolated restore of collection configuration, vector size, point IDs and payload linkage.
4. Prove isolated Redis recovery or adopt a managed HA topology; document which queued/result state may be lost.
5. Run restore drills in disposable infrastructure and record timestamps, hashes, row/point counts and measured recovery duration.

The active named volumes were not stopped, deleted, overwritten or downgraded during this audit. The existing 5/5 PASS-LIVE evidence remains intact.
