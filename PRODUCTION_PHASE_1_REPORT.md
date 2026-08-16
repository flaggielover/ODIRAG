# Production Phase 1 Report

Date: 2026-08-15
Release: `phase1-20260815T185904`
Host: `rag-prod` / Ubuntu 22.04.5 LTS / x86_64
Repository: `D:\RAG`
Remote release: `/opt/odirag/releases/phase1-20260815T185904` (`/opt/odirag/current`)

## Executive Result

Phase 1 infrastructure deployment completed on the real target. The host was
updated without a release upgrade, SSH was hardened with an independently
validated second connection, Docker was installed from the official Docker apt
repository, the eight-service production Compose stack was built and started,
and the frozen PostgreSQL/Qdrant/application-data invariants were verified.

The original OpenAI-compatible embedding blocker was resolved through a
versioned Alibaba Cloud Model Studio / Bailian migration. The production
runtime now uses `text-embedding-v4` against the Bailian OpenAI-compatible
endpoint and the versioned Qdrant collection; real vector, hybrid, and Cohere
rerank smoke tests are PASS-LIVE.

The final provider closure is also complete. Production Direct LLM now uses
DeepSeek's OpenAI-compatible endpoint with the current `deepseek-v4-flash`
model. Real host and backend-container requests returned HTTP 200, and the
actual `ChatService` path completed Bailian query embedding, BM25 and vector
retrieval, hybrid fusion, Cohere rerank, context packing, DeepSeek generation,
citation validation, answer-support validation, and fail-closed out-of-scope
refusal. No deterministic, extractive, or other fake fallback was enabled.

`PHASE_1_OVERALL=PASS-LIVE`

No real secret values, access tokens, passwords, private keys, or provider
response bodies are included in this report.

## Scope and Constraints

- Ubuntu remained on 22.04; no `do-release-upgrade` or 24.04 release upgrade
  was run.
- No unknown files, containers, volumes, LXD instances, or database rows were
  deleted. Only explicitly named `odirag-prod-*` resources were created.
- The closed attachment pipeline was not changed for this deployment. Existing
  attachment code and migrations through `0012_attachment_processing_audit`
  were included in the reviewed bundle.
- No crawl, batch ingest, vector reindex, or destructive cleanup was run during
  first boot. The BM25 snapshot was rebuilt read-only from the restored
  PostgreSQL chunks because the local Docker API was unavailable; Qdrant points
  were restored from an exact snapshot.
- No files were staged and no `git add -A` was used.

## Preflight Evidence

| Check | Live evidence |
|---|---|
| Temporary sudo | Initial `ssh rag-prod "sudo -n whoami"` returned `root`. |
| Working tree | Read-only classification: 57 modified + 109 untracked = 166 paths. Reports, evaluation data, caches, `.env`, virtual environments, tests, and temporary directories were excluded from the production bundle. |
| SSH before change | Effective configuration and listeners were recorded; the host initially exposed password/root-login SSH on 22 and 22022. |
| UFW before change | Inactive; this was treated as a blocker and corrected before daemon hardening. |
| Fail2ban before change | `sshd` jail active. |
| LXD before change | No instances/workloads (`sudo -n lxc list` empty). |
| Reboot marker before change | Present; a controlled reboot was required after Jammy package updates. |
| Capacity | 8 vCPU, 7.6 GiB RAM, no swap, 39 GiB root filesystem. |

The preflight and execution plan are recorded in
[`PHASE_1_EXECUTION_PLAN.md`](PHASE_1_EXECUTION_PLAN.md).

## Host Changes

### SSH and firewall

- SSH configuration was backed up under
  `/root/odirag-ssh-backups/phase1-20260815/` with root-only access.
- `/etc/ssh/sshd_config.d/00-rag-production-hardening.conf` is mode `0600` and
  effective `sshd -T` values are: `port 22022`, public-key authentication on,
  password authentication off, keyboard-interactive authentication off, and
  root login off.
- `sshd -t` and reload succeeded while the original session remained alive.
- A second independent connection on 22022 returned `FRESH_SSH_OK`; an explicit
  connection attempt to port 22 timed out (`exit 255`).
- UFW is active with default deny incoming / allow outgoing and only TCP 22022
  allowed (IPv4 and IPv6). Fail2ban `sshd` remains active.

### Ubuntu and Docker

- Normal Ubuntu 22.04 package update/upgrade completed; no release upgrade was
  attempted.
- The host returned from the controlled reboot on kernel
  `5.15.0-187-generic`; SSH, UFW, and Fail2ban recovery were verified and the
  reboot-required marker is absent.
- Docker Engine, CLI, containerd, Buildx, and Compose plugin were installed
  from Docker's official apt repository. Live versions: Docker `29.7.2`,
  Compose `v5.4.0`.
- The official `hello-world` container completed successfully.

## Production Implementation

The reviewed production surface is under `deploy/production/`:

- `compose.yml`: PostgreSQL, Redis, Qdrant, backend, worker, scheduler,
  frontend, and Nginx; no development profile or demo provider defaults.
- `.env.example` and `secrets/README.md` document the external secret layout;
  real runtime values are outside Git at `/etc/odirag/production.env`.
- `nginx.conf`: only Nginx publishes a host port, bound to
  `127.0.0.1:8080`; `/health/live` and `/health/ready` are proxied explicitly,
  while `/healthz` remains Nginx liveness.
- `backend/app/api/routes/health.py`: dependency-free liveness and strict
  PostgreSQL/Redis/Qdrant readiness. Readiness returns HTTP 503 when any
  required dependency is unavailable or disabled.
- `backend/app/rate_limit.py`: both root probes bypass Redis rate limiting so a
  Redis failure cannot hide liveness/readiness evidence.
- `Dockerfile.backend`: image healthcheck uses `/health/live`, preserving
  single-container CI compatibility.
- `.dockerignore`: excludes secrets, tests, reports, evaluation/performance
  data, caches, and local environments from the runtime build context.

The production settings loaded in the backend were checked without printing
secret values: `environment=production`, `debug=false`, HTTPS-only CORS JSON,
Redis-backed rate limiting, Bailian `text-embedding-v4` at dimension 1536,
Qdrant collection `odirag_chunks_bailian_v4`, Cohere `rerank-v3.5`, DeepSeek
`deepseek-v4-flash`, database pool `5/5`, empty plaintext admin password, and
no admin bootstrap. The target runtime file is outside the release at
`/etc/odirag/production.env`, owner `root:deploy`, mode `0640`, with its parent
directory mode `0750`; no secret values were displayed.

### Resource and persistence controls

The Compose hard limit budget is 6144 MiB, leaving host reserve. Effective
limits were confirmed with `docker inspect`:

| Service | Memory | CPU | PIDs |
|---|---:|---:|---:|
| postgres | 1024 MiB | 1.25 | 200 |
| redis | 512 MiB | 0.50 | 100 |
| qdrant | 1536 MiB | 1.50 | 200 |
| backend | 1024 MiB | 1.25 | 256 |
| worker | 1536 MiB | 1.75 | 256 |
| scheduler | 256 MiB | 0.25 | 64 |
| frontend | 128 MiB | 0.25 | 64 |
| nginx | 128 MiB | 0.25 | 128 |

All services use `init: true`, `restart: unless-stopped`,
`no-new-privileges:true`, and explicit Docker `json-file` rotation. Backend,
worker, and scheduler run as non-root `odirag:odirag`; stateful image users are
left to their official images. Nginx access/error logs resolve to stdout/stderr
and are therefore covered by Docker rotation.

Named persistent volumes verified on the target:

- `odirag-prod-app` -> `/app/data`
- `odirag-prod-postgres` -> `/var/lib/postgresql/data`
- `odirag-prod-redis` -> `/data` (AOF enabled)
- `odirag-prod-qdrant` -> `/qdrant/storage`

The edge network is `172.30.0.0/24`; the private internal network is
`172.31.0.0/24`. No database, Redis, Qdrant, backend, or worker port is host
published. Host listeners after boot were SSH 22022 and loopback
127.0.0.1:8080 only.

## Transfer and Integrity Evidence

The target started empty for the named production resources. The following
artifacts were transferred over SSH and verified by SHA-256 on both sides:

| Artifact | Size | SHA-256 |
|---|---:|---|
| reviewed source bundle | 427,328 bytes | `86c1d96665591fd714d398b57dc9a70fee0b6661662ac49b23ebb60ce2c17054` |
| PostgreSQL dump | 18,852,998 bytes | `c5b522da8104bbdbb6f7a8c84bbde6af29866abf7b19a4ca0f348125ea535521` |
| Qdrant snapshot | 13,902,336 bytes | `e83352a06bd32ff456284ba1fdedf283e232a701e54fcdeb7a46e85bddb34efa` |
| application-data archive | 46,155,171 bytes | `d7375b09bf693cb58f521a6e52b9fc05006f9d501020405e78646ec3f2ef776c` |

Post-boot PostgreSQL evidence:

| Invariant | Result |
|---|---:|
| documents | 182 |
| approved / rejected / pending_manual_review | 101 / 35 / 46 |
| chunks | 821 |
| indexed chunks | 821 |
| identity-level duplicate chunk IDs | 0 |
| attachments | 123 |
| attachments with local bytes | 69 |
| local attachment bytes | 53,783,559 |
| Alembic head | `0012_attachment_processing_audit` |

The 70-file application-data manifest (69 attachment files plus
`indexes/bm25.json`) matched 70/70 after boot. The scheduler legitimately
created one additional runtime file, `celerybeat-schedule`; it is not part of
the immutable data manifest.

Qdrant target evidence: collection `odirag_chunks`, status `green`, 821 points,
1536-dimensional vectors, Cosine distance. The collection and point count
match the frozen source evidence.

## First Boot and Smoke Evidence

All eight services were `running (healthy)` in `docker compose ps`. Backend,
worker, and scheduler used image
`odirag/backend:phase1-20260815T185904`; frontend used the matching tagged
image. Recorded image IDs were:

- backend: `sha256:fdf626992eb06f16ac2b4b043b82dada69e3f14c27adb8e8c19e6e57767ef54e`
- frontend: `sha256:cc22970d4e7216225ba9d85741cde8113798d0a71d4505db19503f8b423f008f`

Via a temporary localhost-only SSH tunnel, Nginx returned HTTP 200 for
`/healthz`, `/health/live`, `/health/ready`, `/`, and the compatibility
`/api/system/health`. The tunnel was closed after smoke testing; no public
application URL was opened in this no-TLS phase.

Authenticated API evidence before the Bailian migration (credentials and tokens
were kept in-process only):

- Admin login: HTTP 200.
- BM25 search (`mode=bm25`): HTTP 200 with 5 hits for a corpus character probe.
- Structured chat count (`how many documents?`): HTTP 200, `query_type=sql`,
  `structured_count=101`.
- Hybrid search and grounded chat: HTTP 503 with the safe structured error
  code `PROVIDER_UNAVAILABLE`, provider `remote_embedding`.
- Out-of-scope refusal request reached the same embedding prerequisite and
  returned HTTP 503; refusal behavior could not be accepted independently.

Independent provider probes from the production backend network:

| Provider | Endpoint host | Result |
|---|---|---|
| remote embedding | `api.openai.com` | HTTP 403, no valid response shape |
| direct LLM | `api.openai.com` | HTTP 403, no valid response shape |
| remote rerank | `api.cohere.com` | HTTP 200, valid results shape |

The application did not switch to deterministic vectors, memory cache, or an
extractive answer merely to make the hybrid smoke appear healthy.

## Provider Closure Gate

The initial provider closure gate recorded the OpenAI region/policy blocker.
The embedding side was remediated by the Bailian migration below, and the
Direct LLM side was subsequently remediated through DeepSeek. All scoped
provider gates now have genuine production execution evidence.

| Field | Final state | Evidence |
|---|---|---|
| `EMBEDDING_PROVIDER` | `PASS-LIVE` | Bailian `remote`, model `text-embedding-v4`, dimensions `1536`; one minimal request and the post-switch production runtime both returned a 1536-dimensional vector successfully. |
| `VECTOR_RETRIEVAL` | `PASS-LIVE` | The production runtime embedded the query with Bailian and retrieved `20` candidates from `odirag_chunks_bailian_v4`; the independent vector branch returned real corpus hits. |
| `HYBRID_RETRIEVAL` | `PASS-LIVE` | Production runtime used Bailian query vectors with `odirag_chunks_bailian_v4`; BM25 and vector branches both returned hits. |
| `RERANK` | `PASS-LIVE` | Cohere `/v2/rerank` returned HTTP 200 with a valid result shape. |
| `DIRECT_LLM` | `PASS-LIVE` | DeepSeek OpenAI-compatible host `api.deepseek.com`, current model `deepseek-v4-flash`; final host and backend-container requests returned HTTP 200, and the active application adapter returned a schema-valid grounded answer. |
| `GROUNDED_RAG` | `PASS-LIVE` | The real production `ChatService` returned a non-refusal answer after Bailian vector retrieval, BM25 fusion, Cohere rerank, context packing, DeepSeek generation, valid context citations, and deterministic answer-support validation. |
| `OUT_OF_SCOPE_REFUSAL` | `PASS-LIVE` | A semantically complete, deliberately unsupported RAG query traversed Bailian vector retrieval, BM25, hybrid fusion, and Cohere rerank, then was refused by the actual application evidence gate as `insufficient_evidence_relevance`, with no citations and no Direct LLM invocation. |
| `DATA_INTEGRITY` | `PASS-LIVE` | Documents `182`, chunks `821`, Qdrant points `821`, parsed attachments `60`; duplicate PostgreSQL `chunk_id` values `0`, duplicate `(document_id, chunk_index)` groups `0`, duplicate Qdrant payload `chunk_id` values `0`, and missing Qdrant payload `chunk_id` values `0`. |

### Initial provider request evidence (before Bailian migration)

Exactly one minimal embedding request and one minimal direct-LLM request were
made from each execution context. Request bodies and authorization values were
not recorded. All four requests used Bearer authentication with configured
credentials and returned the same classification:

| Context | Operation | HTTP | Host/path/model | Provider code/type | Classification | Request ID | Latency |
|---|---|---:|---|---|---|---|---:|
| production host | embedding | 403 | `api.openai.com` `/v1/embeddings` `text-embedding-3-small` | `unsupported_country_region_territory` / `request_forbidden` | `REGION_OR_POLICY_RESTRICTION` | none | 71.8 ms |
| production host | direct LLM | 403 | `api.openai.com` `/v1/chat/completions` `gpt-4.1-mini` | `unsupported_country_region_territory` / `request_forbidden` | `REGION_OR_POLICY_RESTRICTION` | none | 72.5 ms |
| backend container | embedding | 403 | `api.openai.com` `/v1/embeddings` `text-embedding-3-small` | `unsupported_country_region_territory` / `request_forbidden` | `REGION_OR_POLICY_RESTRICTION` | none | 154.8 ms |
| backend container | direct LLM | 403 | `api.openai.com` `/v1/chat/completions` `gpt-4.1-mini` | `unsupported_country_region_territory` / `request_forbidden` | `REGION_OR_POLICY_RESTRICTION` | none | 59.1 ms |

The six required provider variables were `SET` in the runtime file and in the
backend container, with matching names, lengths, and values across the
host-to-container comparison: `ODIRAG_EMBEDDING_API_KEY`,
`ODIRAG_EMBEDDING_BASE_URL`, `ODIRAG_EMBEDDING_MODEL`,
`ODIRAG_DIRECT_LLM_API_KEY`, `ODIRAG_DIRECT_LLM_BASE_URL`, and
`ODIRAG_DIRECT_LLM_MODEL`. No alternate `OPENAI_API_KEY` or development alias
was present. The host process environment being unset is expected because
Compose loads `/etc/odirag/production.env`.

### DeepSeek Direct LLM closure evidence

The existing `DirectLLMAdapter` was reused without a new SDK. It posts the
application's strict JSON contract to `{base_url}/chat/completions`; production
now sets base URL `https://api.deepseek.com`, provider `direct`, answer provider
`llm`, and model `deepseek-v4-flash`. A live `/models` request returned HTTP 200
and listed `deepseek-v4-flash` and `deepseek-v4-pro`, so no retired alias was
used. The credential was loaded from
`/home/deploy/.config/odirag/secrets/deepseek_api_key` (mode `0600`,
`deploy:deploy`) and its contents were never printed, logged, or committed.

| Check | Result | Live evidence |
|---|---|---|
| Host minimal generation | `PASS-LIVE` | Provider DeepSeek, host `api.deepseek.com`, model `deepseek-v4-flash`, HTTP 200, latency `866 ms`, request ID unavailable. No response body was recorded. |
| Backend-container minimal generation | `PASS-LIVE` | The production backend image loaded the credential through a read-only bind of the approved secret path; model `deepseek-v4-flash`, HTTP 200, latency `1398 ms`, request ID unavailable. |
| Application Direct LLM path | `PASS-LIVE` | Active `ApplicationRuntime` constructed `DirectLLMAdapter`; the final `ChatService` request used `deepseek-v4-flash`, returned a non-empty schema-valid answer, and completed Direct LLM generation in `4509 ms`. |
| Grounded RAG | `PASS-LIVE` | BM25 `20`, vector `20`, fusion `8`, Cohere rerank `8`, final context `5`; selected context refs `5`, generated refs `4`, returned citations `4`. All references were subsets of the selected context and `answer_supported_by_citations` passed. |
| Out-of-scope refusal | `PASS-LIVE` | A 15-character semantically complete unsupported query (SHA-256 `13f9b63c09acbd8a1d8f968332e79f457e43bc78b82b178afda26ddf477cc4b8`) ran as RAG in `hybrid_rerank`: BM25 `20`, vector `20`, fusion `8`, Cohere rerank `8`, final `5`. The evidence decision was `insufficient_evidence_relevance`; refusal was true, citations/context were empty, Direct LLM was skipped, and production trace writes were `0`. |
| Persistence boundary | `PASS-LIVE` | RAG/refusal acceptance ran in a PostgreSQL read-only transaction with an in-memory trace repository; production trace writes were `0`. |
| Required service restart | `PASS-LIVE` | Only backend, worker, and scheduler were recreated; PostgreSQL, Redis, Qdrant, frontend, and Nginx were not restarted. All eight services returned healthy. |

The original 3-second shared dependency timeout produced a genuine
`direct_llm` timeout with full context. The supported `deepseek-v4-flash`
model reduced latency, and the bounded production timeout was set to 15
seconds (the application-enforced maximum is 30 seconds). No retrieval or
provider fallback was enabled. A pre-timeout DeepSeek checkpoint remains at
`/etc/odirag/production.env.deepseek-flash-pre-timeout-20260815`; the complete
pre-DeepSeek rollback file remains at
`/etc/odirag/production.env.pre-deepseek-20260815`. Both are mode `0640` and
owned by `root:deploy`.

### Exact Direct LLM rollback

To roll back only the DeepSeek change, restore
`/etc/odirag/production.env.pre-deepseek-20260815` over
`/etc/odirag/production.env` using the same controlled atomic write mechanism.
That retained file preserves the accepted Bailian embedding and
`odirag_chunks_bailian_v4` settings while restoring the prior Direct LLM
provider configuration and timeout. Recreate only the services that consume
the Direct LLM settings:

`docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml up -d --no-deps --force-recreate backend worker scheduler`

Then verify backend readiness, all eight service health states, the restored
non-secret Direct LLM settings, and the Bailian/Qdrant integrity invariants.
Do not delete either Qdrant collection. No Phase 2 disaster-recovery work was
started.

## Bailian Embedding Migration Gate

The Bailian migration was completed only after the provider smoke and all
pre-switch integrity/retrieval checks passed. No crawl, parse, rechunk, or
attachment operation ran, and PostgreSQL rows were not modified.

Configured OpenAI-compatible base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`;
the client appends `/embeddings` and sends model `text-embedding-v4` with
requested dimensions `1536`.

| Check | Result | Evidence |
|---|---|---|
| Bailian minimal embedding | `PASS-LIVE` | One request loaded the credential only from `/home/deploy/.config/odirag/secrets/bailian_api_key`; HTTP 200, provider Alibaba Cloud Model Studio / Bailian, model `text-embedding-v4`, latency `586.1 ms`, returned vector length `1536`. No key or vector values were recorded. |
| New collection creation | `PASS-LIVE` | `odirag_chunks_bailian_v4`, vector size `1536`, distance `Cosine`; the original `odirag_chunks` collection was never passed to a write/delete operation. |
| Exact re-embedding | `PASS-LIVE` | PostgreSQL source selected exactly `821` approved/indexed chunks; `83` Bailian batches produced `821` vectors. Existing `chunk_id`, document identity, chunk order, payload metadata, and provenance were preserved. |
| New collection integrity | `PASS-LIVE` | Status `green`, points `821`, vector size `1536`, Cosine, duplicate payload `chunk_id=0`, missing payload `chunk_id=0`; PostgreSQL and new Qdrant chunk ID sets are equal. |
| Pre-switch retrieval | `PASS-LIVE` | Bailian query vectors drove vector retrieval and hybrid BM25+vector retrieval; Cohere `rerank-v3.5` applied successfully with `8` reranked results. |
| Production runtime switch | `PASS-LIVE` | Active settings report provider `remote`, host `dashscope.aliyuncs.com`, model `text-embedding-v4`, dimensions `1536`, collection `odirag_chunks_bailian_v4`; the running backend repeated vector, hybrid, and Cohere rerank smoke successfully. |
| Required service restart | `PASS-LIVE` | Only `backend`, `worker`, and `scheduler` were recreated. PostgreSQL, Redis, Qdrant, frontend, and Nginx were not restarted; all eight services returned healthy. |
| Rollback availability | `PASS-LIVE` | Old `odirag_chunks` remained green with `821` points, `1536`/Cosine, and unchanged payloads. Previous env is retained at `/etc/odirag/production.env.pre-bailian-20260815` with mode `0640`. |

### Post-switch data integrity

| Invariant | Result |
|---|---:|
| documents | `182` |
| chunks | `821` |
| parsed attachments | `60` |
| duplicate `chunk_id` | `0` |
| duplicate `(document_id, chunk_index)` | `0` |
| old `odirag_chunks` points | `821` |
| new Bailian points | `821` |
| duplicate new Qdrant payload `chunk_id` | `0` |
| PostgreSQL -> new Qdrant ID set equality | `true` |

### Exact rollback

The old collection is retained and must not be deleted. The retained
`/etc/odirag/production.env.pre-bailian-20260815` file predates both the
Bailian and DeepSeek changes, so restoring that whole file is a **combined
provider rollback**: it restores the prior OpenAI-compatible embedding,
`text-embedding-3-small`, embedding version `v1`, collection
`odirag_chunks`, and also the pre-DeepSeek Direct LLM settings.

For an **embedding-only rollback that keeps DeepSeek active**, use the retained
file as the protected source and atomically restore only the embedding provider,
base URL, credential, model, dimensions, version, and Qdrant collection fields.
Leave the Direct LLM, answer-provider, dependency-timeout, and rerank fields
unchanged. Do not print either credential while performing the controlled
field-level update. In either rollback mode, validate the rendered Compose
configuration and recreate only `backend`, `worker`, and `scheduler` with:

`docker compose --env-file /etc/odirag/production.env -f deploy/production/compose.yml up -d --no-deps --force-recreate backend worker scheduler`

Verify backend readiness and the original collection before accepting the
rollback. Neither `odirag_chunks` nor `odirag_chunks_bailian_v4` is to be
deleted.

## Test and Static Gates

- `D:\RAG\backend\.venv\Scripts\python.exe -m pytest`: **524 passed**, 0
  failed, 0 skipped, 0 pytest warnings, 38.77 seconds in the final closure run.
- Ruff: `All checks passed!`.
- Mypy: `Success: no issues found in 170 source files`.
- Production Compose example validation: `docker compose ... config --quiet`
  exited 0 locally and on the target.
- `git diff --check`: no whitespace errors (only existing Git line-ending
  normalization warnings).

## Gate Status

Statuses use only `PASS-LIVE`, `PASS-CONFIG`, `PARTIAL`, `FAIL`, or `BLOCKED`.

| Gate | Status | Evidence / boundary |
|---|---|---|
| Privileged preflight and working-tree classification | PASS-LIVE | Real SSH/UFW/Fail2ban/LXD/reboot/listener checks and 166-path classification completed. |
| SSH hardening and independent reconnect | PASS-LIVE | Port 22022 fresh connection succeeded; port 22 timed out; effective sshd values verified. |
| UFW and Fail2ban | PASS-LIVE | Default-deny UFW with only 22022; `sshd` jail active. |
| Ubuntu 22.04 update and controlled reboot | PASS-LIVE | Jammy update/reboot/reconnect completed; no release upgrade. |
| Official Docker Engine | PASS-LIVE | Docker/Compose versions and `hello-world` verified on target. |
| Production Compose topology and static validation | PASS-CONFIG | Reviewed source, healthchecks, dependencies, networks, resource declarations, and config render validated. |
| Secrets structure and production settings | PASS-CONFIG | Runtime env outside Git, no plaintext admin password, provider/key presence checked without values. |
| First boot and all-service health | PASS-LIVE | PostgreSQL, Redis, Qdrant, backend, worker, scheduler, frontend, and Nginx healthy. |
| Persistence and frozen corpus integrity | PASS-LIVE | PostgreSQL counts, Alembic head, 70/70 data hashes, and Qdrant 821-point/1536-vector evidence match. |
| Health endpoints and loopback ingress | PASS-LIVE | Nginx `/healthz`, root live/ready, frontend root, and compatibility health returned expected status. |
| Resource limits, log rotation, and port exposure | PASS-LIVE | `docker inspect`, `docker stats`, symlinked Nginx logs, and host listener checks completed. |
| BM25/structured API smoke | PASS-LIVE | Authenticated BM25 search and SQL chat returned HTTP 200 with expected counts. |
| Remote rerank provider | PASS-LIVE | Real Cohere request returned HTTP 200 and valid result shape. |
| Bailian embedding migration | PASS-LIVE | Real Bailian request returned HTTP 200 with a 1536-dimensional vector; the new collection passed exact integrity checks and became active only after verification. |
| Vector retrieval | PASS-LIVE | Bailian query embedding and the active `odirag_chunks_bailian_v4` collection returned real vector hits; the final application probe produced `20` vector candidates. |
| Hybrid retrieval | PASS-LIVE | The actual application path produced BM25 `20`, vector `20`, fusion `8`, and final context results before generation or refusal. |
| DeepSeek Direct LLM | PASS-LIVE | Current model discovery, host/container HTTP 200 smoke, active application adapter, and bounded timeout were verified without exposing the credential or response bodies. |
| Grounded LLM generation | PASS-LIVE | The real production `ChatService` completed Bailian/BM25/hybrid/Cohere/context/DeepSeek and passed citation plus answer-support validation. |
| Out-of-scope refusal smoke | PASS-LIVE | A semantically complete unsupported query traversed the real hybrid retrieval/rerank path and was refused for `insufficient_evidence_relevance`, with no citations and no Direct LLM generation. |
| TLS/public ingress, PITR/backups, monitoring, registry, and automated rollback | PARTIAL | Explicitly outside bounded Phase 1; Nginx is loopback-only and no TLS/public port was opened. |
| Frontend dependency audit | PARTIAL | Build passed; npm reported one high-severity dependency vulnerability requiring a separate remediation decision. |
| Qdrant authentication | PARTIAL | Qdrant API-key auth was left disabled because the image treated an empty key as enabled; service remains private on the internal network with no host port. |
| Temporary sudo closeout | PASS-LIVE | `/etc/sudoers.d/99-rag-deploy-temp` is absent; a fresh SSH connection ran `sudo -n true` and received exit code 1 (`sudo: a password is required`). |

## Residual Risks and Stop Point

1. Bailian embedding, the versioned `odirag_chunks_bailian_v4` collection,
   DeepSeek Direct LLM, grounded generation, and fail-closed refusal are
   accepted PASS-LIVE. The original `odirag_chunks` collection remains the
   embedding rollback target; changing a provider or collection again requires
   the same compatibility, integrity, retrieval, and grounded-answer checks.
2. Provider credentials remain external to Git and reports. The application
   continues to fail closed on provider, evidence, citation, or answer-support
   failure and does not leak provider response bodies.
3. TLS termination, public ingress, backups/PITR, monitoring/alerting,
   registry provenance/signing, automated rollback, and the frontend high
   severity dependency remediation remain Phase 2 work.
4. Docker group membership is operationally privileged. Qdrant has network
   isolation but no API-key authentication in this release.
5. Production probes emit a Qdrant compatibility warning because
   `qdrant-client` `1.19.0` is newer than Qdrant server `1.14.1`. Health,
   collection integrity, vector retrieval, hybrid retrieval, and rerank all
   passed live. Version alignment requires a separately reviewed maintenance
   change; no server or client upgrade was attempted in this closure.

No further production mutation is authorized in this report. Production Phase
1 is closed at `PASS-LIVE`; the deployment should remain at this stop point
until a separately approved Phase 2 decision.
