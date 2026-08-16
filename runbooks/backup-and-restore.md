# ODIRAG Backup and Restore Runbook

This runbook covers the single-node Phase 2 recovery layer. It assumes the
production Compose project is `/opt/odirag/current/deploy/production` and the
runtime environment file is `/etc/odirag/production.env`. Real provider
credentials remain outside the backup hierarchy and are never copied into an
artifact.

## Backup root

The server-side hierarchy is `/var/backups/odirag`:

| Asset | Source | Artifact | Restore target | Priority |
|---|---|---|---|---|
| PostgreSQL logical data | `odirag-prod-postgres-1` | `postgres/logical/*.dump` | isolated PostgreSQL 16 container | critical |
| PostgreSQL PITR base/WAL | PostgreSQL volume and archive command | `postgres/base/*.tar.gz`, `postgres/wal/*.gz` | isolated PostgreSQL recovery instance | critical |
| Qdrant active collection | `odirag_chunks_bailian_v4` | `qdrant/*.snapshot` | temporary Qdrant collection | critical |
| Redis state | Redis `/data` and RDB export | `redis/*.rdb`, `redis/*-data.tar.gz` | isolated Redis container | important/cache-backed |
| Attachment bytes | `/app/data/attachments` | `attachments/*.tar.gz` plus SHA-256 list | temporary recovery directory | critical |
| BM25 snapshot | `/app/data/indexes/bm25.json` | included in app-data archive when needed | regenerate from PostgreSQL | regenerable |
| Evaluation/experiment outputs | `/app/data/evaluation`, `/app/data/experiments` | optional, separate retention | regenerate or restore selectively | noncritical |
| Runtime configuration | `/etc/odirag/production.env` | never in normal data backup | restore from protected secret/config procedure | secret-bearing |

The backup root and `postgres/` parent are mode `2711`, owned by
`root:deploy`, so the PostgreSQL container can traverse only the known WAL
path. The WAL directory is mode `2770`, owned by numeric UID/GID `70:70` for
the official PostgreSQL image. Other component directories are mode `2770`,
owned by `root:deploy`; artifacts are mode `0640`. The WAL directory is
mounted into PostgreSQL only for archive output. It is not the PostgreSQL data
volume.

## Commands

Run from the release directory with the actual host backup root:

```bash
sudo ./deploy/production/scripts/backup-postgres.sh
sudo ./deploy/production/scripts/pitr-postgres.sh
sudo ./deploy/production/scripts/backup-wal-archive.sh
sudo ./deploy/production/scripts/backup-qdrant.sh
sudo ./deploy/production/scripts/backup-redis.sh
sudo ./deploy/production/scripts/backup-attachments.sh
sudo ./deploy/production/scripts/verify-backup-manifest.sh
```

The cross-component drill invokes the isolated restore scripts sequentially,
compares SHA-256 fingerprints of the restored PostgreSQL and Qdrant chunk ID
sets, records total recovery time, and removes temporary recovery resources:

```bash
sudo ./deploy/production/scripts/cross-component-drill.sh \
  POSTGRES_DUMP QDRANT_SNAPSHOT REDIS_RDB \
  REDIS_CANARY_KEY REDIS_CANARY_VALUE \
  ATTACHMENT_ARCHIVE ATTACHMENT_CHECKSUMS
```

Logical restore always uses an isolated volume and container:

```bash
sudo ./deploy/production/scripts/restore-postgres.sh \
  /var/backups/odirag/postgres/logical/postgres-logical-<id>.dump
```

Attachment and Redis restores also target temporary resources only:

```bash
sudo ./deploy/production/scripts/restore-attachments.sh \
  /var/backups/odirag/attachments/attachments-<id>.tar.gz \
  /var/backups/odirag/attachments/attachments-<id>.sha256
sudo ./deploy/production/scripts/restore-redis.sh \
  /var/backups/odirag/redis/redis-<id>.rdb \
  odirag:dr:canary:<id> phase2-<id>
```

Never pass `/var/lib/postgresql/data`, a production named volume, the active
Qdrant collection, or `/app/data/attachments` as a restore destination.

The first verified off-host sink is the workstation directory
`D:\TEMP\ODIRAG_BACKUPS\phase2-20260815T`, outside the Git repository.
Only the seven manifest artifacts, `manifest.tsv`, and the attachment checksum
list were copied. Server and workstation size/SHA-256 checks passed 7/7. No
runtime env file, secret, API credential, or SSH key is part of that copy.

## Retention

- PostgreSQL logical dumps: daily, retain 7 validated copies.
- PostgreSQL physical base backups: weekly, retain 4 validated copies.
- WAL archives: retain from the newest validated base backup through 15 days;
  prune only after a newer base backup and manifest verification succeed.
- Qdrant snapshots: daily, retain 7 validated copies.
- Redis RDB/AOF exports: daily, retain 3 validated copies.
- Attachment archives: weekly, retain 4 validated copies.

Retention cleanup is intentionally not automatic until an operator verifies a
newer known-good manifest. Before any deletion, run
`verify-backup-manifest.sh`, confirm at least one newer artifact for that
component has passed a real restore drill, copy its manifest set off-host, and
exclude the newest validated artifact from the deletion list. Delete only
explicit paths from the selected component directory; never use a recursive
cleanup against `/var/backups/odirag`. Never remove the newest validated
artifact.
