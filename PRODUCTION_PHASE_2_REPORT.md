# ODIRAG Production Phase 2 Report

Date: 2026-08-16 (Asia/Shanghai)
Production artifact timestamps: 2026-08-15 UTC
Host: `rag-prod` / Ubuntu 22.04 / Docker 29.7.2 / Compose v5.4.0
Scope: disaster recovery and recovery validation only

## Executive Result

Production Phase 2 implemented and live-verified a single-node recovery layer
for PostgreSQL, Qdrant, Redis, and attachment bytes. Every restore targeted an
isolated container, volume, temporary collection, or temporary directory. No
production data volume, active collection, rollback collection, Redis dataset,
or attachment file was used as a restore target.

`PHASE_2_OVERALL=PASS-LIVE`

No provider key, password, SSH private key, Authorization header, production
environment file, embedding vector, answer body, or provider response body is
included in this report or any normal data backup.

## 1. Phase 1 Baseline

The accepted Phase 1 baseline was preserved: 8/8 services healthy,
`documents=182`, PostgreSQL `chunks=821`, active Qdrant collection
`odirag_chunks_bailian_v4` with 821 points at 1536/Cosine, rollback collection
`odirag_chunks`, parsed attachments 60, and attachment byte files 69. Active
providers remained Bailian `text-embedding-v4`, Cohere `rerank-v3.5`, and
DeepSeek `deepseek-v4-flash`.

## 2. Phase 2 Scope

The work covered logical and physical PostgreSQL backup, continuous compressed
WAL archiving, PITR, measured RPO/RTO, Qdrant snapshot/restore, Redis
persistence/recovery, attachment backup/restore, manifests, a workstation
off-host copy, a cross-component drill, final provider regression, and cleanup.
No Phase 3 monitoring, CI/registry, public ingress, DNS, or TLS work started.

## 3. Server Storage and Capacity

Preflight found 8 vCPU, 7.6 GiB RAM, no swap, and a 39 GiB root filesystem with
about 33 GiB available. After all backups, `/var/backups/odirag` used 121 MiB
and the root filesystem was 16% used with 33 GiB available. Sequential restore
was used to avoid memory pressure.

## 4. Persistent Asset Inventory

| Asset | Source | Approximate size | Backup / recovery | Secret | Priority |
|---|---|---:|---|---|---|
| PostgreSQL | `odirag-prod-postgres` -> `/var/lib/postgresql/data` | 147 MiB preflight | custom dump plus base backup/WAL; isolated PostgreSQL 16 | data may be sensitive | critical |
| Qdrant | `odirag-prod-qdrant` -> `/qdrant/storage` | 27 MiB preflight | active-collection snapshot; temporary collection | payload data | critical |
| Redis | `odirag-prod-redis` -> `/data` | 1.6 MiB preflight | RDB plus `/data` archive; isolated Redis | runtime state | important |
| Attachment bytes | `odirag-prod-app` -> `/app/data/attachments` | 51.6 MiB / 69 files | tar plus per-file SHA-256; temporary directory | source bytes | critical |
| Application uploads/data | `odirag-prod-app` -> `/app/data` | 53.1 MiB preflight | attachment-specific backup; other paths classified | mixed | mixed |
| Configuration | `/opt/odirag/current`, `/etc/odirag/production.env` | small | source/runbooks; protected config procedure | env is secret-bearing | critical |
| Provider secrets | external secret paths and runtime env | small | excluded from normal data backup | yes | critical |
| BM25/evaluation/cache | app-data/Redis derived data | regenerable | rebuild or selective restore | no/mixed | lower |

## 5. PostgreSQL Logical Backup Evidence

PostgreSQL 16 native `pg_dump` produced a versioned custom-format artifact.
Structural validation used a separate `postgres:16-alpine` container and
`pg_restore --list` against the artifact file.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `postgres-logical-20260815T154304Z.dump` | 18,851,681 | `f83140e87de9b160ad7a91f27cc3c28c6d09b1b3f88803c0fc5ce9e5a9a16356` |

## 6. PostgreSQL Restore Evidence

The real logical artifact was copied into an isolated PostgreSQL 16 container
and restored with `--no-owner --no-privileges --exit-on-error`. Verification:

- documents 182; chunks 821;
- orphan chunks 0;
- duplicate `(document_id, chunk_index)` groups 0;
- one Alembic version row;
- restore/integrity time 12.641 seconds in the accepted standalone drill;
- temporary container and named volume removed.

## 7. WAL Archive Configuration

The production PostgreSQL Compose service now reproducibly sets
`wal_level=replica`, `archive_mode=on`, `archive_timeout=15min`, and
`archive_command=/usr/local/bin/odirag-archive-wal %p %f`. WAL segments and
PostgreSQL base-backup history files are gzip-compressed atomically under
`/var/backups/odirag/postgres/wal`.

The official image runs PostgreSQL as UID/GID 70. Backup-root parents are
traverse-only mode `2711`; the WAL directory is `70:70`, mode `2770`. Real WAL
activity produced compressed segments. A later bundle captured 21 archived
files; historical `pg_stat_archiver.failed_count` includes pre-fix validation
attempts and was not reset.

## 8. Physical Base Backup Evidence

`pg_basebackup` produced a real physical backup and `pg_verifybackup` returned
success.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `postgres-base-20260815T155051Z.tar.gz` | 33,718,113 | `fc95a0cb37cf08c11a5d3f97fd49b469fe33cafd9e8eb3b53560516e90af9ccc` |
| `wal-archive-20260815T165146Z.tar.gz` | 6,285,332 | `3e70f223e5d3d9f7f1b04f7858cf85adabe8c39eb0700c66f6f6d0c44b685063` |

## 9. PITR Drill

The drill created only `dr_canary`, committed A, committed B, created named
restore point `odirag_dr_20260815T162516Z_t2`, then committed C. The physical
base plus archived WAL was restored to an isolated PostgreSQL instance. At the
target, A=1, B=1, C=0. The restored server was required to leave recovery mode
before validation. The canary schema, isolated container, and restore directory
were removed.

## 10. RPO Target and Measurement

- Target RPO: <= 15 minutes.
- Measured RPO: 1 second between the accepted restore point and C.
- Result: PASS-LIVE.

## 11. RTO Target and Measurement

- Target RTO: <= 60 minutes.
- Measured PITR RTO: 6.804 seconds from isolated recovery start through
  promotion and A/B/C integrity validation.
- Result: PASS-LIVE.

## 12. Qdrant Snapshot Evidence

Only active collection `odirag_chunks_bailian_v4` was snapshotted. The rollback
collection was not passed to a write or delete operation.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `qdrant-odirag_chunks_bailian_v4-20260815T162918Z.snapshot` | 14,663,168 | `e041f3c915ff521dac624b7c1eaa06e53f42dcc97b98a368460be83dbdadb62d` |

Source status was green, points 821, dimension 1536, distance Cosine, Qdrant
image `qdrant/qdrant:v1.14.1`.

## 13. Qdrant Restore Evidence

The snapshot was uploaded with Qdrant's v1.14 `POST .../snapshots/upload`
endpoint into a collision-checked temporary collection. Verification returned:

- green, 821 points, 1536/Cosine;
- missing payload `chunk_id` 0; duplicate payload `chunk_id` 0;
- PostgreSQL and restored-Qdrant 821-ID sets equal;
- real Bailian query embedding, model `text-embedding-v4`, vector length 1536,
  accepted latency 548.699 ms;
- active/restored vector top-10 exact rank match and max score delta 0;
- BM25 20, vector 20, real Cohere rerank applied, final hits 5;
- temporary collection explicitly deleted and confirmed absent;
- active and rollback collections confirmed present after cleanup.

## 14. Redis Persistence Design

Redis 7.4 uses AOF with `appendonly=yes`, `appendfsync=everysec`, and a periodic
RDB save policy on named volume `odirag-prod-redis`. Redis supports cache,
rate-limiting, Celery broker/result state, and scheduler/runtime state, so it is
not treated as entirely disposable.

## 15. Redis Recovery Evidence

| Artifact | Size | SHA-256 |
|---|---:|---|
| `redis-20260815T164505Z.rdb` | 202,565 | `f89b132d51c8771842811819f2e92123a42951363cbc7740e8644b71085a9989` |
| `redis-20260815T164505Z-data.tar.gz` | 335,465 | `418a10e4c9929f996c7941e798880b8fe3e08ac919b886fce881c10135141f81` |

The RDB was restored into an isolated Redis container/volume by stopping the
empty instance, copying `dump.rdb`, then starting it. The canary matched and the
restored database contained 6 keys. Production Redis was never flushed and
remained available. Temporary Redis resources and the production canary were
removed.

## 16. Attachment Backup Evidence

The actual `/app/data/attachments` path was archived without modifying the
closed parsing pipeline. Artifact `attachments-20260815T164813Z.tar.gz` is
45,857,242 bytes with SHA-256
`b719ff01d371c48970712b6e69576e48c4d9ef65c3adb37fba4bb032fbbaca6c`.
The separate checksum list contains 69 relative file paths.

## 17. Attachment Restore and Checksum Evidence

The archive was extracted only under the recovery-test hierarchy. Source files
69, restored files 69, SHA-256 equality 69/69. Production database state after
the drill remained parsed attachments 60; all 60 had non-null parser,
`processed_at`, and parsed text provenance fields.

## 18. Backup Manifest

`/var/backups/odirag/manifest.tsv` contains backup ID, timestamp, component,
source, artifact, size, SHA-256, software version, restore procedure, and
retention class. `verify-backup-manifest.sh` independently verified 7/7
artifact rows. No secret field is present.

## 19. Off-host Backup Evidence

The workstation sink is `D:\TEMP\ODIRAG_BACKUPS\phase2-20260815T`, outside
Git. It contains the seven manifest artifacts, `manifest.tsv`, and the
attachment checksum list: 9 files, 119,923,885 bytes. Workstation size and
SHA-256 matched the server manifest 7/7; the checksum-list file also matched
the server independently. No env file, provider secret, API key, password, SSH
key, or unrelated system file was copied.

## 20. Cross-component DR Drill

PostgreSQL, Qdrant, Redis, and attachment restores were run sequentially from
the created artifacts. Total recovery duration was 69.973 seconds. The sorted
821-ID SHA-256 fingerprints from restored PostgreSQL and restored Qdrant were
identical. Redis canary and attachment 69/69 checks passed. Evidence is retained
under `/var/backups/odirag/drills/`; recovery-test directories are empty.

## 21. Backup Retention Policy

- PostgreSQL logical: daily, 7 validated copies.
- Physical base: weekly, 4 validated copies.
- WAL: retain from newest validated base through 15 days; bundle hourly, retain
  2 after a newer verified bundle exists.
- Qdrant: daily, 7 validated snapshots.
- Redis: daily, 3 validated RDB/AOF sets.
- Attachments: weekly, 4 validated archives.

Cleanup is intentionally operator-gated. Before deletion, validate the
manifest, prove a newer same-component artifact with a real restore, confirm
its off-host copy, and exclude the newest known-good artifact. Never recursively
delete the backup root.

## 22. Production Regression

Final production state: 8 running and 8 healthy services. Nginx
`/health/live` and `/health/ready` returned success. The no-write production
`ChatService` probe exercised Bailian, BM25, active Qdrant, hybrid fusion,
Cohere, DeepSeek, citation/support validation, and out-of-scope refusal:

- grounded RAG: BM25 20, vector 20, fusion 8, rerank 8, final 5, citations 1,
  Direct LLM 3,160.527 ms, positive token usage, support validated;
- out of scope: BM25 20, vector 20, rerank 8, reason
  `insufficient_evidence_relevance`, no Direct LLM call;
- transaction read-only, production trace writes 0, in-memory traces 2.

## 23. Tests and Static Checks

- Pytest: 524 collected, 524 passed, 0 failed, 0 skipped, 26.31 seconds.
- Ruff: all backend and Phase 2 Python verifier checks passed.
- mypy: no issues in 170 source files.
- `git diff --check`: exit 0; only existing LF/CRLF normalization warnings.
- Production Compose `config --quiet`: exit 0 on the target.
- All Phase 2 shell scripts passed remote `bash -n`.

Black check was attempted on Windows but did not return output and was stopped;
no Black process remains. It is not a Phase 2 acceptance Gate; Ruff, mypy,
pytest, shell syntax, live restore evidence, and whitespace checks all passed.

## 24. Final Data Integrity Evidence

| Invariant | Result |
|---|---:|
| documents | 182 |
| PostgreSQL chunks | 821 |
| parsed attachments | 60 |
| parsed attachment provenance fields complete | 60/60 |
| attachment byte files | 69 |
| duplicate PostgreSQL `chunk_id` groups | 0 |
| duplicate `(document_id, chunk_index)` groups | 0 |
| active Qdrant points | 821 |
| active Qdrant dimensions/distance | 1536 / Cosine |
| duplicate/missing active payload `chunk_id` | 0 / 0 |
| active and rollback Qdrant collections present | true |
| temporary Qdrant collections | 0 |

## 25. Commands Actually Executed

Representative exact command families executed on the live host:

```text
sudo -n true
docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml config --quiet
docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml up -d --no-deps --force-recreate postgres
psql: SHOW wal_level/archive_mode/archive_command/archive_timeout; SELECT pg_switch_wal()
backup-postgres.sh
pitr-postgres.sh
pitr-drill.sh <physical-base>
restore-postgres.sh <logical-dump>
backup-wal-archive.sh
backup-qdrant.sh
restore-qdrant.sh <snapshot>
backup-redis.sh
restore-redis.sh <rdb> <canary-key> <canary-value>
backup-attachments.sh
restore-attachments.sh <archive> <checksums>
verify-backup-manifest.sh
cross-component-drill.sh <seven explicit recovery arguments>
docker exec -i odirag-prod-backend-1 python -   # no-write provider regression
python -m pytest
python -m ruff check .
python -m mypy app
scp explicit artifact paths to the workstation sink
sudo rm -f /etc/sudoers.d/99-rag-deploy-temp
sudo -n true   # expected exit 1 after closeout
```

## 26. Files Created

Phase 2 created 17 recovery/verification scripts under
`deploy/production/scripts/`, including backup/restore scripts for all four
components, WAL/PITR helpers, manifest verification, cross-component drill,
and safe Python verifiers. It also created:

- `runbooks/backup-and-restore.md`
- `runbooks/disaster-recovery.md`
- `PRODUCTION_PHASE_2_REPORT.md`

## 27. Files Modified

- `deploy/production/compose.yml`: reproducible WAL/PITR settings and mounts.
- `deploy/production/.env.example`: `POSTGRES_ARCHIVE_TIMEOUT` example.

No attachment pipeline or backend application behavior was modified for Phase
2. No file was staged or committed.

## 28. Git Diff Summary

The repository was already materially dirty at Phase 2 start (166 enumerated
paths: 57 modified, 109 untracked). Phase 2 preserved unrelated work and used
no `git add -A`. Whole-worktree diff statistics therefore include Phase 1 and
earlier work and are not attributed to Phase 2. Phase 2 changes are scoped to
the production Compose/env example, 17 scripts, two runbooks, and this report.

## 29. Temporary Resources Created and Removed

Removed after evidence: isolated PostgreSQL containers/volumes, PITR data
directories and canary schema, temporary Qdrant restore collections, isolated
Redis containers/volumes and canary key, attachment restore directories, and
all `.partial` backup files. Final counts: temporary DR containers 0, temporary
DR volumes 0, temporary Qdrant collections 0, restore-test entries 0, partial
files 0.

The task-specific sudoers file was removed. A fresh SSH connection then ran
`sudo -n true` and received exit code 1 with `sudo: a password is required`.
No legitimate permanent admin configuration was removed.

## 30. Remaining Risks

1. `qdrant-client` 1.19.0 warns that server 1.14.1 is outside its recommended
   minor-version range. Snapshot, restore, scroll, vector search, and cleanup
   all passed; align versions in a separately reviewed maintenance change.
2. Backup scheduling and retention deletion remain operator-driven. Continuous
   WAL archiving is live, but periodic logical/base/Qdrant/Redis/attachment jobs
   should be scheduled with alerting in a later authorized phase.
3. The workstation off-host copy is a first host-loss sink, not immutable or
   object-locked storage. No project policy requiring application-layer backup
   encryption was found; storage protection should be reviewed before adding a
   second remote destination.
4. Runtime configuration and provider secrets are deliberately excluded from
   normal data backups and need a separate protected recovery procedure.
5. The PostgreSQL archive failure counter retains failures from implementation
   retries. Monitor new failures and last successful WAL rather than resetting
   historical evidence.

## 31. Remaining Blockers

None for the approved Phase 2 scope. No critical Gate is PARTIAL, FAIL, BLOCKED,
or based on configuration-only evidence.

## 32. Recommended Phase 3 Actions

When separately authorized, add metrics and alerts for backup age, manifest
verification, WAL archive freshness/failures, disk growth, and scheduled drill
results. Do not start Prometheus, Grafana, Alertmanager, external monitoring,
CI/registry, DNS, or TLS work from this report.

## Final Gate Table

| Gate | Status | Live evidence |
|---|---|---|
| POSTGRES_LOGICAL_BACKUP | PASS-LIVE | Real custom dump, independent structure check, manifest hash. |
| POSTGRES_RESTORE | PASS-LIVE | Isolated restore: 182 documents, 821 chunks, relational/Alembic checks. |
| POSTGRES_WAL_ARCHIVE | PASS-LIVE | Effective config and real compressed WAL/history files. |
| POSTGRES_BASE_BACKUP | PASS-LIVE | Real `pg_basebackup`; `pg_verifybackup` passed. |
| POSTGRES_PITR | PASS-LIVE | A/B present, C absent at named restore point. |
| POSTGRES_RPO_RTO | PASS-LIVE | RPO 1 second; RTO 6.804 seconds, both within target. |
| QDRANT_SNAPSHOT | PASS-LIVE | Active collection snapshot artifact and hash. |
| QDRANT_RESTORE | PASS-LIVE | Temporary restore, full ID/invariant/retrieval checks, explicit cleanup. |
| REDIS_PERSISTENCE | PASS-LIVE | Live AOF/everysec/RDB settings and real RDB/AOF artifacts. |
| REDIS_RECOVERY | PASS-LIVE | Isolated RDB restore, canary and non-empty state verified. |
| ATTACHMENT_BACKUP | PASS-LIVE | Real 69-file archive and SHA-256 list. |
| ATTACHMENT_RESTORE | PASS-LIVE | Temporary extraction; SHA-256 69/69. |
| BACKUP_MANIFEST | PASS-LIVE | Seven artifact rows independently verified. |
| OFF_HOST_BACKUP | PASS-LIVE | Workstation copy, size/SHA-256 7/7 plus checksum-list match. |
| DISASTER_RECOVERY_DRILL | PASS-LIVE | Four components restored; ID digest equal; 69.973 seconds. |
| PRODUCTION_REGRESSION | PASS-LIVE | 8/8, live/ready, real provider/RAG/refusal path. |
| DATA_INTEGRITY | PASS-LIVE | Frozen counts, duplicate checks, both Qdrant collections, no temps. |
| PHASE_2_OVERALL | PASS-LIVE | All critical Gates have genuine live execution evidence. |

Phase 2 stops here. Phase 3 has not started.
