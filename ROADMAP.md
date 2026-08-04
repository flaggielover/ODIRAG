# Roadmap

The phase implementation is complete at the code and deterministic-test level. The remaining work
is production validation and scale hardening, not placeholder feature scaffolding.

## Near Term

- Run the complete Compose stack on a Docker-capable host and record image, migration, Qdrant,
  Redis, worker, scheduler, Nginx, seed, login, reindex, search, chat, feedback, and evaluation
  evidence.
- Execute the reachable real-site crawl with an approved network path and preserve a redacted
  trace; keep fixture coverage as the offline regression baseline.
- Run a credentialed Brave source-discovery campaign against an approved jurisdiction, preserve
  candidate/event evidence, manually verify official status, and confirm activation through a
  real Redis worker and PostgreSQL transaction. Current coverage is provider-contract and SQLite
  workflow evidence only.
- Replace the process-local rate limiter with Redis or ingress enforcement before horizontal API
  scaling.
- Add network-layer egress controls that pin validated crawler destinations and block private/cloud
  metadata ranges, closing the residual DNS rebinding window.
- Run larger representative evaluation and load datasets on production-like PostgreSQL, Redis,
  Qdrant, worker counts, and provider models.

## Product Extensions

- Add OCR execution behind the existing OCR-needed flag and isolated parser boundary.
- Broaden safe SQL templates only for verified analytics use cases; never enable unrestricted
  generated SQL.
- Add user/role management beyond the current bootstrap administrator workflow.
- Add managed object storage, retention policy, backup automation, and restore drills.
- Add Prometheus/Grafana export when an operational environment and alert routing owner exist.
- Add global alert rules for repeated source-discovery provider failures, approval backlog, and
  low trial-crawl quality; the current discovery metrics API is pull-based and events are durable.
- Add dependency/image scanning, signed release artifacts, and a documented vulnerability contact.

## Release Gate

A production release requires real Docker stack evidence, external secret injection, TLS, private
service networking, authenticated Redis/Qdrant where supported, backups and restore rehearsal,
distributed rate limiting, security review, production-like load measurements, and a tagged Git
history. Current local deterministic numbers are engineering evidence, not an SLA.
