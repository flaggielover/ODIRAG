# Alerting operations

Alert rules live under `deploy/production/monitoring/rules/` and are loaded by
Prometheus. Alertmanager groups by `alertname`, `service`, and `severity` with
bounded intervals to avoid notification storms.

The default `internal-audit` receiver intentionally contains no external
credentials. Prometheus-to-Alertmanager receipt and alert resolution can be
verified internally; external delivery stays `BLOCKED` until an authorized
channel is supplied. Never put API keys, webhook tokens, or Authorization
headers in this repository.

For a reversible test, stop one non-data exporter briefly, record T0 through
T6 (injection, scrape observation, firing, receipt, recovery, resolution),
then restart it and verify all production services are healthy. Never stop
PostgreSQL, Qdrant, or Redis for alert tests.
