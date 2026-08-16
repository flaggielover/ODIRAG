# ODIRAG Production Phase 3 Report

生成日期：2026-08-16（Asia/Shanghai）
阶段：Observability, Metrics, Dashboards & Alerting
结论：`PHASE_3_OVERALL=PASS-LIVE`

本报告只记录真实执行、实际抓取和实际故障注入证据。未执行的外部通知和公网可用性检查分别标记为 `BLOCKED`，没有推断为通过。报告不包含 API key、密码、Authorization header、用户查询、回答正文或完整向量。

## Executive Summary

- 生产应用栈：8/8 容器运行且健康。
- 监控栈：8/8 容器运行；Prometheus 10/10 targets 为 `UP`。
- 生产探针：`/health/live=200`、`/health/ready=200`、Nginx `/healthz=200`。
- 监控管理接口：Prometheus、Grafana、Alertmanager 均返回 HTTP 200，且仅绑定 loopback。
- 告警生命周期：HostDown 与 BackendDown 两个受控故障均真实进入 pending、firing、Alertmanager、recovery、resolved。
- 当前告警：Prometheus 0，Alertmanager 0。
- 生产回归：531/531 tests passed，Ruff passed，mypy passed。
- 数据完整性：182 documents、821 chunks、60 parsed attachments、69 attachment byte files；活动 Qdrant collection 821 points，集合与 PostgreSQL chunk ID 集合完全一致。
- Phase 4 和 Phase 5 均未启动。

## 1. Phase 1 Baseline

Phase 1 已验收为 `PHASE_1_OVERALL=PASS-LIVE`。本阶段开始时的已接受基线包括 Ubuntu 22.04、Docker Compose 生产栈、8/8 应用服务健康、SSH 端口 22022、UFW 与 Fail2ban 启用、数据库/Redis/Qdrant/backend 不公开、Nginx 仅 loopback。活动 embedding 为 Bailian `text-embedding-v4`，维度 1536；活动 collection 为 `odirag_chunks_bailian_v4`，旧 `odirag_chunks` 保留为回滚集合。

## 2. Phase 2 Baseline

Phase 2 已验收为 `PHASE_2_OVERALL=PASS-LIVE`。既有真实证据包括 PostgreSQL logical backup/restore、WAL archive、base backup、PITR、Qdrant snapshot/restore、Redis persistence/recovery、attachment backup/restore 和 cross-component drill。已测 PostgreSQL RPO 为 1 秒、RTO 为 6.804 秒；cross-component DR recovery duration 为 69.973 秒；off-host manifest 7/7 artifacts 通过 size/hash 校验。

## 3. Phase 3 Scope

本阶段实现并现场验证 host、container、PostgreSQL、Redis、Qdrant、backend/API、RAG、provider metrics，以及 Prometheus、Grafana、Alertmanager、内部 Blackbox probing、告警规则、真实故障注入、百分位测量与生产回归。没有执行 DNS、TLS、公开 Nginx ingress、外部公网 uptime、CI/CD 或自动发布。

## 4. Observability Architecture

| Layer | Component | Data path | Exposure |
| --- | --- | --- | --- |
| Host | node_exporter + textfile collector | Host metrics and ODIRAG operational snapshots | Docker private network only |
| Containers | cAdvisor | Docker CPU/memory/network/filesystem | Docker private network only |
| Data stores | postgres_exporter, redis_exporter, Qdrant native `/metrics` | Database/cache/vector metrics | Application private network only |
| Application | Backend internal `/metrics` | HTTP, DB, provider and RAG metrics | Internal network only; not proxied by Nginx |
| Probes | blackbox_exporter | Backend live/ready and Nginx healthz | Private/edge Docker networks only |
| Collection | Prometheus | 15-second scrape and rule evaluation | `127.0.0.1:9090` only |
| Visualization | Grafana | Provisioned Prometheus datasource and dashboards | `127.0.0.1:3000` only |
| Alerting | Alertmanager | Grouping, deduplication and internal lifecycle | `127.0.0.1:9093` only |

`odirag-monitoring` 是独立 internal bridge。Prometheus 另接入应用 private network；Blackbox 仅接入所需 private/edge networks。`odirag-monitoring-management` 是非 internal 管理 bridge，但其 Prometheus、Grafana、Alertmanager host publishing 全部显式绑定 `127.0.0.1`。Exporter 不发布宿主端口。

## 5. Monitoring Resource Budget

| Service | CPU limit | Memory limit | Persistent policy |
| --- | ---: | ---: | --- |
| Prometheus | 0.20 | 256 MiB | 15 days and 2 GiB maximum |
| Grafana | 0.15 | 256 MiB | Persistent SQLite volume |
| Alertmanager | 0.04 | 32 MiB | 120-hour state retention |
| node_exporter | 0.03 | 32 MiB | None |
| cAdvisor | 0.10 | 96 MiB | None |
| postgres_exporter | 0.03 | 32 MiB | None |
| redis_exporter | 0.03 | 32 MiB | None |
| blackbox_exporter | 0.04 | 32 MiB | None |

合计硬限制为 0.62 CPU、768 MiB。所有服务配置 `restart: unless-stopped`、`no-new-privileges`、bounded pids 和 Docker `json-file` 日志轮转（5 MiB x 3）。

初始 operational targets（观测目标，不是合同 SLA）：

| Signal | Initial target / threshold |
| --- | --- |
| API availability | 24h observed availability >= 99.5% |
| RAG request success | 15m observed success >= 95% |
| API P95 | Observe against 2s warning threshold |
| RAG P95 | Observe against 10s warning threshold |
| Provider errors | Any bounded provider error increase in 5m requires investigation |
| Host memory | Keep utilization below 85% sustained threshold |
| Filesystem | Keep free space above 15%; 5% is critical |

短期 Phase 3 样本不能证明长期达成上述目标，只用于验证指标与告警链路。

## 6. Prometheus Version And Configuration

- Version: Prometheus 3.13.2。
- Scrape interval: 15s；scrape timeout: 10s；evaluation interval: 15s。
- TSDB: persistent named volume，WAL compression，retention 15d，size cap 2GB。
- Rule files: 7 groups，30 rules，30/30 rule health `ok`。
- Alertmanager discovery: 1 active endpoint。
- `promtool` 对运行配置和规则完成现场校验。

## 7. Prometheus Target Status

最终现场查询：10/10 active targets 为 `UP`，0 down。

| Job | Targets | Status |
| --- | ---: | --- |
| prometheus | 1 | UP |
| node | 1 | UP |
| cadvisor | 1 | UP |
| postgres | 1 | UP |
| redis | 1 | UP |
| qdrant | 1 | UP |
| backend | 1 | UP |
| blackbox-http | 3 | UP |

Prometheus 重启后 TSDB 保持，head series 从 10,336 恢复并增长至 10,393；targets 全部恢复。

## 8. Host Metrics Evidence

node_exporter 实际提供 CPU、load、memory、swap、filesystem、disk I/O、network、inode 与 uptime 指标。现场样本包括 CPU utilization 约 17.48%、load1 约 0.73、总内存约 8.12 GB、available memory 约 6.34 GB、root filesystem available 约 31.57 GB。最终磁盘审计为 39G 总量、11G 已用、29G 可用（27% used）。

## 9. Container Metrics Evidence

cAdvisor 现场返回 21 个 named containers，其中 8 个生产应用容器均有指标。已验证 container CPU、memory、network、filesystem 指标；容器运行和 restart 状态由 textfile collector 补充。采样时应用栈总内存约 576 MiB，CPU rate 约 0.513 core。最终 8/8 应用容器仍运行且健康。

## 10. PostgreSQL Metrics Evidence

postgres_exporter 使用 dedicated role `odirag_monitor` 和 `pg_monitor`，没有复用数据库 superuser。凭据通过 file secret 注入。现场证据：`pg_up=1`、scrape error=0、4/100 connections、database size 86,374,000 bytes、deadlocks=0。WAL textfile metrics 覆盖 archive mode、pending files、last success/failure 和 failure increments；最终 ready backlog=0。

## 11. Redis Metrics Evidence

redis_exporter 使用 file secret，且密码不出现在 container inspect environment。现场证据：`redis_up=1`、used memory 约 2.9 MB、connected clients 15、evicted keys 0、rejected connections 0、RDB last save status=1、AOF enabled=1、AOF rewrite status=1。Redis 与 exporter 均无公开端口。

## 12. Qdrant Metrics Evidence

使用已安装 Qdrant 的原生 `/metrics`。现场证据：target `UP`，169 次 REST responses，失败数 0，采样平均 request latency 约 0.0726s。textfile collection checks 确认：

- Active `odirag_chunks_bailian_v4`: green，821 points，1536 dimensions，Cosine。
- Rollback `odirag_chunks`: green，821 points，未修改。
- Active duplicate payload `chunk_id`: 0；PostgreSQL 与 Qdrant chunk ID set equality: true。

## 13. Backend / API Metrics

Backend 新增内部 Prometheus endpoint `/metrics`，不经过 Nginx。它记录 HTTP requests、status class、duration histogram、in-flight、exceptions 和 DB latency/error。route 使用稳定模板并有 cardinality cap。现场看到 20 个 ODIRAG metric families、75 个 API/RAG 前置样本，route cardinality 为 4，unsafe label keys 为 0。最终证据采集时，Prometheus 查询显示运行中 backend target 的 HTTP request counter 与 histogram count 均为 491，证明主进程 registry 正在被真实 scrape。该计数会随 15s scrape 增长。Nginx 访问 `/metrics` 不会暴露 backend metrics。

## 14. RAG Business Metrics

RAG metrics 覆盖 request count、embedding、vector retrieval、BM25、hybrid merge、rerank、Direct LLM、end-to-end duration、candidate counts、grounded count、refusal count 和 bounded error categories。所有 label 均为受控枚举；metrics snapshot 已断言不包含查询、回答、authorization 或 request ID。

一次最多 6 请求的 no-write production sample 在生产 backend 容器内创建独立 ASGI app，使用真实生产 settings/runtime、真实 PostgreSQL、Bailian、Qdrant、Cohere 与 DeepSeek。数据库事务强制 read-only，repository writes 替换为内存实现，最终新增 trace writes=0。该独立 registry 的完整 Prometheus exposition 通过 node_exporter textfile collector 进入生产 Prometheus，label `job="node"`；它没有伪装为运行中 backend process 的 registry。最终现场查询为 RAG count=6、RAG histogram count=6、各 stage histogram count=6（Direct LLM 与 refusal 各 3），可审计区分 live backend HTTP series 与 bounded no-write RAG evidence series。

## 15. Provider Metrics

Provider metrics 使用 bounded labels `provider`、`operation`、`outcome/status`、`error_category`，并记录 count、latency、success/failure。真实样本：Bailian 7 operations、Qdrant 6、Cohere 6、DeepSeek 3，全部 success、provider error 0。Bailian 直接 embedding smoke 返回 vector length 1536。cached embedding wrapper 的 provider label 已修正为底层 Bailian，而不是错误的 wrapper 名称。

## 16. Grafana Version

Grafana 13.1.3。API health 为 `database=ok`，Prometheus datasource UID `odirag-prometheus` health 为 `OK`。Grafana 初始 160 MiB 限制出现真实 OOM 证据后调整至 256 MiB；调整后重启验证 healthy、restart count 0、OOM=false。

## 17. Provisioned Dashboards

Grafana 重启后仍自动 provision 9/9 dashboards：

1. Host Overview (`odirag-host`)
2. Container Overview (`odirag-containers`)
3. API / Backend (`odirag-api`)
4. PostgreSQL (`odirag-postgresql`)
5. Redis (`odirag-redis`)
6. Qdrant (`odirag-qdrant`)
7. RAG Pipeline (`odirag-rag`)
8. Provider Health (`odirag-providers`)
9. Production SLO / Golden Signals (`odirag-slo`)

## 18. P50 / P95 / P99 Results

PromQL histogram 结果如下。API 表达式只查询运行中 `job="backend"`；RAG 表达式只查询 `job="node"` 的有界 no-write evidence snapshot，二者未混合。

| Metric | P50 | P95 | P99 |
| --- | ---: | ---: | ---: |
| API request latency (`job=backend`, count=491) | 0.02685s | 0.05453s | 0.19544s |
| RAG end-to-end latency | 1.0s | 8.5s | 9.7s |

Stage P95：embedding 0.085s、vector retrieval 4.25s、BM25 0.085s、hybrid merge 0.00475s、rerank 0.97s、Direct LLM 4.8125s、end-to-end 9.25s。

## 19. Sample Size

API histogram 在最终取证时有 491 个运行中 backend samples；它们主要来自内部 scrape/health traffic，只代表当前内部 API traffic mix。RAG 百分位样本为 6 个有界、顺序执行的真实 production-runtime requests：3 个 grounded、3 个 refusal。RAG 总时长 19.252s；客户端 wall-clock P50 1.716s、P95 8.353s、P99 9.490s。Prometheus API 已再次独立复算出 RAG P50=1.0s、P95=8.5s、P99=9.7s，RAG total=6。样本量很小，只证明真实 provider/runtime、histogram exposition、scrape 和 PromQL 链路有效，不能推断长期 SLA 或容量上限。

## 20. Error Rate

运行中 backend API 证据采集时没有 5xx series，即 0/491 observed 5xx。初始有界 RAG 样本为 6/6 completed、errors=0、error rate=0%。故障注入后的第一次回归在任何可见 provider call 和数据库写入前安全失败，输出已限制为通用 error code；一次有界重试为 6/6、errors=0、duration 17.339s、trace writes=0。该瞬时失败在本报告中保留，不隐藏。

## 21. Alert Rules

7 个 rule groups 共 30 条 rules，30/30 health `ok`。要求的 26 类告警均存在，包括 HostDown、HighCPU、HighMemory、DiskSpaceLow、FilesystemCritical、ContainerDown、ContainerRestartLoop、BackendDown、BackendHigh5xx、BackendHighLatency、PostgreSQLDown、PostgreSQLConnectionPressure、PostgreSQLDeadlocks、RedisDown、RedisMemoryPressure、RedisPersistenceFailure、QdrantDown、QdrantCollectionUnhealthy、QdrantPointCountMismatch、RAGHighErrorRate、RAGHighLatency、EmbeddingProviderErrors、RerankProviderErrors、LLMProviderErrors、BackupStaleness 和 WALArchiveStaleness。另有 4 条强化规则：WALArchiveFailure、TextfileMetricsStale、TextfileMetricsMissing、TextfileDependencyCollectorFailed。

WAL 规则经过现场语义修正：staleness 只在 pending files > 0 且 last success 超过 30 分钟时触发；failure 只在 15 分钟窗口内 failures 增长时触发，避免历史失败计数产生永久假阳性。

## 22. Alertmanager Configuration

Alertmanager 0.33.1，配置已通过 `amtool` 现场校验。`resolve_timeout=5m`；`group_by=[alertname, service, severity]`；`group_wait=30s`；`group_interval=5m`；`repeat_interval=4h`。critical 会 inhibit 同一 alert/service 的 warning。持久状态 retention 为 120h，接口只绑定 `127.0.0.1:9093`。

## 23. Alert Receiver State

内部 receiver `internal-audit` 已配置，Prometheus 到 Alertmanager 的 discovery、delivery、deduplication 与 resolution 均真实验证。当前没有已授权的 email/Slack/PagerDuty/webhook 凭据，因此 external receiver count=0，`EXTERNAL_ALERT_DELIVERY=BLOCKED`。没有创建伪造或临时外部 receiver。

## 24. Blackbox Probe Evidence

内部 blackbox exporter 实际探测：

| Target | HTTP | probe_success | Observed duration |
| --- | ---: | ---: | ---: |
| Backend `/health/live` | 200 | 1 | ~6.16 ms |
| Backend `/health/ready` | 200 | 1 | ~37.15 ms |
| Nginx `/healthz` | 200 | 1 | ~2.66 ms |

未创建公网探针，应用 ingress 仍仅 loopback。

## 25. Fault Injection Scenarios

执行了两个有白名单、自动恢复、信号安全的受控场景：

1. 停止 node_exporter，验证 `HostDown` pending/firing/Alertmanager/resolved，然后恢复并确认 exporter ready。
2. 停止 backend，验证 `BackendDown` pending/firing/Alertmanager/resolved，然后恢复并确认容器 healthy、condition 清零。

脚本只允许指定容器的 `inspect/stop/start`，不操作数据库、卷、collection 或生产数据。执行前经三轮独立代码复审；finally 根据真实容器状态强制恢复，恢复失败不能输出 PASS。

## 26. Alert Firing Evidence

| Scenario | T0 fault | Pending observed | T2 firing | Result |
| --- | --- | ---: | ---: | --- |
| HostDown | 06:44:58.690Z | 15.027s | 135.268s | PASS-LIVE |
| BackendDown | 06:48:53.052Z | 30.068s | 150.270s | PASS-LIVE |

两次 firing 都由 Prometheus live API 返回并满足 scenario-specific labels。

## 27. Alert Delivery Evidence

内部 Prometheus -> Alertmanager 交付：

- HostDown: 约 0.005s 从 firing 到 Alertmanager active receipt。
- BackendDown: 约 0.004s 从 firing 到 Alertmanager active receipt。

Alertmanager 匹配 alertname/job/instance/service、active status 及 `startsAt >= T0 - 5s`，避免残留同名告警假阳性。外部通知未配置，因此 external delivery 为 `BLOCKED`，不是 `PASS-LIVE`。

## 28. Alert Resolution Evidence

- HostDown：容器恢复并确认 ready 后，Alertmanager resolution 于 15.030s 内观察到。
- BackendDown：backend 恢复 healthy 且 Prometheus condition 清零后，Alertmanager resolution 于 15.032s 内观察到。

最终 Prometheus alerts=0、Alertmanager alerts=0；应用 8/8 healthy、targets 10/10 UP。

## 29. Detection Latency

- HostDown T1 detection latency: 15.024s。
- BackendDown T1 detection latency: 15.041s。

与 15s scrape/evaluation cadence 一致。

## 30. Firing Latency

- HostDown: 135.268s from T0。
- BackendDown: 150.270s from T0。

这包括规则配置的 `for` duration 以及 scrape/evaluation alignment，不是通知网络延迟。

## 31. Resolution Latency

- HostDown: 15.030s from confirmed recovery to resolved observation。
- BackendDown: 15.032s from confirmed healthy/condition-clear to resolved observation。

## 32. Production Regression

故障注入后确认：8/8 应用服务 healthy、8/8 monitoring containers running、10/10 Prometheus targets UP、三个生产健康端点 200、Prometheus/Alertmanager alerts 归零。第二次有界 no-write RAG regression 为 6/6、provider checks 全通过、vector length 1536、数据库 trace writes=0。

## 33. Test Results

- `pytest`: 531 collected，531 passed，0 failed，exit code 0，61.52s。
- Ruff: all checks passed。
- mypy: 171 source files，no issues found。
- `git diff --check`: exit code 0；只有工作区 CRLF 提示，无 whitespace errors。
- Phase 3 focused backend observability tests 在全量测试前也已通过。

## 34. Data Integrity

最终只读校验：

| Check | Result |
| --- | ---: |
| Documents | 182 |
| Chunks | 821 |
| Parsed attachments | 60 |
| Attachment byte files | 69 |
| Duplicate chunk_id | 0 |
| Duplicate (document_id, chunk_index) | 0 |
| Active Qdrant points | 821 |
| Duplicate active Qdrant payload chunk_id | 0 |
| Missing IDs between PostgreSQL and active Qdrant | 0 |
| Active vector config | 1536 / Cosine / green |
| Temporary Qdrant collections | 0 |

Backup manifest 仍为 7/7 artifacts size/hash verified，89 files、127,789,734 bytes。没有重新 crawl、parse、chunk 或修改 attachment pipeline。

## 35. Exposed / Listening Ports

最终 `ss` 与 Docker port audit：

| Bind | Purpose | Boundary |
| --- | --- | --- |
| `0.0.0.0:22022`, `[::]:22022` | Hardened SSH | Expected public administration path |
| `127.0.0.1:8080` | Production Nginx | Loopback only |
| `127.0.0.1:3000` | Grafana | Loopback only |
| `127.0.0.1:9090` | Prometheus | Loopback only |
| `127.0.0.1:9093` | Alertmanager | Loopback only |
| `127.0.0.53:53` | Local resolver | Host-local |

PostgreSQL、Redis、Qdrant、backend、node_exporter、cAdvisor、postgres_exporter、redis_exporter、blackbox_exporter 均未发布宿主公网端口。

## 36. Monitoring Resource Consumption

最终 snapshot：Grafana 141.6 MiB、Prometheus 88.79 MiB、cAdvisor 54.2 MiB、Alertmanager 14.98 MiB、Blackbox 14.37 MiB、node_exporter 9.39 MiB、redis_exporter 8.75 MiB、postgres_exporter 8.74 MiB。所有值低于 hard limits。

持久卷：Prometheus 20 MiB、Grafana 50 MiB、Alertmanager 4 KiB。系统盘 27% used、约 29G available。当前没有监控导致的 memory pressure 或异常 TSDB growth 证据。

## 37. Files Created

Phase 3 新增的可复现文件：

- `backend/app/api/routes/prometheus.py`
- `deploy/production/monitoring/.env.example`
- `deploy/production/monitoring/compose.yml`
- `deploy/production/monitoring/prometheus.yml`
- `deploy/production/monitoring/alertmanager.yml`
- `deploy/production/monitoring/blackbox.yml`
- `deploy/production/monitoring/README.md`
- `deploy/production/monitoring/rules/{host,containers,database,qdrant,backend,rag,backup}.yml`
- `deploy/production/monitoring/grafana/provisioning/datasources/prometheus.yml`
- `deploy/production/monitoring/grafana/provisioning/dashboards/odirag.yml`
- 9 files under `deploy/production/monitoring/grafana/dashboards/`
- `deploy/production/monitoring/scripts/update-textfile-metrics.sh`
- `deploy/production/monitoring/systemd/odirag-monitoring-textfile.service`
- `deploy/production/monitoring/systemd/odirag-monitoring-textfile.timer`
- `deploy/production/scripts/measure-production-observability.py`
- `deploy/production/scripts/verify-alert-lifecycle.py`
- `runbooks/monitoring.md`
- `runbooks/alerting.md`
- `runbooks/incident-response.md`
- `PRODUCTION_PHASE_3_REPORT.md`

Runtime secret files 位于 `/etc/odirag/monitoring/`，不在 Git；报告仅校验其 mode/owner，不读取内容。

## 38. Files Modified

Phase 3 后端行为和测试的 scoped 修改：

- `backend/pyproject.toml`, `backend/requirements.lock`
- `backend/app/metrics.py`, `backend/app/main.py`, `backend/app/rate_limit.py`, `backend/app/runtime.py`
- `backend/app/api/routes/chat.py`
- `backend/app/llm/adapters.py`
- `backend/app/retrieval/engine.py`
- `backend/app/services/chat.py`
- `backend/tests/unit/test_metrics.py`
- `backend/tests/unit/test_core_api.py`
- `backend/tests/unit/test_chat_grounding.py`

仓库在 Phase 3 开始前已经包含 Phase 1/2、attachment 和 evaluation 的未提交修改；本阶段没有回滚、覆盖或盲目 stage 这些用户工作。

## 39. Commands Actually Executed

以下为实际执行的命令族；敏感参数和值不记录：

- `ssh rag-prod`、`sudo -n whoami/true`、`stat`、`ss -lnt`、`free`、`df`、`du`。
- `docker compose config/up/restart/ps/logs`、`docker ps/inspect/stats/volume/system df`。
- `curl` 对 backend health/metrics、Prometheus API、Grafana API、Alertmanager API、Blackbox/Qdrant endpoints 的内部请求。
- `promtool check config/rules`、`amtool check-config`。
- `systemctl daemon-reload/enable/start/status` 用于 textfile timer。
- PostgreSQL 只读 SQL、least-privilege monitor role setup、Qdrant read-only collection checks。
- `measure-production-observability.py` bounded no-write production measurement。
- `verify-alert-lifecycle.py` 两个白名单故障注入与自动恢复场景。
- `python -m pytest`、Ruff、mypy、`git diff --check`。

没有执行 `git add -A`、数据删除、volume 删除、collection 删除、Redis FLUSH、PostgreSQL DROP、新 crawl 或 bulk ingestion。

## 40. Git Diff Summary

Phase 3 scope 包含 13 个既有 tracked files 的修改和 33 个新 implementation/runbook files；本报告为第 34 个新文件。监控配置、backend instrumentation、验证脚本和 runbooks 均保持 unstaged/uncommitted。工作树整体仍包含 Phase 3 之前的 166 项既存修改/未跟踪文件，因此全仓 `git status` 不能视为 Phase 3 独占 diff。没有清理或 stage 不相关文件。

## 41. Temporary Test Resources Created / Removed

- node_exporter 与 backend 的受控停止均已恢复并现场验证 healthy/ready。
- 临时 lifecycle/measurement processes：0。
- `/tmp/odirag-phase3-*` transfer paths：0 remaining。
- 旧 `/etc/odirag/monitoring/postgres-exporter.env` 已移除；当前 exporter 使用 file secret。
- 临时 Qdrant collections：0。
- Prometheus 与 Alertmanager 当前 active alerts：0。
- Post-fault bounded RAG metric snapshot 在 Prometheus 完成 scrape 和独立 PromQL 取证后，已从 host textfile collector 与 backend `/tmp` 精确删除；当前 `job=node` RAG instant series 为空，历史 samples 由 Prometheus TSDB retention 保存。

## 42. Remaining Risks

1. 百分位只有 6 个有界样本，置信度有限；不能替代长期流量趋势或容量测试。
2. RAG/provider percentile evidence 来自生产容器内独立 no-write ASGI registry，经 textfile collector 进入 Prometheus；它不是运行中 backend process 的原生 RAG traffic。主 backend HTTP registry 已单独证明 live scrape，但需要后续自然生产流量积累长期 RAG series。
3. 单节点部署没有 Prometheus/Grafana/Alertmanager HA，主机故障会同时影响应用和本地监控。
4. Qdrant Python client 1.19 与 server 1.14 存在 minor version warning；本阶段操作成功，但应安排版本兼容收敛。
5. Grafana 曾在 160 MiB 限制下 OOM；256 MiB 后稳定，仍应观察 dashboard usage 增长。
6. host 上存在与 ODIRAG 无关的 `fwupd-refresh.service` failed 状态；未为获取绿色结果而 reset 或修改，需由主机维护窗口单独处理。
7. textfile operational metrics 依赖 systemd timer；collector success/staleness alerts 已提供，但仍需持续观察。

## 43. Remaining Blockers

- `ALERT_DELIVERY=BLOCKED`（仅 external channel）：没有用户授权的外部 notification credentials。内部 Prometheus -> Alertmanager pipeline 为 `PASS-LIVE`。
- `PUBLIC_EXTERNAL_UPTIME=BLOCKED`：Phase 5 尚未建立公开 HTTPS ingress，按边界要求不得为监控测试提前公开应用。

这两个明确延期项不阻止本阶段 `PHASE_3_OVERALL=PASS-LIVE`。

## 44. Phase 4 Recommendations

Phase 4 开始前建议以本报告和 runbooks 为入口，实施受控 CI/CD、镜像 registry、SBOM、provenance、release/rollback automation，并把 Phase 3 的 531-test、Ruff、mypy、Compose validation、Prometheus rule validation 纳入 gates。保持生产 monitoring 网络和 loopback exposure 不变；不要在 Phase 4 提前实施 DNS/TLS/public ingress。安排 Qdrant client/server minor version 对齐，并为 monitoring config 与 dashboards 增加发布前 schema/policy checks。外部通知渠道仅在用户提供已授权凭据后配置。

## Final Gate Table

| Gate | Status | Evidence summary |
| --- | --- | --- |
| HOST_METRICS | PASS-LIVE | node_exporter target UP，真实 host samples |
| CONTAINER_METRICS | PASS-LIVE | cAdvisor target UP，应用与监控容器 samples |
| POSTGRES_METRICS | PASS-LIVE | Dedicated monitor role，target UP，connections/size/deadlocks/WAL evidence |
| REDIS_METRICS | PASS-LIVE | target UP，memory/client/persistence evidence |
| QDRANT_METRICS | PASS-LIVE | Native metrics UP，活动/回滚 collection 821 points |
| BACKEND_METRICS | PASS-LIVE | Internal `/metrics` scraped，bounded labels，not public |
| RAG_METRICS | PASS-LIVE | Real no-write production-runtime sample, textfile scrape and stage histograms; source disclosed as `job=node` |
| PROVIDER_METRICS | PASS-LIVE | Bailian/Qdrant/Cohere/DeepSeek live success metrics from disclosed bounded sample |
| PROMETHEUS | PASS-LIVE | 10/10 targets UP，persistent TSDB，30/30 rules healthy |
| GRAFANA | PASS-LIVE | API/database/datasource healthy after restart |
| DASHBOARDS | PASS-LIVE | 9/9 provisioned after restart |
| LATENCY_PERCENTILES | PASS-LIVE | Real bounded sample，P50/P95/P99 queried with PromQL |
| ALERT_RULES | PASS-LIVE | 30 rules healthy，required categories present |
| ALERTMANAGER | PASS-LIVE | Internal endpoint/discovery/dedup/resolution verified |
| ALERT_DELIVERY | BLOCKED | External receiver credentials unavailable; internal delivery PASS-LIVE |
| INTERNAL_BLACKBOX_MONITORING | PASS-LIVE | Three private probes success=1 and HTTP 200 |
| FAULT_INJECTION | PASS-LIVE | HostDown and BackendDown controlled scenarios recovered |
| ALERT_FIRING | PASS-LIVE | Both scenarios reached genuine firing state |
| ALERT_RESOLUTION | PASS-LIVE | Both scenarios resolved after confirmed recovery |
| PRODUCTION_REGRESSION | PASS-LIVE | 8/8 app，8/8 monitoring，10/10 targets，bounded RAG retry 6/6 |
| DATA_INTEGRITY | PASS-LIVE | 182/821/60/69，no duplicates，Qdrant set equality |
| PUBLIC_EXTERNAL_UPTIME | BLOCKED | Deferred until Phase 5 public HTTPS ingress exists |
| PHASE_3_OVERALL | PASS-LIVE | All in-scope critical gates have live evidence |

## Final Operational State

- `PHASE_3_OVERALL=PASS-LIVE`
- Temporary production sudo rule `/etc/sudoers.d/99-rag-deploy-production` remains intentionally present with mode 0440 and owner root:root, per user instruction. It was not revoked.
- Phase 4 not started.
- Phase 5 not started.
