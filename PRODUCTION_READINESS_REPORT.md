# ODIRAG Production Readiness Report

Authoritative status: 2026-08-17 (Asia/Shanghai)

## Final Verdict

`PHASE_1_OVERALL=PASS-LIVE`

`PHASE_2_OVERALL=PASS-LIVE`

`PHASE_3_OVERALL=PASS-LIVE`

`PHASE_4_OVERALL=PASS-LIVE`

`PHASE_5_OVERALL=PASS-LIVE`

`PRODUCTION_READINESS=PASS-LIVE`

Public production URL: <https://rag.suzheodirag.top/>

This report supersedes the historical readiness checkpoints that previously lived
in this file. Detailed evidence remains in the phase reports and Git history:

- `PRODUCTION_PHASE_1_REPORT.md`
- `PRODUCTION_PHASE_2_REPORT.md`
- `PRODUCTION_PHASE_3_REPORT.md`
- `PRODUCTION_PHASE_4_REPORT.md`
- `PRODUCTION_PHASE_5_REPORT.md`

## Current Production Identity

```text
release=v0.1.0-r6
source_commit=31694f725cbe7f1ee9efcb4291175e734de1d3c9
current=/opt/odirag/releases/v0.1.0-r6
previous=/opt/odirag/releases/v0.1.0-r4
transaction_journal=absent
backend_digest=sha256:144d2107497ed338ca7d18d7cd4354ff79eed7285dd8e870c4b0771431bd5ae8
frontend_digest=sha256:db49c94c0effd455a07a9670c620b312905f561e63370aa3e9e41e524de010a2
application_services=8/8 healthy
```

## Acceptance Summary

| Layer | Status | Accepted evidence |
| --- | --- | --- |
| Runtime and data | PASS-LIVE | 182 documents, 821 chunks, active/rollback Qdrant collections healthy, 60 parsed attachments, 69 attachment files. |
| Provider chain | PASS-LIVE | Bailian 1536-dimensional embedding, BM25/vector fusion, Cohere rerank, DeepSeek grounded answer and fail-closed refusal. |
| Disaster recovery | PASS-LIVE | PostgreSQL logical/physical/PITR, Qdrant, Redis, attachment restores, off-host copy, measured RPO/RTO. |
| Observability | PASS-LIVE | Prometheus/Grafana/Alertmanager, 12/12 targets, public HTTPS Blackbox probes and alert rules. |
| Software supply chain | PASS-LIVE | Private GitHub repository, CI, GHCR immutable digests, SPDX SBOM, BuildKit provenance, deterministic deploy/rollback. |
| Public ingress | PASS-LIVE | DNS, UFW, Nginx, Let's Encrypt, TLS 1.2/1.3, HTTP redirect, security headers. |
| Public application | PASS-LIVE | Real browser frontend/API, Grounded RAG, citation/support validation, out-of-scope refusal. |
| Attack surface | PASS-LIVE | Only 80/443/22022 externally reachable; application internals, state stores, monitoring and exporters remain private. |
| Engineering regression | PASS-LIVE | 531 backend tests, Ruff, Black, mypy, frontend lint/type/unit/E2E/build, Compose/Nginx/workflow validation. |

## Frozen Data Invariants

```text
documents=182
chunks=821
parsed_attachments=60
attachment_files=69
attachment_sha256_matches=69
duplicate_chunk_id=0
duplicate_document_chunk_index=0
active_collection=odirag_chunks_bailian_v4
active_points=821
active_dimensions=1536
active_distance=cosine
active_status=green
rollback_collection=odirag_chunks
rollback_points=821
rollback_dimensions=1536
rollback_distance=cosine
rollback_status=green
duplicate_active_qdrant_payload_chunk_id=0
postgres_qdrant_id_set_equal=true
```

## Public Service Contract

- DNS A record: `rag.suzheodirag.top -> 45.192.110.8`.
- HTTP permanently redirects to the exact trusted HTTPS hostname.
- HTTPS root, liveness, readiness, and gateway health return 200.
- Trusted certificate: Let's Encrypt, SAN `rag.suzheodirag.top`, valid through
  2026-11-14T18:04:45Z.
- TLS 1.0/1.1 rejected; TLS 1.2/1.3 accepted.
- Automatic renewal timer and Nginx reload hook are installed and tested.
- Public ports: 80 and 443. Management: 22022, public-key only.
- Databases, Qdrant, backend, Prometheus, Grafana, Alertmanager, Blackbox, and
  exporters are not publicly reachable.
- Temporary passwordless production sudo has been revoked; `sudo -n true` returns
  non-zero while deploy SSH public-key access remains available.

## Operational Boundaries

Production is accepted with these visible boundaries:

- single-node recovery architecture rather than high availability;
- no third-party paid uptime or paging service, while continuous internal
  Blackbox-through-public-path and independent external verification are active;
- SSH source-CIDR restriction awaits a stable management CIDR;
- Qdrant client/server versions should be aligned in a future controlled release;
- one-day HSTS is intentionally conservative for the initial public observation
  window;
- historical unsupported attachment/OCR cases remain outside the accepted parsed
  60-file set and were not altered during production engineering;
- the Phase 5 final commit is retained locally on `codex/phase5-final-acceptance`;
  remote synchronization requires explicit approval because the local safety
  boundary rejected both default-branch and isolated-branch pushes.

These items are documented operational risks. They do not contradict the real
health, security, recovery, release, public E2E, or data-integrity evidence used for
the final `PRODUCTION_READINESS=PASS-LIVE` decision.
