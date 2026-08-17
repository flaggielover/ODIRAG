# Roadmap

ODIRAG has completed the accepted Phase 1-5 production-engineering path: public HTTPS,
live providers, observability, disaster recovery, immutable GHCR releases, SBOM/provenance,
transactional deployment, verified rollback, and public end-to-end acceptance are recorded as
`PASS-LIVE`. This roadmap contains only work that remains; completed gates are not future items.

## Answer Quality

- Improve the latest 100-question Gold result without weakening evidence or refusal safety. The
  current status is `GOLD_EVALUATION_QUALITY=PARTIAL` and
  `QUALITY_GUARD=FAIL-LIVE-QUALITY`.
- Reduce 32/90 supported false refusals, especially the 29 unresolved post-answer validation
  cases and the remaining Evidence Gate false negatives.
- Improve exact chunk citation precision/recall (`0.288069 / 0.433333`) and multi-chunk evidence
  completeness while retaining the diagnostic document-level metrics.
- Raise Supported Answer Recall from `0.644444` while preserving 10/10 safe Gold refusals and the
  zero unsupported-answer rate.
- Re-run the full human-verified Gold set after material provider, prompt, chunking, retrieval,
  rerank, grounding, citation, or refusal changes. The existing run 16 predates the Bailian
  embedding migration and must not be presented as a post-migration quality benchmark.
- Address remote rerank capacity/reliability: run 16 applied Cohere reranking to 67/100 traces and
  failed open on 33/100 HTTP 429 responses.

## Availability and Scale

- Design and validate a multi-node/high-availability architecture. The accepted deployment is
  single-node recovery, not HA.
- Revalidate Redis rate-limit capacity, trusted-proxy identity, BM25/cache synchronization,
  Celery scheduling, database pools, and failure recovery before adding API or worker replicas.
- Add capacity and soak evidence for representative concurrent search/chat/crawl workloads; do
  not turn current bounded measurements into an SLA.
- Align the Qdrant Python client and server versions in a controlled release and repeat snapshot,
  restore, retrieval, and rollback checks.

## Operations and Security

- Add an authorized third-party uptime/paging destination when an owner and credentials are
  available. Current Prometheus/Alertmanager and public-path Blackbox monitoring remain internal
  to the single host, with independent external verification but no paid external SLA.
- Restrict SSH to a stable management source CIDR when one is available, preserving the tested
  recovery path.
- Review the initial one-day HSTS policy after the observation window before increasing duration
  or adding `includeSubDomains`.
- Extend network-level egress controls across outbound paths. Source-discovery and attachment
  fetching already support trusted DNS plus pinned transports, but general crawling and other
  integrations should also block private/cloud-metadata ranges and receive path-specific review.
- Move the verified off-host backup copy to an independently protected or object-locked recovery
  sink if the operational threat model requires host-loss and ransomware isolation.

## Content and Governance

- Extend attachment support beyond the accepted 60 parsed files. Unsupported legacy formats,
  unavailable source bytes, and other terminal unsupported cases remain explicit boundaries.
- Integrate and validate a production OCR provider before claiming OCR coverage. The current
  attachment closure records no production OCR attempt or success.
- Keep autonomous source discovery bounded and approval-based. Any new jurisdiction, suffix
  policy, or scheduled topic requires an accountable reviewer, live provider/network evidence,
  and alert ownership.
- Broaden safe SQL templates only for verified analytics use cases; never enable unrestricted
  model-generated SQL.
- Add user and role administration beyond the bootstrap-superuser workflow when the product has a
  defined multi-user authorization model.

## Evidence Rule

Future work is complete only when its declared environment was exercised and its evidence is
retained. Local, CI, live, historical, partial, blocked, and unverified results must remain
separate. Current accepted production evidence is in
[`PRODUCTION_READINESS_REPORT.md`](PRODUCTION_READINESS_REPORT.md); current quality evidence is in
[`EVALUATION.md`](EVALUATION.md).
