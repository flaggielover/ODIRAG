# Production release descriptors

Each production release is installed as a separate directory under
`/opt/odirag/releases/<release-id>`. The directory contains the source bundle
for that Git commit plus a non-secret `manifest.env` with exactly these keys:

```text
ODIRAG_RELEASE_ID=v0.1.0
ODIRAG_SOURCE_COMMIT=<40 lowercase hexadecimal characters>
ODIRAG_BACKEND_IMAGE_REF=ghcr.io/owner/image@sha256:<64 lowercase hexadecimal characters>
ODIRAG_FRONTEND_IMAGE_REF=ghcr.io/owner/image@sha256:<64 lowercase hexadecimal characters>
ODIRAG_ALEMBIC_HEAD=0012_attachment_processing_audit
ODIRAG_COMPOSE_SHA256=<sha256 of deploy/production/compose.yml>
ODIRAG_BUILD_CREATED=<UTC RFC3339 timestamp>
```

The manifest never contains passwords, provider keys, registry credentials, or
the runtime environment. Runtime secrets remain in
`/etc/odirag/production.env`. A deployment only promotes `/opt/odirag/current`
after image-label, migration, container-health, HTTP-health, and image-ID gates
pass. The prior current directory becomes `/opt/odirag/previous` and is not
deleted.

Run release operations as root:

```sh
deploy/production/scripts/deploy-release.sh /opt/odirag/releases/<release-id>
deploy/production/scripts/verify-release.sh --providers
deploy/production/scripts/rollback-release.sh
```

Never use `down -v`, prune release images, edit a deployed manifest, or replace
a digest reference with a tag.
