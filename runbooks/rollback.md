# Deterministic release rollback

Rollback uses `/opt/odirag/previous`, whose manifest records the exact source
commit and GHCR image digests. It never rebuilds old source and never changes
PostgreSQL, Redis, Qdrant, attachment, or monitoring volumes.

## Preflight

Confirm `current` and `previous` resolve to different directories inside
`/opt/odirag/releases`, and that both contain a read-only `manifest.env` and
`deployment-state.json`. Do not print `/etc/odirag/production.env` or registry
credentials.

## Roll back

```sh
sudo -n deploy/production/scripts/rollback-release.sh
sudo -n deploy/production/scripts/verify-release.sh --providers
```

The rollback tool pulls the previous digest if necessary, repeats OCI label and
migration compatibility checks, recreates only application services, waits for
8/8 health, verifies live/ready/healthz, and atomically swaps current/previous.
If activation fails, the current symlink is not promoted.

After rollback, separately record deployment duration and rollback duration,
then verify the frozen invariants: 182 documents, 821 chunks, 821 active
vectors, 60 parsed attachments, 69 attachment files, no duplicate chunk IDs or
document/chunk-index pairs, active collection healthy, and rollback collection
present. Retain both releases and both image digests.
