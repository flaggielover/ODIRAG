#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"
nginx_image="${NGINX_IMAGE:-nginx:1.30.4-alpine-slim}"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

cert_dir="$test_root/letsencrypt/live/rag.suzheodirag.top"
mkdir -p "$cert_dir"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -subj '/CN=rag.suzheodirag.top' \
  -keyout "$cert_dir/privkey.pem" \
  -out "$cert_dir/fullchain.pem" >/dev/null 2>&1

docker run --rm \
  --add-host backend:127.0.0.1 \
  --add-host frontend:127.0.0.1 \
  --volume "$repo_root/deployment/nginx.conf:/etc/nginx/nginx.conf:ro" \
  "$nginx_image" nginx -t

docker run --rm \
  --volume "$repo_root/deployment/frontend.nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  "$nginx_image" nginx -t

docker run --rm \
  --volume "$repo_root/deploy/production/public-nginx-bootstrap.conf:/etc/nginx/conf.d/default.conf:ro" \
  "$nginx_image" nginx -t

docker run --rm \
  --volume "$repo_root/deploy/production/public-nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  --volume "$test_root/letsencrypt:/etc/letsencrypt:ro" \
  "$nginx_image" nginx -t

printf '%s\n' 'nginx_config_validation=PASS-CONFIG configs=4'
