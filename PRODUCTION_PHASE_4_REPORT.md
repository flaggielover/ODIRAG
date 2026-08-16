# ODIRAG Production Phase 4 Report

Evidence window: 2026-08-17 (Asia/Shanghai), with production workflow timestamps recorded in UTC.

## Result

`PHASE_4_OVERALL=PASS-LIVE`

The immutable R4 release was deployed, an immutable R5 release was deployed as the rollback candidate, and an authenticated R5 to R4 rollback was executed through GitHub Actions. The final production state is R4 with R5 retained as the previous release. No data volume, Qdrant collection, document, chunk, or attachment was deleted.

## Gate Matrix

| Gate | Status | Evidence |
| --- | --- | --- |
| REPOSITORY_HYGIENE | PASS-CONFIG | Clean working-tree snapshot before this evidence report; no blind staging, secrets, `.env`, caches, or generated evaluation data were included. |
| GITHUB_REPOSITORY | PASS-LIVE | Authenticated `flaggielover/ODIRAG` workflows completed and GHCR immutable images were pulled by digest. |
| CI | PASS-LIVE | CI runs `31962155080` and `31963622481` completed successfully, including release transaction tests and container checks. |
| IMAGE_BUILD | PASS-LIVE | R4 release run `31962378234` and R5 release run `31963191387` built and pushed backend/frontend images. |
| IMAGE_IDENTITY | PASS-LIVE | Production containers matched the R4 top-level OCI digests after rollback; no tag-only deployment was used. |
| SBOM | PASS-LIVE | R4 and R5 SBOM artifacts were downloaded and verified as valid SPDX documents; backend/frontend artifact checksums matched the release records. |
| PROVENANCE | PASS-LIVE | BuildKit registry provenance was produced by the successful R4/R5 release jobs. Native GitHub attestations were intentionally disabled for the private user-owned repository limitation. |
| GITHUB_ACTIONS | PASS-LIVE | R4 deploy `31962887804`, R5 deploy `31963822514`, and authenticated rollback `31964339095` completed successfully. |
| GHCR | PASS-LIVE | R4/R5 images were available and pulled using immutable manifest digests inside the authenticated deployment window. |
| RELEASE_MODEL | PASS-LIVE | Release directories contain root-owned manifests and deployment state; `current`/`previous` pointers and the transaction journal were verified after rollback. |
| DEPLOYMENT | PASS-LIVE | R4 deployment completed with data and provider gates; R5 deployment completed with the same gates and was retained for rollback. |
| ROLLBACK | PASS-LIVE | R5 to R4 rollback workflow completed in `150.258` seconds; operation, previous release, image identity, health, data, provider, and verification gates all passed. |
| PRODUCTION_REGRESSION | PASS-LIVE | Bailian embedding, vector retrieval, hybrid BM25+vector retrieval, Cohere rerank, DeepSeek grounded RAG, out-of-scope refusal, and read-only write-boundary checks passed after rollback. |
| DATA_INTEGRITY | PASS-LIVE | PostgreSQL/Qdrant exact ID equality and both active/rollback collection checks passed; counts and duplicate checks are recorded below. |
| PHASE_4_OVERALL | PASS-LIVE | All required Phase 4 deployment and rollback gates are live-verified. |

## Release Identity

R4 source commit: `c7a305a71b4a0105f62fc214f2a3238e3172bcaf`.

R4 images:

- Backend: `ghcr.io/flaggielover/odirag-backend@sha256:7aeee4b1774e64f429986d4f7f69ccc6bdec028c366e3618686f336b2c422ce9`
- Frontend: `ghcr.io/flaggielover/odirag-frontend@sha256:4440914b95b157c8fd92df9d394d05b7a7c2b04c44e962ff0ecf3421c1978e4c`

R5 images (retained as rollback target):

- Backend: `ghcr.io/flaggielover/odirag-backend@sha256:bdb0f4145f74614c69a9c9d80986df4586dc216d976d7d8d9c4171758ed2de54`
- Frontend: `ghcr.io/flaggielover/odirag-frontend@sha256:557bd513539e3717ef0cd4cb17fc146576e4041e1a2ac87316b72aa22fcb304f`

The authenticated rollback workflow change is source commit `ddfe77d03d7d46fd3c2a493894034db0deaf77c5`; it adds an explicit `deploy|rollback` operation and keeps GHCR authentication active for the transaction.

## Final Production State

```text
current=/opt/odirag/releases/v0.1.0-r4
previous=/opt/odirag/releases/v0.1.0-r5
journal_present=false
deployment_state.release_id=v0.1.0-r4
deployment_state.operation=rollback
deployment_state.previous_release=/opt/odirag/releases/v0.1.0-r5
deployment_state.duration_seconds=150.258
deployment_state.data_integrity_verified=true
deployment_state.providers_verified=true
```

All eight application/stateful services were healthy after rollback: backend, frontend, nginx, postgres, qdrant, redis, scheduler, and worker. Nginx probes returned `200` for `/health/live`, `/health/ready`, and `/healthz`. PostgreSQL, Redis, and Qdrant were not rebuilt or recreated during the drill.

## Data Integrity

```text
documents=182
chunks=821
parsed_attachments=60
attachment_files=69
duplicate_chunk_id=0
duplicate_document_chunk_index=0
active_collection=odirag_chunks_bailian_v4
active_qdrant_status=green
active_qdrant_points=821
active_qdrant_dimensions=1536
active_qdrant_distance=cosine
rollback_collection=odirag_chunks
rollback_qdrant_status=green
rollback_qdrant_points=821
rollback_qdrant_dimensions=1536
rollback_qdrant_distance=cosine
duplicate_qdrant_payload_chunk_id=0
point_payload_ids_equal=true
postgres_qdrant_id_set_equal=true
```

The original `odirag_chunks` collection remains available as rollback data. It was not overwritten or deleted.

## Provider Regression

The final independent R4 verification reported:

```text
embedding_provider=bailian
embedding_model=text-embedding-v4
vector_length=1536
vector_retrieval=PASS-LIVE
hybrid_bm25_vector=PASS-LIVE
rerank_provider=cohere
rerank_model=rerank-v3.5
direct_llm_provider=deepseek
direct_llm_model=deepseek-v4-flash
grounded_rag=PASS-LIVE
out_of_scope_refusal=PASS-LIVE
direct_llm_called_for_refusal=false
transaction_read_only=true
production_trace_writes=0
in_memory_traces=2
```

The verification output exposed no API keys, tokens, Authorization headers, complete vectors, or provider secret values.

## Historical Failures and Remediation

- R0 (`31942430697`) pushed images but failed the GitHub native attestation step because the repository is private and user-owned. The tag and images were not moved or deleted.
- R2 failed its quality job before production deployment.
- R3 deployment (`31961467438`) reached real provider and data gates but failed its Python 3.10 timestamp import. The fix was committed as `c7a305a...`; R4 was rebuilt from that commit.
- R4/R5 and the authenticated rollback completed without those failures.

## Rollback Procedure

1. Keep both release directories and both Qdrant collections.
2. Restore the previous provider/model/version and `ODIRAG_QDRANT_COLLECTION=odirag_chunks` from the previous immutable manifest.
3. Run the authenticated release transaction with the previous immutable image digests and `--pull never` when the images are already verified locally.
4. Recheck eight-service health, `/health/live`, `/health/ready`, data integrity, provider smoke tests, and `journal_present=false`.
5. Only after all gates pass, update `current`; leave the former candidate in `previous` for audit and recovery.

## Scope Boundary

Phase 4 is complete. Phase 5 has not been started in this report. Production sudo authorization remains intentionally active for the remaining approved engineering phases and must not be revoked here.
