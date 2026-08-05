# ODIRAG Production Acceptance Checklist

本文是部署到真实环境前的执行清单，不是模拟成功清单。最后审阅：2026-08-05。每一项都必须在目标环境执行并保存原始输出。本机 WSL2/Docker Desktop 已无损恢复，当前 Compose development 栈的八个服务、PostgreSQL/Alembic、Redis、Qdrant health、worker、scheduler、Nginx 1.30.4、frontend、8080 API 和 acceptance-summary 已通过真实本地验收。当前镜像仍未 fresh rebuild/Scout/SBOM，生产 secret、远程 provider 凭据、真实索引/Qdrant points 和代表性真实抓取也仍未验收。

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
docker compose build backend
docker compose build frontend
docker compose --profile ui --profile async up -d --no-build
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

### PostgreSQL 备份/恢复演练（隔离恢复库）

以下命令只创建并删除一个带时间戳的恢复库，不向业务库执行 `restore` 或 `downgrade`：

~~~powershell
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$backupDir = Join-Path $PWD "artifacts\acceptance\$stamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$containerDump = "/tmp/odirag-acceptance-$stamp.dump"
$restoreDb = "odirag_acceptance_restore_$stamp"
if ($restoreDb -notmatch '^odirag_acceptance_restore_\d{14}$') { throw 'Unsafe restore database name' }

$pgUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
$pgDb = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
docker compose exec -T postgres pg_dump -U $pgUser -d $pgDb -Fc --no-owner --no-privileges -f $containerDump
docker compose cp "postgres:$containerDump" $backupDir
$dumpPath = Join-Path $backupDir ([IO.Path]::GetFileName($containerDump))
if (-not (Test-Path -LiteralPath $dumpPath) -or (Get-Item -LiteralPath $dumpPath).Length -lt 1024) {
  throw 'PostgreSQL backup file was not copied or is implausibly small'
}
Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath
docker compose exec -T postgres pg_restore -l $containerDump | Select-Object -First 20

docker compose exec -T postgres createdb -U $pgUser $restoreDb
docker compose exec -T postgres pg_restore -U $pgUser -d $restoreDb --exit-on-error --no-owner --no-privileges $containerDump
$countSql = "SELECT 'sources', count(*) FROM sources UNION ALL SELECT 'source_columns', count(*) FROM source_columns UNION ALL SELECT 'source_discovery_runs', count(*) FROM source_discovery_runs UNION ALL SELECT 'source_candidates', count(*) FROM source_candidates UNION ALL SELECT 'source_candidate_columns', count(*) FROM source_candidate_columns UNION ALL SELECT 'source_discovery_events', count(*) FROM source_discovery_events UNION ALL SELECT 'crawl_tasks', count(*) FROM crawl_tasks UNION ALL SELECT 'coze_invocations', count(*) FROM coze_invocations UNION ALL SELECT 'documents', count(*) FROM documents ORDER BY 1"
$sourceCounts = @(docker compose exec -T postgres psql -U $pgUser -d $pgDb -At -v ON_ERROR_STOP=1 -c $countSql)
$restoreCounts = @(docker compose exec -T postgres psql -U $pgUser -d $restoreDb -At -v ON_ERROR_STOP=1 -c $countSql)
if (Compare-Object $sourceCounts $restoreCounts) { throw 'Restored PostgreSQL table counts differ from source' }

docker compose exec -T postgres dropdb -U $pgUser --if-exists $restoreDb
docker compose exec -T postgres rm -f $containerDump
~~~

预期：`pg_dump`、`pg_restore`、恢复库计数对比全部退出 0；备份文件及 SHA-256 留档。当前仓库没有自动备份调度器，恢复演练仍是人工生产门禁。

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

预期打印 True。继续验证应用使用共享 Redis 限流器，而不是进程内 fallback：

~~~powershell
docker compose exec -T backend python -c "from app.config import Settings; print(Settings().rate_limit_backend)"
docker compose exec -T backend python -c "from app.config import Settings; s=Settings(); print(s.trusted_proxy_ips)"
$base = 'http://127.0.0.1:8080'
curl.exe -sS -D acceptance-rate-limit-headers.txt -o NUL "$base/api/system/health"
Get-Content acceptance-rate-limit-headers.txt | Select-String 'x-ratelimit-limit|x-ratelimit-remaining|x-ratelimit-reset'
docker compose exec -T redis redis-cli --scan --pattern 'odirag:ratelimit:*'
$spoof = '203.0.113.250'
curl.exe -sS -H "X-Forwarded-For: $spoof" -o NUL "$base/api/system/health"
if (@(docker compose exec -T redis redis-cli --scan --pattern "*$spoof*").Count -ne 0) {
  throw 'Client-supplied X-Forwarded-For created a limiter bucket'
}
~~~

预期第一条为 `redis`，响应同时包含三类 `X-RateLimit-*` header，Redis scan 至少返回一个
`odirag:ratelimit:<window>:<bucket>:<profile>:<identity>` key。staging/production 配置若选择 `memory`
必须在启动时失败，不能以单实例假设绕过共享限流。

只在隔离验收环境执行 fail-closed 演练：停止 Redis 后请求受限 API，预期 HTTP 503 且错误码为
`RATE_LIMIT_BACKEND_UNAVAILABLE`；恢复 Redis 后请求恢复成功。不要在承载业务流量的生产实例直接停止 Redis。

还需确认 broker、result backend、embedding cache 使用隔离 Redis DB/ACL；一次 PING 和一次计数写入仍不证明故障转移或持久化恢复。

## 5. Qdrant

~~~powershell
$qdrant = 'http://127.0.0.1:6333'
Invoke-RestMethod "$qdrant/healthz"
Invoke-RestMethod "$qdrant/collections" | ConvertTo-Json -Depth 8
~~~

预期：health endpoint 返回成功；collections 响应可解析。完成一次真实 reindex 后检查：

~~~powershell
$collection = docker compose exec -T backend python -c "from app.config import get_settings; print(get_settings().qdrant_collection)"
$collection = $collection.Trim()
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

用一个已启用、已通过来源验收的栏目执行真实 queued crawl（不要把 `inline` 当作 worker 证据）：

~~~powershell
$apiBase = 'http://127.0.0.1:8080/api'
$columnId = <真实已启用栏目ID>
$queued = Invoke-RestMethod "$apiBase/crawl-tasks" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  source_column_id = $columnId
  task_type = 'incremental'
  trigger_type = 'manual'
  execution_mode = 'queued'
  provider = 'coze'
  contract_mode = 'batch_crawl'
  provider_contract = 'batch_crawl'
  max_articles = 1
  max_pages = 1
} | ConvertTo-Json)
$deadline = (Get-Date).AddMinutes(5)
do {
  Start-Sleep -Seconds 2
  $queued = Invoke-RestMethod "$apiBase/crawl-tasks/$($queued.id)" -Headers $headers
} while ($queued.status -in @('pending','queued','running','calling_coze','coze_running','normalizing','saving_documents') -and (Get-Date) -lt $deadline)
if ($queued.status -notin @('completed','waiting_review','partial_failed')) {
  throw "Queued crawl did not reach an accepted terminal state: $($queued.status)"
}
if ($queued.provider -ne 'coze' -or $queued.contract_mode -ne 'batch_crawl') { throw 'Worker used the wrong provider contract' }
~~~

预期：任务曾进入 queued/running，最终为 `completed`、`waiting_review` 或明确的 `partial_failed`；`provider` 为 `coze`、`contract_mode` 为 `batch_crawl`，并且 invocation、失败 URL 和持久化计数可由后续接口核对。

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

容器用户边界也要留证：

~~~powershell
docker compose exec -T backend id -u
docker compose exec -T frontend id -u
docker compose exec -T nginx id -u
~~~

预期：backend 输出 `10001`。当前 frontend/reverse-proxy Nginx 基础镜像的 master 进程可能输出 `0`（worker 会降权）；这只能记录为残余 hardening 风险，不能把它写成“所有容器均 non-root”或生产通过。

在 frontend/ 执行：

~~~powershell
npm ci
npx playwright install chromium
npm run lint
npm run type-check
npm test
npm run build
npm audit --omit=dev
npm audit
npm ls --all
npm run test:e2e
~~~

预期：lint/type-check/test/build 全部退出 0；两次 audit 均为 0 high/critical（发布门禁建议所有级别均为 0），依赖树无 invalid/extraneous 必需依赖；fixture Playwright 用例全部通过，live-stack.spec.ts 在未设置 E2E_LIVE=1 时明确 skipped。fixture 通过只证明浏览器 API 契约，不证明生产依赖。

在仓库根目录执行 Python 依赖一致性检查。先单独构建两个 builder stage，再对 Compose
使用的全部运行时镜像与 builder 镜像生成 SBOM 和 critical/high CVE 报告：

~~~powershell
pip --python .\backend\.venv check
docker build --file Dockerfile.backend --target builder --tag odirag/backend-builder:acceptance .
docker build --file Dockerfile.frontend --target builder --tag odirag/frontend-builder:acceptance .
$scanDir = Join-Path $PWD 'artifacts\acceptance\image-scan'
New-Item -ItemType Directory -Force -Path $scanDir | Out-Null
$images = @(
  @(docker compose config --images)
  'odirag/backend-builder:acceptance'
  'odirag/frontend-builder:acceptance'
) | Sort-Object -Unique
foreach ($image in $images) {
  $safeName = $image -replace '[^A-Za-z0-9._-]', '_'
  $digestPath = Join-Path $scanDir "$safeName.digest.txt"
  docker image inspect $image --format '{{.Id}} {{json .RepoDigests}}' |
    Set-Content -LiteralPath $digestPath
  if (-not (Test-Path -LiteralPath $digestPath) -or (Get-Item -LiteralPath $digestPath).Length -lt 20) {
    throw "Image ID/digest evidence is missing for $image"
  }
  $sbomPath = Join-Path $scanDir "$safeName.spdx.json"
  docker scout sbom "local://$image" --format spdx `
    --output $sbomPath
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sbomPath) -or (Get-Item -LiteralPath $sbomPath).Length -lt 100) {
    throw "SBOM generation failed or produced an empty report for $image"
  }
  $cvePath = Join-Path $scanDir "$safeName.cves.md"
  docker scout cves "local://$image" --multi-stage --only-severity critical,high `
    --format markdown --output $cvePath --exit-code
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $cvePath) -or (Get-Item -LiteralPath $cvePath).Length -lt 1) {
    throw "Unapproved critical/high CVE or scan failure: $image"
  }
}
Get-ChildItem -LiteralPath $scanDir | Select-Object Name,Length
~~~

预期：pip 报告 `No broken requirements found`；backend、frontend、PostgreSQL、Redis、Qdrant、
reverse-proxy Nginx 以及 Python/Node builder 全部产生非空 SPDX SBOM、镜像 ID/digest 记录和 CVE
报告，且没有未批准的 critical/high CVE。`local://` 确保扫描本机刚构建或刚拉取的镜像，而不是
同名 registry 镜像。发布到 registry 后还必须把不可变 RepoDigest 写入部署清单；只有本地 image ID
不能满足发布 provenance 门禁。若扫描器需要联网更新漏洞库，必须保留扫描时间、数据库版本、镜像
digest 和例外审批，不能以“命令不可用”记为通过。

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
$env:COZE_API_TOKEN = '<real-token>'
$env:ODIRAG_COZE_BOT_ID = '<real-bot-id>'
docker compose up -d --force-recreate backend worker
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.coze_base_url, bool(s.coze_api_token), s.coze_bot_id)"
~~~

用一个真实待审核文档执行 POST /api/reviews/{document_id}/run，再执行 POST /api/chat。预期：Coze 返回符合 Pydantic 严格 JSON schema 的真实 review/answer，chat trace 的 model_name 为配置模型，引用仍来自已存储 chunk；缺 token 时必须是结构化 503，不能返回模拟答案。Coze Chat v3 的异步/消息读取语义必须以目标账户实际响应确认；当前适配器只做了协议夹具测试，未宣称 live 通过。参考：[Coze Chat v3](https://www.coze.com/open/docs/developer_guides/chat_v3)。

### Coze 栏目批量抓取部署

在本机未提交的 `.env` 中配置 `COZE_ENABLED=true`、`COZE_BATCH_API_URL`、
`COZE_API_TOKEN`、`COZE_DEFAULT_CONTRACT=batch_crawl`、`COZE_TIMEOUT_SECONDS=90` 和
`COZE_MAX_RETRIES=2`。旧单篇部署如需验证，使用独立的 `COZE_LEGACY_API_URL`；不要增加
`workflow_id` 或 Coze 远端轮询配置。然后执行：

先设置 `ODIRAG_SOURCE_COLUMN_ID` 为一个已人工批准并启用的真实栏目 ID；以下命令会在变量为空时立即失败：

~~~powershell
if ([string]::IsNullOrWhiteSpace($env:ODIRAG_SOURCE_COLUMN_ID)) {
  throw 'ODIRAG_SOURCE_COLUMN_ID must reference a real enabled source column'
}
docker compose build backend
docker compose build frontend
docker compose --profile async --profile ui up -d --no-build
python scripts/live_accept_coze_batch.py --source-column-id $env:ODIRAG_SOURCE_COLUMN_ID
~~~

预期：脚本通过认证 API 创建真实 queued Coze/batch_crawl 任务，固定 `max_articles=5`、`max_pages=1`，
worker 完成一次 `batch_crawl` invocation；退出码为 0，单行 JSON 中
`status=live_batch_verified`，并给出 `success_count`、`accepted_count`、`rejected_count`、
`pending_review_count`、`failed_count`、`database_document_count`、`chunk_count` 和
`qdrant_point_count`。后四项来自任务持久化结果和 Qdrant `count(exact=true)`，不能用数据库
`index_status` 冒充。脚本不输出 token、部署 URL、header 或 raw response。未配置新批量 URL 时退出码必须为 2，
`status=batch_workflow_not_published`；这不是 Live 成功。节点级施工步骤和十组控制台用例见
`docs/COZE_BATCH_WORKFLOW_BUILD_SPEC.md`。

栏目任务只能使用 `batch_crawl`。向 `POST /api/crawl-tasks` 提交
`provider=coze, contract_mode=legacy_single_article` 的预期结果是 HTTP 422、错误码
`COZE_LEGACY_SINGLE_ARTICLE_ONLY`；旧单篇部署只通过来源连通性/单篇兼容回归验证，不能创建栏目任务，
也不能用于证明批量抓取成功。

## 11. Embedding provider

~~~powershell
$env:ODIRAG_EMBEDDING_PROVIDER = 'remote'
$env:ODIRAG_EMBEDDING_BASE_URL = 'https://<provider-base>/v1'
$env:ODIRAG_EMBEDDING_API_KEY = '<real-key>'
$env:ODIRAG_EMBEDDING_MODEL = '<real-model>'
$env:ODIRAG_EMBEDDING_DIMENSIONS = '<provider-dimension>'
docker compose up -d --force-recreate backend worker
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.embedding_provider, s.embedding_base_url, bool(s.embedding_api_key), s.embedding_model, s.embedding_dimensions)"
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
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.rerank_provider, s.rerank_base_url, bool(s.rerank_api_key), s.rerank_model)"
$debug = Invoke-RestMethod "$base/api/search/debug" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入支持措施'; mode = 'hybrid_rerank' } | ConvertTo-Json)
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
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.direct_llm_base_url, bool(s.direct_llm_api_key), s.direct_llm_model)"
$chat = Invoke-RestMethod "$base/api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入有哪些支持措施？' } | ConvertTo-Json)
$trace = Invoke-RestMethod "$base/api/chat/traces/$($chat.trace_id)" -Headers $headers
$trace.model_name
$trace.token_usage_json
$trace.cost
~~~

预期：answer 由真实 provider 生成但只能引用 retrieval 返回的 chunk；trace model 等于配置模型。若响应含 `usage`/`cost`，`token_usage_json` 应出现规范化 token 字段且 `cost_measurement=provider_reported`；若 provider 不返回价格，必须出现 `cost_measurement=not_available`，cost=0 仅表示未知，不得解释为免费。当前 extractive/deterministic demo 的 zero-cost 标记是诚实降级；真实 LLM token/cost 仍需 live 验收。

## 14. Brave source discovery / Phase 16

~~~powershell
$env:ODIRAG_SOURCE_DISCOVERY_PROVIDER = 'brave'
$env:ODIRAG_SOURCE_DISCOVERY_API_KEY = '<real-brave-key>'
$env:ODIRAG_SOURCE_DISCOVERY_SEARCH_URL = 'https://api.search.brave.com/res/v1/web/search'
$api = "$base/api"
docker compose build backend
docker compose --profile async up -d --no-build backend worker scheduler
$discoveryConfig = docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.source_discovery_provider, s.source_discovery_search_url, bool(s.source_discovery_api_key))"
if ($discoveryConfig -notmatch '^brave ') { throw 'Brave source discovery is not configured' }

$run = Invoke-RestMethod "$api/source-discovery/runs" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  topic = '企业研发投入支持政策'
  region = '四川'
  organization_level = 'provincial'
  required_source_count = 1
  required_document_count = 3
  max_candidates = 10
  execution_mode = 'queued'
} | ConvertTo-Json)
$deadline = (Get-Date).AddMinutes(5)
do {
  Start-Sleep -Seconds 2
  $run = Invoke-RestMethod "$api/source-discovery/runs/$($run.id)" -Headers $headers
} while ($run.status -in @('pending','running') -and (Get-Date) -lt $deadline)
if ($run.status -ne 'awaiting_approval') { throw "Discovery did not reach manual approval: $($run.status)" }

$candidates = @(Invoke-RestMethod "$api/source-discovery/runs/$($run.id)/candidates" -Headers $headers)
$candidate = @($candidates | Where-Object { $_.status -eq 'pending_approval' } | Sort-Object quality_score -Descending | Select-Object -First 1)[0]
if ($null -eq $candidate) { throw 'No pending_approval candidate was returned' }
if ($candidate.official_status -ne 'official' -or $candidate.quality_score -lt 0.65) { throw 'Candidate failed official/quality threshold' }
if (@($candidate.columns | Where-Object { $_.status -eq 'trial_crawled' }).Count -lt 1) { throw 'No trial-crawled column' }

# Approval is an explicit gate: activation before approval must fail with 409.
$blocked = Invoke-WebRequest "$api/source-discovery/candidates/$($candidate.id)/activate" -Method Post -Headers $headers -SkipHttpErrorCheck
$blockedError = $blocked.Content | ConvertFrom-Json
if ($blocked.StatusCode -ne 409 -or $blockedError.error.code -ne 'INVALID_SOURCE_CANDIDATE_STATE') { throw 'Expected 409 INVALID_SOURCE_CANDIDATE_STATE' }
$approved = Invoke-RestMethod "$api/source-discovery/candidates/$($candidate.id)/approve" -Method Post -Headers $headers
if ($approved.status -ne 'approved' -or [string]::IsNullOrWhiteSpace($approved.approved_by)) { throw 'Manual approval was not recorded' }
$activated = Invoke-RestMethod "$api/source-discovery/candidates/$($candidate.id)/activate" -Method Post -Headers $headers
if ($activated.status -ne 'activated' -or $null -eq $activated.source_id) { throw 'Candidate activation failed' }
$source = Invoke-RestMethod "$api/sources/$($activated.source_id)" -Headers $headers
if (-not $source.enabled -or $source.official_status -ne 'official' -or @($source.columns | Where-Object enabled).Count -lt 1) { throw 'Activated source/column is not enabled and official' }

$events = @(Invoke-RestMethod "$api/source-discovery/runs/$($run.id)/events" -Headers $headers)
if ($events.Count -lt 1 -or $events[0].stage -ne 'content_gap_detection') {
  throw 'Run event history does not start with content_gap_detection'
}
$candidateEvents = @(Invoke-RestMethod "$api/source-discovery/candidates/$($candidate.id)/events" -Headers $headers)
$requiredStages = @('candidate_discovery','official_status_validation','column_discovery','trial_crawl','quality_scoring','manual_approval','source_activation')
$observedStages = @($candidateEvents | ForEach-Object stage)
$lastIndex = -1
foreach ($stage in $requiredStages) {
  $nextIndex = -1
  for ($index = $lastIndex + 1; $index -lt $observedStages.Count; $index++) {
    if ($observedStages[$index] -eq $stage) { $nextIndex = $index; break }
  }
  if ($nextIndex -lt 0) { throw "Missing or out-of-order candidate stage: $stage" }
  $lastIndex = $nextIndex
}
$metrics = Invoke-RestMethod "$api/source-discovery/metrics" -Headers $headers
if ($metrics.activated_source_count -lt 1) { throw 'Activation metrics were not updated' }
~~~

预期事件顺序包含：content_gap_detection → candidate_discovery → official_status_validation → column_discovery → trial_crawl → quality_scoring → manual_approval → source_activation。候选必须先是 pending_approval，未经管理员 approve 的 activate 必须返回 409；批准后 activate 才能创建 enabled Source 和 enabled SourceColumn。Brave API 的真实响应/配额要单独记录；Bing Search API 已在 2025-08-11 退役，不能把旧 Bing endpoint 当作验收路径（见 [Microsoft retirement notice](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement) 和 [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get)）。

### 14.1 真实官方站点至少 10 篇

试抓上限是 5 篇，不能把 trial crawl 当作十篇生产证据。对刚激活且人工确认至少有 10 篇可访问文章的栏目执行：

~~~powershell
$column = @($source.columns | Where-Object enabled | Select-Object -First 1)[0]
if ($null -eq $column) { throw 'No enabled column is available for the ten-article acceptance' }
$cozeStatus = Invoke-RestMethod "$api/system/coze/status" -Headers $headers
if (-not $cozeStatus.enabled -or -not $cozeStatus.token_configured -or -not $cozeStatus.batch_workflow_configured) { throw 'Coze batch workflow is not fully configured' }
$task = Invoke-RestMethod "$api/crawl-tasks" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  source_column_id = $column.id
  task_type = 'full'
  trigger_type = 'manual'
  execution_mode = 'queued'
  provider = 'coze'
  contract_mode = 'batch_crawl'
  provider_contract = 'batch_crawl'
  max_articles = 10
  max_pages = 1
} | ConvertTo-Json)
$deadline = (Get-Date).AddMinutes(15)
do {
  Start-Sleep -Seconds 2
  $task = Invoke-RestMethod "$api/crawl-tasks/$($task.id)" -Headers $headers
} while ($task.status -notin @('completed','waiting_review','partial_failed','failed','cancelled') -and (Get-Date) -lt $deadline)
if ($task.status -notin @('completed','waiting_review')) { throw "Ten-article crawl failed: $($task.status)" }
if ($task.discovered_count -lt 10 -or $task.fetched_count -lt 10 -or $task.failed_count -ne 0) { throw "Ten-article requirement failed: discovered=$($task.discovered_count), fetched=$($task.fetched_count), failed=$($task.failed_count)" }
$invocations = @(Invoke-RestMethod "$api/crawl-tasks/$($task.id)/invocations" -Headers $headers)
if (@($invocations | Where-Object { $_.contract -eq 'batch_crawl' -and $_.status -eq 'completed' -and $_.http_status_code -ge 200 -and $_.http_status_code -lt 300 }).Count -lt 1) { throw 'No successful persisted batch_crawl invocation' }
$results = @(Invoke-RestMethod "$api/crawl-tasks/$($task.id)/results" -Headers $headers)
$summary = Invoke-RestMethod "$api/crawl-tasks/$($task.id)/acceptance-summary" -Headers $headers
$failedUrls = @(Invoke-RestMethod "$api/crawl-tasks/$($task.id)/failed-urls" -Headers $headers)
if ($results.Count -lt 10 -or $summary.database_document_count -lt 10 -or $failedUrls.Count -ne 0) { throw 'Ten real documents were not persisted' }
~~~

预期：任务为 `completed` 或正常的 `waiting_review`，至少发现/抓取/持久化 10 篇，失败 URL 为 0，且存在成功的 `batch_crawl` Coze invocation。少于 10 篇、失败 URL、没有 invocation 或只有 fixture 数据均为 FAIL。

### 14.2 Coze review 与 grounded chat

配置真实 `ODIRAG_LLM_PROVIDER=coze`、`ODIRAG_ANSWER_PROVIDER=llm`、`COZE_API_TOKEN`、`ODIRAG_COZE_BOT_ID` 后，按串行构建规则重启；栏目批量 URL 仍使用独立的 `COZE_BATCH_API_URL`：

~~~powershell
$env:ODIRAG_LLM_PROVIDER = 'coze'
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:COZE_ENABLED = 'true'
$env:COZE_API_TOKEN = '<real-token>'
$env:ODIRAG_COZE_BOT_ID = '<real-bot-id>'
docker compose build backend
docker compose --profile async up -d --no-build backend worker
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.coze_base_url, bool(s.coze_api_token), s.coze_bot_id)"

$review = $null
foreach ($item in $results) {
  $attempt = Invoke-RestMethod "$api/reviews/$($item.id)/run" -Method Post -Headers $headers
  if ($null -ne $attempt.llm_decision) { $review = $attempt; break }
}
if ($null -eq $review) { throw 'No fetched document reached a real Coze review' }
$documentId = $review.document_id
if ($review.final_status -ne 'approved') {
  $manual = Invoke-RestMethod "$api/reviews/$documentId/manual-review" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ decision = 'approve'; summary = 'Production acceptance reviewer confirmed this official document'; reasons = @('Acceptance evidence') } | ConvertTo-Json)
  if ($manual.final_status -ne 'approved') { throw 'Manual review approval failed' }
}
$index = Invoke-RestMethod "$api/documents/$documentId/reindex" -Method Post -Headers $headers
if ($index.chunk_count -lt 1 -or $index.vector_point_ids.Count -lt 1) { throw 'Approved Coze-reviewed document was not indexed' }
$chat = Invoke-RestMethod "$api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '<来自该官方文档、可由原文直接回答的问题>' } | ConvertTo-Json)
$trace = Invoke-RestMethod "$api/chat/traces/$($chat.trace_id)" -Headers $headers
if ($chat.refusal -or $chat.citations.Count -lt 1 -or $trace.model_name -ne 'coze-bot') { throw 'Grounded Coze chat did not return a cited answer' }
if ($trace.token_usage_json.measurement -eq 'not_available') { Write-Warning 'Provider omitted token usage; record cost as unverified, not zero' }
~~~

预期：review 的 `llm_decision` 来自真实 Coze，批准文档可被真实 embedding 索引，chat 只引用已存储 chunk；Coze trace 的 `model_name` 为 `coze-bot`。缺少凭据、异步语义不匹配、无 usage 或无引用必须保留为 UNVERIFIED/FAIL，不能用 fixture 替代。

## 15. 结束条件与当前结论

只有 PostgreSQL、Redis、Qdrant、worker、scheduler、Nginx、frontend、Alembic 和所选真实 provider 全部 PASS-LIVE，且日志/trace/备份恢复证据已归档，才可把部署标为生产接受。

### 本机 development 栈证据（2026-08-05，当前恢复检查点）

以下结果是真实本地 Compose 运行结果，标记为 `VERIFIED-LOCAL`。它们证明当前 development 栈，但不能替代目标生产环境的 `PASS-LIVE`：

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| Compose 服务 | 当前 8 个服务均 healthy：backend、frontend、postgres、redis、qdrant、worker、scheduler、nginx；Nginx 为 1.30.4 | development 配置未证明生产 secret/TLS/provenance；镜像未 fresh build/scan |
| PostgreSQL | `pg_isready` accepting connections；server/client UTF8；current/heads 为 `0006_coze_task_operations (head)`；`alembic check` 无漂移；6 张 Phase16/Coze 表存在 | 未执行生产备份恢复、连接池耗尽和专用 PostgreSQL downgrade |
| Redis | PONG、backend ping=True、应用配置 `redis`、响应含限流 header、共享 `odirag:ratelimit:*` key 存在 | 未证明 ACL、故障转移、多副本公平性和持久化恢复 |
| Qdrant | `/healthz` HTTP 200；当前 collection 数为 0 | 没有成功抓取/索引文档，未证明 collection schema、points 删除补偿和备份 |
| worker/scheduler | worker inspect ping 成功；scheduler PID 存在；日志观察到 recovery/monitoring 调度 | 未执行真实 queued crawl/source-discovery 完成和故障恢复演练 |
| Nginx/frontend | Nginx 1.30.4 下 `/healthz`、`/`、`/api/system/health` 均 200；dependencies 全 healthy；管理员页面登录并渲染仪表盘；浏览器控制台无 warning/error；安全响应头存在 | 仅交互式本地 HTTP 浏览器证据；未执行自动化 live Playwright、HTTPS 和生产浏览器门禁 |
| Docker/WSL 恢复 | Docker Desktop 4.85.0、Client/Server 29.6.2、Compose v5.3.1；`docker-desktop` WSL2 running；未删除 VHD/Volume/数据库 | 卡死 Desktop 进程已恢复；仍需目标主机容灾/重启演练 |
| 当前镜像配置与现存本地镜像 | 已配置 Python 3.12 Alpine、Nginx 1.30.4 Alpine，backend runtime 移除 pip；现存本地镜像启动通过 | 本轮未 fresh build/Scout/SBOM，状态仍为供应链 UNVERIFIED |
| Alembic | current/heads 为 `0006_coze_task_operations (head)`；`alembic check` 无新 upgrade operations | 未执行生产数据库 downgrade/backup/restore |
| scsia.org | 浏览器可读；backend DNS `198.18.0.208` 被 SSRF guard 拒绝；最新任务失败、0 文档、接口 422 | 不是 live crawl 成功；需要正常公网 DNS/出口及图片/OCR 抽取验收 |

因此当前结论仍为 **NOT ACCEPTED / EXTERNAL ACCEPTANCE REQUIRED**。Docker Desktop/WSL 和本地服务启动门禁已完成；剩余生产门禁是：当前加固镜像 fresh build/Scout/SBOM、真实 Brave/Coze/Direct LLM/embedding/rerank 凭据与错误/成本证据、至少 10 篇真实官方站点抓取、真实索引/Qdrant points、代表性评测与负载、备份恢复、Git checkpoint 和 live Playwright。
