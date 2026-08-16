# ODIRAG production monitoring

This directory contains non-secret, reproducible observability configuration
for Phase 3. Monitoring is private to the Docker networks and is not a public
ingress path. Phase 5 owns public HTTPS uptime checks.

## Components and budget

The production host has approximately 7.6 GiB RAM and 39 GiB system disk.
The monitoring profile reserves bounded resources so application services keep
priority:

| Component | CPU limit | Memory limit | Disk policy |
| --- | ---: | ---: | --- |
| Prometheus | 0.20 | 256 MiB | 15 day retention, 2 GiB size cap |
| Grafana | 0.15 | 256 MiB | persistent SQLite only |
| Alertmanager | 0.04 | 32 MiB | 120 hour persistent state |
| node-exporter | 0.03 | 32 MiB | none |
| cAdvisor | 0.10 | 96 MiB | none |
| postgres-exporter | 0.03 | 32 MiB | none |
| redis-exporter | 0.03 | 32 MiB | none |
| blackbox-exporter | 0.04 | 32 MiB | none |

The combined limit is 768 MiB and 0.62 CPU. Require at least 2 GiB available
before startup so the host and
the existing PostgreSQL, Qdrant, Redis, backend, worker, scheduler, frontend,
and Nginx services. Prometheus data must be reviewed after deployment with
`docker system df` and `df -h`.

## Wiring

The dedicated monitoring network is internal. Prometheus also joins
`odirag-prod-private`; Blackbox joins the existing private and edge networks.
Exporter ports are never published. Prometheus, Grafana, and Alertmanager bind
only to host loopback for local administration and SSH tunnels; Nginx does not
proxy any of them.

The backend target expects an internal `/metrics` endpoint. Metric names in
the rules are intentionally bounded by stable labels (`job`, `provider`,
`operation`, `status`, `error_category`). Never add query text, document IDs,
request IDs, URLs, API keys, or exception strings as labels.

## Validation

Before reload, validate the YAML and rule files with the versions of
`promtool`, `amtool`, and `blackbox_exporter` deployed in the production image.
After startup verify every expected Prometheus target is `up`, query the
metrics endpoint, and restart Grafana once to verify provisioning is
reproducible. Alertmanager has an internal receiver with no external
credentials; report external notification delivery as blocked until an
authorized channel exists.
