# Production Phase 1 Execution Plan

Date: 2026-08-15
Scope: first production deployment only
Repository: `D:\RAG`
Remote: `rag-prod` (`deploy` user)

## Goal

Deploy the current, tested RAG working tree to the empty production host while
preserving the frozen corpus and without introducing a second ingestion run.
The phase ends after the first boot, live smoke checks, data-integrity evidence,
and temporary sudo revocation.

This is an execution plan, not a claim that any gate has passed. A gate is
marked `PASS-LIVE` only after the corresponding command has run successfully
against the real target.

## Frozen Constraints

- Do not perform an Ubuntu 24.04 release upgrade.
- Do not delete unknown files, volumes, containers, LXD instances, or database
  data. New production resources use an explicit `odirag-prod-` prefix.
- Do not print, commit, or place real secrets in this repository, Dockerfiles,
  reports, or command output.
- Do not use `git add -A`; the current working tree contains evidence and
  evaluation artifacts that are not deployment inputs.
- Do not change the closed attachment parsing business logic. Only deployment
  wiring or a demonstrated startup blocker may justify a change.
- Do not batch crawl, ingest, or reindex the corpus during boot.
- Do not implement Phase 2 PITR, monitoring, CI/CD, image registry, TLS,
  automated rollback, or disaster-recovery runbooks.

## Baseline Evidence

- HEAD: `eb356a0f1fa382c481540dfed56dbcabd030d5d0` on `master`.
- Working tree: 57 modified and 109 untracked paths (166 total); this is an
  intentional dirty Phase closure state and must be classified, not reset.
- Backend test command: `backend\.venv\Scripts\python.exe -m pytest`.
- Test result: 518 passed, 0 failed, 0 skipped, 0 pytest warnings.
- Local source data: 182 documents (101 approved, 35 rejected, 46 pending
  manual review), 821 PostgreSQL chunks, 821 green Qdrant points, 123
  attachments, 60 parsed attachments with complete provenance.
- Identity-level duplicate chunks and Qdrant payload IDs: 0. One same-document
  content-hash group exists (document 128, chunk indexes 3 and 11); the final
  report must state this metric distinction rather than silently relabel it.
- Production host: Ubuntu 22.04, 8 vCPU, 7.6 GiB RAM, no swap, 39 GiB root
  disk with about 37 GiB free. Docker is not installed. LXD has no instances.
- Current server security evidence: UFW inactive; Fail2ban `sshd` jail active;
  effective sshd has ports 22 and 22022, password authentication enabled, and
  root login enabled. These are implementation blockers, not PASS claims.

## Working-Tree Classification

Deploy only an explicit reviewed bundle. Include current backend runtime code,
the complete Alembic chain through 0012, frontend source, config, deployment
templates, Dockerfiles, and operational scripts required by the production
compose. Exclude `.env`, `.git`, virtual environments, caches, pytest temporary
directories, all evaluation/performance data, human-review workbooks, and
reports. Preserve the local worktree and volumes; do not stage or clean it.

## Ordered Gates

### 1. Privileged preflight (read-only)

Record effective `sshd -T`, UFW policy, Fail2ban `sshd` jail, LXD projects and
instances, kernel/reboot markers, package state, resource capacity, listeners,
and non-base workloads. Stop if an unknown workload is found.

### 2. SSH safety and firewall

Keep a persistent existing SSH session alive. Back up the relevant SSH config
files to a root-owned, timestamped path. Allow TCP 22022 in UFW before changing
the daemon. Set effective values to: port 22022 only, public-key auth enabled,
password and keyboard-interactive auth disabled, root login disabled,
`LoginGraceTime 30`, and `MaxAuthTries 3`. Run `sshd -t`, reload SSH, then
open and validate a second independent `rag-prod` connection. If it fails,
restore the backups through the persistent session immediately and re-test.
Enable UFW with default-deny incoming/default-allow outgoing and only the
required SSH rule; application traffic remains loopback-only until a later TLS
phase. Keep Fail2ban enabled and verify its jail after the change.

### 3. Ubuntu 22.04 updates and controlled reboot

Confirm the provider VNC/Web Console recovery path (the user-provided rescue
path is the fallback) and that SSH is enabled at boot. Run only the normal
Jammy update/upgrade; never run `do-release-upgrade`. Re-check package and
reboot markers, reboot once when the installed kernel/system packages require
it, then reconnect automatically on port 22022. Verify hostname, kernel, SSH,
UFW, and Fail2ban after the host returns before continuing.

### 4. Official Docker Engine

Use Docker's official Ubuntu apt repository and install Docker Engine, CLI,
containerd, Buildx, and the Compose plugin. Enable/start Docker, run the
official `hello-world` smoke test, add `deploy` to the `docker` group, and
validate `docker ps` in a fresh independent SSH session. Record the high-
privilege nature of Docker group membership.

### 5. Application and production layout

Add a separate `deploy/production` compose and safe `.env.example`, secrets
README/.gitignore, and `runbooks/production-deployment.md`. Keep the existing
development compose unchanged. Add root `/health/live` and `/health/ready`:
liveness must have no dependency and return 200; readiness must require
PostgreSQL, Redis, and Qdrant all healthy and return 503 otherwise. Bypass the
rate limiter for both probes. Preserve `/api/system/health` compatibility.

The production compose contains only actual services: PostgreSQL, Redis,
Qdrant, backend, worker, scheduler, frontend, and nginx. Stateful services have
no host-published ports. Nginx binds to loopback port 8080 for this no-TLS
phase. Use explicit healthchecks, readiness dependencies, restart policies,
`no-new-privileges`, bounded resources, and Docker json-file rotation.

### 6. Resource and persistence budget

Use standalone Compose limits with a hard total of about 6144 MiB, leaving at
least 1.6 GiB for the host and future work:

| Service | Memory | CPU | PIDs |
|---|---:|---:|---:|
| PostgreSQL | 1024 MiB | 1.25 | 200 |
| Qdrant | 1536 MiB | 1.50 | 200 |
| Redis | 512 MiB | 0.50 | 100 |
| Backend | 1024 MiB | 1.25 | 256 |
| Worker (`--concurrency=2`) | 1536 MiB | 1.75 | 256 |
| Scheduler | 256 MiB | 0.25 | 64 |
| Frontend | 128 MiB | 0.25 | 64 |
| Nginx | 128 MiB | 0.25 | 128 |

Persist PostgreSQL, Qdrant, Redis AOF, shared application data, attachment
bytes, parsed/raw state, and the BM25 snapshot in named `odirag-prod-*`
volumes. Do not claim backup/restore readiness in this phase.

### 7. Secrets and initial state transfer

Keep production secrets in a server-controlled file outside Git, mode 0600,
and inject them through environment variables because the application contract
is environment-based. Generate new database, Redis, Qdrant, and JWT secrets on
the server without printing them. Transfer provider values only through an
encrypted transport and never echo them. Production validation must use
`ODIRAG_ENVIRONMENT=production`, non-demo providers, Redis rate limiting,
explicit HTTPS CORS origins, and no plaintext admin password.

The target host is empty, so preserve the frozen corpus with a one-time,
non-ingestion initial state transfer: a consistent PostgreSQL dump/restore,
attachment/BM25 application-data copy, and an exact Qdrant collection transfer
with point IDs and vector dimensions preserved. This is solely the initial
deployment seed; no reusable Phase 2 Qdrant restore or disaster-recovery
workflow is implemented. Redis starts empty because it is cache/queue state,
not the source of truth. Verify source and target counts before and after each
transfer and abort on any mismatch.

### 8. First boot and evidence

Run `docker compose config` before starting. Start stateful services first,
load only the verified initial state, then start backend/worker/scheduler,
frontend, and nginx. Inspect `docker compose ps`, health, logs, restart policy,
resource limits, mounts, and log rotation with `docker inspect`. Run live and
ready probes plus one real retrieval, one real rerank attempt, one real RAG
query, and one real generation. A provider failure is reported as PARTIAL or
FAIL; it is never converted to PASS.

Verify the frozen invariants after boot: 821 PostgreSQL chunks, 821 Qdrant
points, 60 attachment provenance rows, zero identity-level duplicate chunks,
and zero duplicate Qdrant payload IDs. Do not run crawl/ingest/reindex.

### 9. Closeout

Create `PRODUCTION_PHASE_1_REPORT.md` with exact commands, evidence, files,
resource budget, ports, volumes, secrets strategy, gate statuses, risks, and
remaining blockers. Re-check `git diff` and stage only explicitly intended
files if staging is requested. Remove temporary sudo with
`sudo rm -f /etc/sudoers.d/99-rag-deploy-temp`, then verify `sudo -n true`
fails. Never claim PASS-LIVE for a step lacking real target evidence.

## Rollback Rules

- SSH: restore the timestamped config backups through the persistent session if
  the fresh 22022 connection fails.
- UFW: retain the existing session; restore the prior rules if SSH access is
  lost. Do not reboot until the second connection succeeds.
- Package/reboot: do not release-upgrade; use VNC/Web Console if SSH does not
  return, and stop before Docker installation until access is restored.
- Application: use a new release directory and named volumes; never remove
  unknown data. Stop only the explicitly named Phase 1 services if rollback is
  required.
- Data: keep source volumes untouched. Abort on checksum/count mismatch; do not
  retry with a bulk ingest.

## Self-Review Result

- Scope is one production deployment phase and stops before Phase 2 systems.
- Every requested service, persistence asset, health contract, secret class,
  resource limit, and evidence gate has an explicit owner step.
- No step requires a real secret in chat, Git, a Dockerfile, or a report.
- The only data writes are to newly named production resources or the requested
  deployment files; existing source data is read-only during transfer.
- The plan preserves the attachment closure and explicitly distinguishes
  initial state transfer from later disaster recovery.
