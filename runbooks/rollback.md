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

The rollback target is the locked `/opt/odirag/previous` release; arbitrary
release directories are rejected. A broken current release is not required to
pass health or provider checks before rollback. Its manifest and verified local
image IDs are retained only as a best-effort reverse-recovery descriptor. The
tool pulls the previous digest, repeats OCI label and migration compatibility
checks, recreates only application services, waits for 8/8 health, requires
exact HTTP 200 responses, verifies data and real providers, and atomically
swaps current/previous. If activation fails or the process is interrupted, the
transaction journal restores the original local digest with `--pull never`.

After rollback, separately record deployment duration and rollback duration,
then verify the frozen invariants: 182 documents, 821 chunks, 821 active
vectors, 60 parsed attachments, 69 attachment files, no duplicate chunk IDs or
document/chunk-index pairs, active and rollback collections both green with 821
points, 1536 dimensions, and Cosine distance. Retain both releases and both
image digests.
