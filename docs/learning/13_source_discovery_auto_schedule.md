# Optional unattended source discovery

The Phase 16 workflow is safe to run manually by an administrator. An unattended variant is also
available, but it is disabled by default and must be explicitly configured.

Set `ODIRAG_SOURCE_DISCOVERY_AUTO_ENABLED=true` and provide
`ODIRAG_SOURCE_DISCOVERY_AUTO_TOPICS` as either a JSON string array or a comma-separated list.
`ODIRAG_SOURCE_DISCOVERY_AUTO_INTERVAL_SECONDS` is bounded to a minimum of five minutes. Optional
region, organization level, and coverage thresholds apply to every configured topic.

Celery Beat invokes `odirag.source_discovery.scan_gaps`. The task checks PostgreSQL first, skips a
topic with a `pending`, `running`, or `awaiting_approval` run (regardless of optional region), and
also waits for the same-topic minimum interval before queuing another run. It queues a bounded
discovery run only when the literal topic still has a content gap. The worker then performs candidate discovery,
HTTPS and official-domain validation, column discovery, trial crawl, and quality scoring.

This scheduler never approves or activates a candidate. Every quality-passing candidate remains
`pending_approval` until an administrator reviews it. With the flag false or no topics configured,
the task returns `disabled` without opening the database or calling an external provider. Monitor
the task result, `source_discovery_events`, and `/api/source-discovery/metrics`; configure a real
Brave credential and alert owner before enabling it in a target environment.

Deploy a single Celery Beat scheduler. The same-topic active/cooldown guard is not an atomic lock
between multiple Beat replicas, so running more than one scheduler can still create a race.
