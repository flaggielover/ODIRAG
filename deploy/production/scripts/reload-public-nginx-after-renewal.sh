#!/usr/bin/env bash
set -Eeuo pipefail

/usr/sbin/nginx -t
/bin/systemctl reload nginx
printf '%s\n' 'public_nginx_certificate_reload=PASS-LIVE'
