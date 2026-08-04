# ODIRAG Production Acceptance Checklist

本文是部署到真实环境前的执行清单，不是模拟成功清单。每一项都必须在目标环境执行并保存原始输出。本机 Docker Desktop/Compose 的 development 栈已完成一轮真实本地验收，但没有生产 secret、远程 provider 凭据或代表性真实抓取，因此本文件中的生产 provider 项目仍为 UNVERIFIED。

## 证据规则

- PASS-LIVE：命令在目标 PostgreSQL/Redis/Qdrant/worker/provider/入口上实际执行，输出与预期一致。
- PASS-FIXTURE：只使用 SQLite、内存实现、确定性模型、MockTransport 或 Playwright route fixture；不能替代 live acceptance。
- BLOCKED：前置依赖或凭据缺失，不能推断成功。
- FAIL：命令已执行但结果不符合预期。

每项保存命令、UTC 时间、镜像 digest、配置版本、脱敏日志和结果。不要把 token、密码、Authorization header 或完整响应中的敏感字段提交到仓库。

## 0. 前置准备

在部署机安装 Docker Engine、Docker Compose v2、PowerShell 7、Python 3.12+、Node 22+ 和 psql（或使用容器内客户端）。将 .env.example 复制为 .env，替换所有开发默认值；生产环境必须使用 ODIRAG_ENVIRONMENT=production、随机的 ODIRAG_JWT_SECRET_KEY、ODIRAG_ADMIN_PASSWORD_HASH，不能设置明文 ODIRAG_ADMIN_PASSWORD。

~~~powershell
$ErrorActionPreference = 'Stop'
docker version
docker compose version
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose model is invalid' }
~~~

预期：Docker/Compose 版本可打印，docker compose config --quiet 无输出且退出码为 0。若 Compose 输出 warning，先修复变量或镜像配置再继续。

## 1. 启动完整栈

~~~powershell
docker compose --profile ui --profile async up -d --build
docker compose ps --all
docker compose ps --format json | ConvertFrom-Json | Format-Table
docker compose images
docker compose ps --all > acceptance-compose-ps.txt
docker compose logs --no-color --since 10m > acceptance-compose-logs.txt
~~~

预期服务：postgres、redis、qdrant、backend、frontend、nginx、worker、scheduler 均为 running，并且 health 为 healthy。保存镜像 tag/digest、Compose 状态和最近 10 分钟脱敏日志。

## 2. PostgreSQL

~~~powershell
$pgUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
$pgDb = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
docker compose exec -T postgres pg_isready -U $pgUser -d $pgDb
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -Atc "SELECT current_database(), current_user"
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "SELECT count(*) AS sources FROM sources; SELECT count(*) AS documents FROM documents;"
~~~

预期：pg_isready 报 accepting connections；SQL 成功并返回数据库/用户；业务查询返回整数且无 relation/permission 错误。继续核对 Phase 16 表：

~~~powershell
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -Atc "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('source_discovery_runs','source_candidates','source_candidate_columns','source_discovery_events') ORDER BY tablename"
~~~

预期恰好返回四张表。若使用受管 PostgreSQL，另执行备份、恢复和连接池耗尽演练；这些不由 Compose 默认配置证明。

## 3. Alembic

~~~powershell
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
docker compose exec -T backend alembic check
~~~

预期：current 和 heads 都指向 `0006_coze_task_operations`，并标记 (head)；alembic check 无待生成迁移且退出码为 0。

使用专用验收数据库验证全链路迁移（不要在生产业务库直接 downgrade）：

~~~powershell
$acceptanceDb = 'odirag_acceptance_migration'
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $acceptanceDb;"
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "CREATE DATABASE $acceptanceDb;"
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; alembic upgrade head'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; alembic downgrade 0003_crawl_reliability'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; alembic upgrade head'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; alembic current'
~~~

预期：upgrade、downgrade、再 upgrade 都退出 0，最终 `0006_coze_task_operations (head)`。完成后清理专用数据库或按组织保留审计证据。

## 4. Redis

~~~powershell
docker compose exec -T redis redis-cli ping
docker compose exec -T redis redis-cli SET odirag:acceptance:probe ok EX 60
docker compose exec -T redis redis-cli GET odirag:acceptance:probe
docker compose exec -T redis redis-cli DEL odirag:acceptance:probe
~~~

预期依次为 PONG、OK、ok、1。随后从 backend 容器确认应用 Redis URL 可达：

~~~powershell
docker compose exec -T backend python -c "import asyncio,os; from redis.asyncio import Redis; print(asyncio.run(Redis.from_url(os.environ['ODIRAG_REDIS_URL']).ping()))"
~~~

预期打印 True。还需确认 broker、result backend、embedding cache 使用隔离 Redis DB/ACL；仅一次 PING 不证明故障转移或持久化恢复。

## 5. Qdrant

~~~powershell
$qdrant = 'http://127.0.0.1:6333'
Invoke-RestMethod "$qdrant/healthz"
Invoke-RestMethod "$qdrant/collections" | ConvertTo-Json -Depth 8
~~~

预期：health endpoint 返回成功；collections 响应可解析。完成一次真实 reindex 后检查：

~~~powershell
$collection = if ($env:ODIRAG_QDRANT_COLLECTION) { $env:ODIRAG_QDRANT_COLLECTION } else { 'odirag_chunks' }
$info = Invoke-RestMethod "$qdrant/collections/$collection"
$info.result.status
$info.result.config.params.vectors.size
$info.result.points_count
~~~

预期：status 为 green（或目标版本等价健康状态），vector size 等于 ODIRAG_EMBEDDING_DIMENSIONS，points_count 与已索引 chunk 数一致且大于零。删除/重解析后再次检查 points_count 下降，不能只检查数据库行。

## 6. Worker

~~~powershell
docker compose exec -T worker celery -A app.tasks.celery_app:celery_app inspect ping --timeout 10
docker compose exec -T backend python -c "from app.tasks.celery_app import ping; r=ping.delay(); print(r.get(timeout=30, propagate=True))"
~~~

预期：inspect 输出 worker 的 pong；第二条输出 {'status': 'healthy', 'service': 'odirag-worker'}（或等价 JSON），证明任务确实经过 broker 被 worker 执行。再创建一个 queued crawl task 和一个 queued source-discovery run，确认状态从 pending 到 running 再到完成/审批等待，并在 broker 不可用时确认任务被持久化为 failed 且可 retry。

## 7. Scheduler

~~~powershell
docker compose exec -T scheduler sh -c 'test -s /tmp/celerybeat.pid'
docker compose logs --no-color --since 5m scheduler
~~~

预期：PID 文件存在且进程仍在；日志包含 beat 启动和调度信息。至少观察到 refresh-monitoring-alerts（300 秒）和 recover-crawl-tasks（60 秒）各执行一次，不能只凭容器 running 判定 scheduler 有效。

## 8. Nginx 与前端

~~~powershell
$base = 'http://127.0.0.1:8080'
(Invoke-WebRequest "$base/healthz").StatusCode
(Invoke-WebRequest "$base/").StatusCode
(Invoke-WebRequest "$base/api/system/health").StatusCode
~~~

预期三个状态码都是 200；/healthz body 为 ok，/ 返回前端 HTML，health JSON 的 database、redis、qdrant 状态与目标环境事实一致，不得被 demo 值覆盖。保存响应头并确认 X-Content-Type-Options、X-Frame-Options、Referrer-Policy 存在。

在 frontend/ 执行：

~~~powershell
npm ci
npx playwright install chromium
npm run lint
npm run type-check
npm test
npm run build
npm run test:e2e
~~~

预期：lint/type-check/test/build 全部退出 0；fixture Playwright 用例全部通过，live-stack.spec.ts 在未设置 E2E_LIVE=1 时明确 skipped。fixture 通过只证明浏览器 API 契约，不证明生产依赖。

真实栈浏览器门禁：

~~~powershell
$env:E2E_LIVE = '1'
$env:E2E_BASE_URL = 'https://<real-odirag-host>'
$env:E2E_USERNAME = '<acceptance-user>'
$env:E2E_PASSWORD = '<acceptance-password>'
$env:E2E_QUERY = '企业研发投入有哪些支持措施？'
npm run test:e2e -- e2e/live-stack.spec.ts
~~~

预期：live 用例通过且没有 request interception；登录、来源、文档、带真实引用的聊天和监控均可达。失败时保留 trace，不要改成 fixture 以“修复”结果。

## 9. Auth 与核心 API 烟测

~~~powershell
$login = Invoke-RestMethod "$base/api/auth/login" -Method Post -ContentType 'application/json' -Body (@{ username = $env:E2E_USERNAME; password = $env:E2E_PASSWORD } | ConvertTo-Json)
$token = $login.access_token
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "$base/api/auth/me" -Headers $headers
Invoke-RestMethod "$base/api/sources" -Headers $headers
Invoke-RestMethod "$base/api/documents?limit=1" -Headers $headers
~~~

预期：login 返回 access/refresh token；me 返回当前管理员；sources/documents 返回真实数据库数据。不要在终端或日志打印 $token。

## 10. Coze

先在受控 shell 注入真实凭据，重启 backend；不要在仓库 .env.example 填入 token：

~~~powershell
$env:ODIRAG_LLM_PROVIDER = 'coze'
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:ODIRAG_COZE_BASE_URL = 'https://api.coze.com'
$env:ODIRAG_COZE_API_TOKEN = '<real-token>'
$env:ODIRAG_COZE_BOT_ID = '<real-bot-id>'
docker compose up -d --force-recreate backend worker
~~~

用一个真实待审核文档执行 POST /api/reviews/{document_id}/run，再执行 POST /api/chat。预期：Coze 返回符合 Pydantic 严格 JSON schema 的真实 review/answer，chat trace 的 model_name 为配置模型，引用仍来自已存储 chunk；缺 token 时必须是结构化 503，不能返回模拟答案。Coze Chat v3 的异步/消息读取语义必须以目标账户实际响应确认；当前适配器只做了协议夹具测试，未宣称 live 通过。参考：[Coze Chat v3](https://www.coze.com/open/docs/developer_guides/chat_v3)。

### Coze 栏目批量抓取部署

在本机未提交的 `.env` 中配置 `COZE_ENABLED=true`、`COZE_BATCH_API_URL`、
`COZE_API_TOKEN`、`COZE_DEFAULT_CONTRACT=batch_crawl`、`COZE_TIMEOUT_SECONDS=90` 和
`COZE_MAX_RETRIES=2`。旧单篇部署如需验证，使用独立的 `COZE_LEGACY_API_URL`；不要增加
`workflow_id` 或 Coze 远端轮询配置。然后执行：

~~~powershell
docker compose --profile async --profile ui up -d --build
python scripts/live_accept_coze_batch.py --source-column-id <真实已启用栏目ID>
~~~

预期：脚本通过认证 API 创建真实 queued Coze/batch_crawl 任务，固定 `max_articles=5`、`max_pages=1`，
worker 完成一次 `batch_crawl` invocation；退出码为 0，单行 JSON 中
`status=live_batch_verified`，并给出 `success_count`、`accepted_count`、`rejected_count`、
`pending_review_count`、`failed_count`、`database_document_count`、`chunk_count` 和
`qdrant_point_count`。后四项来自任务持久化结果和 Qdrant `count(exact=true)`，不能用数据库
`index_status` 冒充。脚本不输出 token、部署 URL、header 或 raw response。未配置新批量 URL 时退出码必须为 2，
`status=batch_workflow_not_published`；这不是 Live 成功。节点级施工步骤和十组控制台用例见
`docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md`。

## 11. Embedding provider

~~~powershell
$env:ODIRAG_EMBEDDING_PROVIDER = 'remote'
$env:ODIRAG_EMBEDDING_BASE_URL = 'https://<provider-base>/v1'
$env:ODIRAG_EMBEDDING_API_KEY = '<real-key>'
$env:ODIRAG_EMBEDDING_MODEL = '<real-model>'
$env:ODIRAG_EMBEDDING_DIMENSIONS = '<provider-dimension>'
docker compose up -d --force-recreate backend worker
$doc = Invoke-RestMethod "$base/api/documents?final_status=approved&limit=1" -Headers $headers | Select-Object -First 1
$reindex = Invoke-RestMethod "$base/api/documents/$($doc.id)/reindex" -Method Post -Headers $headers
$reindex.embedding_model
$reindex.embedding_version
$reindex.chunk_count
$reindex.vector_point_ids.Count
~~~

预期：provider 实际返回与输入数量相同的向量；维度与 Qdrant collection 一致；响应中的 model/version 是配置值；Qdrant points 和 Redis cache 可观察到对应写入。无 key、超时、维度不匹配必须结构化失败并清理部分写入。

## 12. Rerank provider

~~~powershell
$env:ODIRAG_RERANK_PROVIDER = 'remote'
$env:ODIRAG_RERANK_BASE_URL = 'https://<rerank-provider-base>'
$env:ODIRAG_RERANK_API_KEY = '<real-key>'
$env:ODIRAG_RERANK_MODEL = '<real-model>'
docker compose up -d --force-recreate backend
$debug = Invoke-RestMethod "$base/api/search/debug" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入支持措施'; mode = 'hybrid+rerank' } | ConvertTo-Json)
$debug.rerank_results.Count
$debug.warnings
~~~

预期：rerank_results.Count 大于零，index 在输入范围内且按 provider 分数排序；warnings 不包含 rerank_provider_disabled 或 provider_unavailable。没有 rerank 凭据时只能显式使用 none 并接受降级警告。

## 13. Direct LLM provider

~~~powershell
$env:ODIRAG_LLM_PROVIDER = 'direct'
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:ODIRAG_DIRECT_LLM_BASE_URL = 'https://<openai-compatible-base>/v1'
$env:ODIRAG_DIRECT_LLM_API_KEY = '<real-key>'
$env:ODIRAG_DIRECT_LLM_MODEL = '<real-model>'
docker compose up -d --force-recreate backend worker
$chat = Invoke-RestMethod "$base/api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入有哪些支持措施？' } | ConvertTo-Json)
$trace = Invoke-RestMethod "$base/api/chat/traces/$($chat.trace_id)" -Headers $headers
$trace.model_name
$trace.token_usage_json
$trace.cost
~~~

预期：answer 由真实 provider 生成但只能引用 retrieval 返回的 chunk；trace model 等于配置模型，token usage/cost 为 provider 真实遥测或明确的 not_available，不得伪造为零。当前代码对 extractive/deterministic demo 的零成本是诚实的；真实 LLM token/cost 仍是生产风险项。

## 14. Brave source discovery / Phase 16

~~~powershell
$env:ODIRAG_SOURCE_DISCOVERY_PROVIDER = 'brave'
$env:ODIRAG_SOURCE_DISCOVERY_API_KEY = '<real-brave-key>'
$env:ODIRAG_SOURCE_DISCOVERY_SEARCH_URL = 'https://api.search.brave.com/res/v1/web/search'
docker compose up -d --force-recreate backend worker
$run = Invoke-RestMethod "$base/api/source-discovery/runs" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ topic = '企业研发投入'; region = '四川'; required_source_count = 1; required_document_count = 3; execution_mode = 'inline' } | ConvertTo-Json)
Invoke-RestMethod "$base/api/source-discovery/runs/$($run.id)/events" -Headers $headers
~~~

预期事件顺序包含：content_gap_detection → candidate_discovery → official_status_validation → column_discovery → trial_crawl → quality_scoring → manual_approval → source_activation。候选必须先是 pending_approval，未经管理员 approve 的 activate 必须返回 409；批准后 activate 才能创建 enabled Source 和 enabled SourceColumn。Brave API 的真实响应/配额要单独记录；Bing Search API 已在 2025-08-11 退役，不能把旧 Bing endpoint 当作验收路径（见 [Microsoft retirement notice](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement) 和 [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get)）。

## 15. 结束条件与当前结论

只有 PostgreSQL、Redis、Qdrant、worker、scheduler、Nginx、frontend、Alembic 和所选真实 provider 全部 PASS-LIVE，且日志/trace/备份恢复证据已归档，才可把部署标为生产接受。

### 本机 development 栈证据（2026-08-04）

以下结果是真实本地 Compose 运行结果，标记为 `VERIFIED-LOCAL`，不能替代目标生产环境的 `PASS-LIVE`：

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| Compose 服务 | 8 个服务均 healthy：backend、frontend、postgres、redis、qdrant、worker、scheduler、nginx | development 配置；未证明生产 secret/TLS/镜像 provenance |
| PostgreSQL | `pg_isready` accepting connections；身份/业务计数查询成功；4 张 Phase16 表存在 | 未执行生产备份恢复、连接池耗尽和专用 PostgreSQL downgrade |
| Redis | PONG、临时键 SET/GET/DEL、backend ping=True | 未证明 ACL、故障转移和持久化恢复 |
| Qdrant | `/healthz` 成功；当前 collection 数为 0 | 没有成功抓取/索引文档，未证明 collection schema、points 删除补偿和备份 |
| worker/scheduler | worker inspect ping 与 `ping.delay()` 成功；日志观察到 recovery/monitoring 调度 | 未执行真实 queued crawl/source-discovery 完成和故障恢复演练 |
| Nginx/frontend | `/healthz`、`/`、`/api/system/health` 均 200；安全响应头存在 | 未执行 HTTPS/live Playwright 和生产浏览器门禁 |
| Alembic | current/heads 为 `0006_coze_task_operations (head)`；`alembic check` 无新 upgrade operations | 未执行生产数据库 downgrade/backup/restore |
| scsia.org | 浏览器可读；backend DNS `198.18.0.208` 被 SSRF guard 拒绝；最新任务失败、0 文档、接口 422 | 不是 live crawl 成功；需要正常公网 DNS/出口及图片/OCR 抽取验收 |

因此当前结论仍为 **NOT ACCEPTED / EXTERNAL ACCEPTANCE REQUIRED**。剩余生产门禁是：真实 Brave/Coze/Direct LLM/embedding/rerank 凭据与错误/成本证据、至少 10 篇真实官方站点抓取、代表性评测与负载、备份恢复、依赖扫描、Git checkpoint 和 live Playwright。
