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
[[ -z "$(git -C "$REPOSITORY_ROOT" status --porcelain --untracked-files=all)" ]] \
  || die "working tree contains untracked release inputs"

compose="$REPOSITORY_ROOT/deploy/production/compose.yml"
nginx="$REPOSITORY_ROOT/deploy/production/nginx.conf"
integrity_check="$REPOSITORY_ROOT/deploy/production/scripts/verify-production-integrity.py"
provider_check="$REPOSITORY_ROOT/deploy/production/scripts/verify-production-rag.py"
for release_input in \
  deploy/production/compose.yml \
  deploy/production/nginx.conf \
  deploy/production/scripts/verify-production-integrity.py \
  deploy/production/scripts/verify-production-rag.py; do
  git -C "$REPOSITORY_ROOT" ls-files --error-unmatch "$release_input" >/dev/null \
    || die "release input is not tracked: $release_input"
  [[ "$(git -C "$REPOSITORY_ROOT" hash-object "$release_input")" \
      == "$(git -C "$REPOSITORY_ROOT" rev-parse "$source_commit:$release_input")" ]] \
    || die "release input does not match source commit: $release_input"
done
compose_sha="$(sha256sum "$compose" | awk '{print $1}')"
nginx_sha="$(sha256sum "$nginx" | awk '{print $1}')"
integrity_check_sha="$(sha256sum "$integrity_check" | awk '{print $1}')"
provider_check_sha="$(sha256sum "$provider_check" | awk '{print $1}')"
build_created="$(git -C "$REPOSITORY_ROOT" show -s --format=%cI "$source_commit")"
alembic_output="$(cd "$REPOSITORY_ROOT/backend" && python -m alembic heads)"
mapfile -t alembic_heads < <(grep -Eo '^[0-9a-z_]+' <<<"$alembic_output")
[[ "${#alembic_heads[@]}" == "1" ]] || die "exactly one Alembic head is required"
alembic_head="${alembic_heads[0]}"

parent="$(dirname -- "$output")"
mkdir -p -- "$parent"
[[ ! -e "$output" && ! -L "$output" ]] || die "refusing to overwrite an existing release manifest"
temporary="${output}.tmp.$$"
cat >"$temporary" <<EOF
ODIRAG_RELEASE_ID=$release_id
ODIRAG_SOURCE_COMMIT=$source_commit
ODIRAG_BACKEND_IMAGE_REF=$backend_ref
ODIRAG_FRONTEND_IMAGE_REF=$frontend_ref
ODIRAG_ALEMBIC_HEAD=$alembic_head
ODIRAG_COMPOSE_SHA256=$compose_sha
ODIRAG_NGINX_SHA256=$nginx_sha
ODIRAG_INTEGRITY_CHECK_SHA256=$integrity_check_sha
ODIRAG_PROVIDER_CHECK_SHA256=$provider_check_sha
ODIRAG_BUILD_CREATED=$build_created
EOF
chmod 0644 "$temporary"
mv -f -- "$temporary" "$output"
printf 'release_manifest=PASS-CONFIG release=%s commit=%s alembic_head=%s compose_sha256=%s nginx_sha256=%s output=%s\n' \
  "$release_id" "$source_commit" "$alembic_head" "$compose_sha" "$nginx_sha" "$output"
