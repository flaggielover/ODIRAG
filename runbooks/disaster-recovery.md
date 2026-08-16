# ODIRAG Disaster Recovery Runbook

Phase 2 validates recovery without destroying the production stack. Every
restore uses an isolated Docker volume, temporary directory, or temporary
Qdrant collection. Production invariants remain:

```text
documents=182
chunks=821
active Qdrant points=821
parsed attachments=60
attachment byte files=69
```

## Recovery sequence

1. Verify disk capacity and that all eight production services are healthy.
2. Verify the machine-readable manifest and SHA-256 for the selected artifacts.
3. Restore PostgreSQL logical data into `odirag-dr-postgres-*` and validate
   document/chunk counts and Alembic state.
4. Restore the physical base backup plus compressed WAL into an isolated
   PostgreSQL instance. Recover to the named point between canary B and C.
5. Restore the active Qdrant snapshot into a collection named
   `odirag_chunks_bailian_v4_restore_test_<timestamp>`. Compare point count,
   vector configuration, payload uniqueness, and PostgreSQL chunk IDs.
6. Restore the Redis RDB canary into `odirag-dr-redis-*`; production Redis is
   never flushed.
7. Extract attachment bytes into a temporary directory and verify all 69
   checksums. Do not overwrite `/app/data/attachments`.
8. Clean only explicitly named `odirag-dr-*` containers, volumes, temporary
   collections, and restore directories.

## PITR and objectives

The production PostgreSQL command enables `wal_level=replica`,
`archive_mode=on`, compressed WAL archiving, and a 900-second archive timeout.
The target is RPO <= 15 minutes and RTO <= 60 minutes. The PITR drill records
the canary target, measured RPO between the target and C, and measured RTO from
isolated recovery start until A/B are queryable and C is absent.

The accepted live drill recovered to restore point
`odirag_dr_20260815T162516Z_t2`: canary A and B existed, C did not. Measured
RPO was 1 second and measured RTO was 6.804 seconds, both within target. The
production canary schema and isolated container/directory were removed after
evidence capture.

The sequential cross-component drill restored PostgreSQL, Qdrant, Redis, and
attachment bytes in 69.973 seconds. The restored PostgreSQL and Qdrant 821-ID
SHA-256 fingerprints were equal; Redis canary recovery and attachment 69/69
checksums passed. Evidence is retained under `/var/backups/odirag/drills/`,
while `/var/backups/odirag/restore-tests/` is empty after cleanup.

## Stop conditions

Stop immediately if production counts, Qdrant points, attachment checksums,
service health, disk safety, or secret boundaries change unexpectedly. Do not
continue to obtain a green report after a stop condition.
