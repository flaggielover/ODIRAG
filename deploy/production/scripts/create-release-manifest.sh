#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"

die() {
  printf 'create-release-manifest: %s\n' "$*" >&2
  exit 1
}

if [[ "$#" != "5" ]]; then
  die "usage: $0 RELEASE_ID SOURCE_COMMIT BACKEND_DIGEST_REF FRONTEND_DIGEST_REF OUTPUT"
fi

release_id="$1"
source_commit="$2"
backend_ref="$3"
frontend_ref="$4"
output="$5"

[[ "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || die "invalid release id"
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || die "source commit must be a full Git SHA"
[[ "$backend_ref" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] || die "backend ref is not an immutable GHCR digest"
[[ "$frontend_ref" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$ ]] || die "frontend ref is not an immutable GHCR digest"
[[ "$(git -C "$REPOSITORY_ROOT" rev-parse HEAD)" == "$source_commit" ]] || die "source commit is not the checked-out HEAD"
git -C "$REPOSITORY_ROOT" diff --quiet -- . || die "tracked working tree changes must be committed first"
git -C "$REPOSITORY_ROOT" diff --cached --quiet -- . || die "staged changes must be committed first"

compose="$REPOSITORY_ROOT/deploy/production/compose.yml"
compose_sha="$(sha256sum "$compose" | awk '{print $1}')"
build_created="$(git -C "$REPOSITORY_ROOT" show -s --format=%cI "$source_commit")"
alembic_output="$(cd "$REPOSITORY_ROOT/backend" && python -m alembic heads)"
alembic_head="$(grep -Eo '^[0-9a-z_]+' <<<"$alembic_output" | head -n 1)"
[[ -n "$alembic_head" ]] || die "could not resolve Alembic head"

parent="$(dirname -- "$output")"
mkdir -p -- "$parent"
temporary="${output}.tmp.$$"
cat >"$temporary" <<EOF
ODIRAG_RELEASE_ID=$release_id
ODIRAG_SOURCE_COMMIT=$source_commit
ODIRAG_BACKEND_IMAGE_REF=$backend_ref
ODIRAG_FRONTEND_IMAGE_REF=$frontend_ref
ODIRAG_ALEMBIC_HEAD=$alembic_head
ODIRAG_COMPOSE_SHA256=$compose_sha
ODIRAG_BUILD_CREATED=$build_created
EOF
chmod 0644 "$temporary"
mv -f -- "$temporary" "$output"
printf 'release_manifest=PASS-CONFIG release=%s commit=%s alembic_head=%s compose_sha256=%s output=%s\n' \
  "$release_id" "$source_commit" "$alembic_head" "$compose_sha" "$output"
