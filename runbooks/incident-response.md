# Production incident response

This runbook covers the private Phase 3 monitoring stack. Public DNS, TLS,
HTTPS ingress, and public uptime checks remain Phase 5 scope.

## Triage

1. Confirm the alert is firing in Prometheus and present in Alertmanager.
2. Record the alert labels, first observation time, and affected fixed service.
3. Check `docker compose ps`, the relevant container logs, host memory, and
   filesystem headroom without printing environment variables or credentials.
4. Confirm whether the application data invariants remain 182 documents, 821
   chunks, 821 active vectors, 60 parsed attachments, and 69 attachment files.
5. Prefer restoring the affected non-data service. Do not flush Redis, drop
   PostgreSQL objects, recreate chunks, or delete either Qdrant collection.

## Severity

- Critical: backend, PostgreSQL, Redis, Qdrant, host, or filesystem unavailable;
  active Qdrant collection not green; point count differs from 821.
- Warning: sustained latency/error/resource threshold, stale backup or WAL
  archive, provider failures, or repeated container restarts.

## Recovery verification

After remediation, verify the alert moves from firing to resolved, all eight
application services are healthy, `/health/live` and `/health/ready` return
HTTP 200, and the data invariants remain unchanged. Record detection, firing,
receipt, recovery, and resolution timestamps. Do not delete Prometheus,
Grafana, or Alertmanager persistence during incident cleanup.
