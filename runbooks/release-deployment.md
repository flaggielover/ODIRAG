# Release deployment

Production releases use immutable GitHub Container Registry digests and a
separate source directory under `/opt/odirag/releases/<release-id>`. Runtime
secrets remain in `/etc/odirag/production.env`; they are never copied into a
release directory, image, manifest, report, or command log.

## Release identity

Every release must bind these values:

- a full 40-character Git commit SHA;
- a unique release ID;
- backend and frontend `ghcr.io/...@sha256:...` references;
- the Docker platform image IDs resolved after pull;
- the Alembic head;
- the production Compose, Nginx, integrity-check, and provider-check SHA-256 values;
- the deterministic commit timestamp used as the OCI created label.

Generate the non-secret manifest only from a committed tree:

```sh
deploy/production/scripts/create-release-manifest.sh \
  "$RELEASE_ID" "$GIT_COMMIT" "$BACKEND_DIGEST_REF" "$FRONTEND_DIGEST_REF" \
  ".tmp/releases/$RELEASE_ID/manifest.env"
```

Create the source bundle from that exact commit with `git archive`, install it
into a new root-owned directory, then place the generated `manifest.env` at the
release root. Do not copy the developer `.env`, generated evaluation data,
backups, caches, or Git metadata.

## Health-gated activation

On the production host:

```sh
sudo -n deploy/production/scripts/deploy-release.sh \
  "/opt/odirag/releases/$RELEASE_ID"
sudo -n deploy/production/scripts/verify-release.sh \
  "/opt/odirag/releases/$RELEASE_ID"
```

The deployment tool validates every manifest-bound file, verifies the
root-owned runtime file without displaying it, pulls both digest references,
checks OCI revision/version labels, proves migration-head compatibility, and
recreates only backend, worker, scheduler, and frontend. PostgreSQL, Redis,
Qdrant, monitoring, and named volumes are not recreated. `/opt/odirag/current`
is promoted only after all eight application services, three exact HTTP 200
health checks, frozen data invariants, and real provider/RAG checks pass. The
old current release becomes `/opt/odirag/previous`.

Before the first service change, the tool writes a root-only transaction
journal at `/opt/odirag/.release-transaction.env`. EXIT, HUP, INT, and TERM
recover the recorded original digest and pointers. A later release command
also consumes an unfinished journal, covering abrupt process termination or a
host restart. Recovery uses the already verified local image IDs with
`--pull never`; it does not depend on registry availability.

Repeat the real-provider gate when collecting independent post-deploy evidence:

```sh
sudo -n deploy/production/scripts/verify-release.sh --providers
```

The same bounded check is mandatory inside deployment and rollback. It runs
Bailian embedding, vector/BM25 hybrid retrieval,
Cohere rerank, DeepSeek grounded generation, and fail-closed refusal in a
read-only database transaction. It does not write a production query trace.

## Prohibited operations

Do not deploy a tag-only reference, use `docker compose build` on the server,
run `down -v`, prune images needed by current/previous, delete release
directories, or modify a deployed manifest. A schema-changing release requires
a separate compatibility and rollback plan and must not be used for the Phase
4 rollback drill.
