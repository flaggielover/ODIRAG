# ODIRAG Production Acceptance Checklist

本文是部署到真实环境前的执行清单，不是模拟成功清单。最后审阅：2026-08-09。八个服务当前 healthy。Task 23 的真实 MIIT government/official 主链保持 `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5`；Phase A Evidence Sufficiency 已对“检索到无关 chunk”的场景取得 PASS-LIVE。更广泛的 Phase B-F 生产发布门禁仍未全部接受。

## 当前 official-source 最后一关（PASS-LIVE）

当前合法判定是索引 hit metadata 中 `official_status` 忽略大小写后等于 `official`。`organization_type` 和域名只用于来源治理/人工核验，不参与 chat-time 判定；不要把 association 改成 government，不要关闭 `grounding_require_official_source`。

已执行结果：

| Task | Official URL type | HTTP / provider | discovered / fetched / documents | accepted / rejected / pending / failed | task chunks / Qdrant points |
| --- | --- | --- | --- | --- | --- |
| 19 | 四川省科技厅静态政策栏目 | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 20 | 工信部通知栏目 | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 21 | 中国政府网最新政策栏目 | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 22 | 工信部真实正文 URL | 200 / `no_articles` | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 |
| 23 | 同一工信部真实正文 URL，Coze 重新发布后 | 200 / `completed` | 1 / 1 / 1 | 1 / 0 / 0 / 0 | 6 / 6 |

Tasks 19-22 是重新发布前的历史失败证据。Task 23 raw/normalized 已持久化并由当前 Pydantic Schema 重新解析通过；文章 1、content length 2,614、HTML、`needs_ocr=false`、quality 0.95、government/official。Document 6 已人工 approved，生成 6 stable chunks/points，并完成正式 cited answer。

Coze 重新发布后的精确重跑入口（不输出 token/password）：

~~~powershell
$ErrorActionPreference = 'Stop'
$pairs = @{}
Get-Content .env | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
    $key, $value = $line.Split('=', 2)
    $pairs[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
  }
}
$loginBody = @{ username = $pairs.ODIRAG_ADMIN_USERNAME; password = $pairs.ODIRAG_ADMIN_PASSWORD } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/auth/login -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($loginBody))
$headers = @{ Authorization = "Bearer $($login.access_token)" }
$taskBody = @{ source_column_id = 9; task_type = 'full'; trigger_type = 'manual'; provider = 'coze'; provider_contract = 'batch_crawl'; contract_mode = 'batch_crawl'; max_pages = 1; max_articles = 5 } | ConvertTo-Json
$task = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/crawl-tasks -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($taskBody))
do {
  Start-Sleep -Seconds 5
  $task = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/crawl-tasks/$($task.id)" -Headers $headers
} while ($task.status -notin @('completed', 'partial_failed', 'failed', 'cancelled'))
if ($task.discovered_count -lt 1 -or $task.fetched_count -lt 1) { throw 'Coze official-source discovery still produced no articles' }
$results = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/api/crawl-tasks/$($task.id)/results" -Headers $headers
if (@($results).Count -lt 1) { throw 'No official document was persisted' }
~~~

Task 23 实际结果满足上述预期：discovered/fetched/documents 1/1/1；raw/normalized 存在；正文和真实元数据正确；人工 approved；6 chunks/6 task points；重复 reindex 6 cache hits/0 new embeddings 且 IDs 不变；Hybrid final hits 5；正式 `/api/chat` 非拒答、Direct token usage 3,339、citation 可追溯；独立零命中问题 `refusal=true`、0 citations。因此本检查点已写入 `KNOWLEDGE_BASE_LIVE_CLOSED_LOOP=5/5`。

## Phase A Evidence Sufficiency（PASS-LIVE）

~~~powershell
docker compose run --rm --no-deps -e ODIRAG_RUN_MIGRATIONS=false -v D:\RAG\backend:/app/backend backend alembic check
docker compose run --rm --no-deps -e ODIRAG_RUN_MIGRATIONS=false -v D:\RAG\scripts:/app/scripts backend python /app/scripts/live_accept_evidence_sufficiency.py --base-url http://backend:8000/api
powershell -NoProfile -ExecutionPolicy Bypass -File D:\RAG\scripts\run_live_playwright.ps1
~~~

预期：Alembic 输出 `No new upgrade operations detected`；Live 脚本输出 `PASS-LIVE`，受支持问题的 Direct token/citation 大于零，非空无关检索与 cancellation/penalty/scope adversarial 问题的 candidates 大于零但 `refusal=true`、citations/token/cost 均为零；8080 Playwright 登录、官方问答、引用和监控页通过。2026-08-09 实际结果：supported trace `47c5b283-5e38-40f4-a7a3-1e684737671f`（5 hits、3,336 tokens、1 个真实 MIIT citation）；Mars/dinosaur trace `b38598b2-89a3-4cd2-92b3-ee733b013f71`；cancellation/original-numeric-penalty/scope traces `e07f742b-fa91-4e52-bd5f-cd7de42d96fc`、`7b1434b2-a01f-4005-872c-bf98ce314667`、`99cba6de-53db-42f1-8fbf-e127f9858fd9`。四个拒答均为 5 candidates、0 citations/tokens/cost。后端 324 passed；fixture Playwright 9 passed/1 skipped，live-stack 1 passed。

评测期望：citation precision/recall 的分母排除 `should_refuse=true` 的正确拒答样本；9 个正确拒答加 1 个错误 citation 的回归结果必须为 precision/recall `0/0`，不能是 `0.9/0.9`。`answer_grounding_rate` 必须来自 citation-bound claim 检查，不得直接使用被测 ChatService 的 `answer_support_validated` 自证。

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
docker compose build --pull --no-cache backend
docker compose build --pull --no-cache frontend
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

### PostgreSQL 备份/恢复演练（独立临时容器与临时卷）

以下 PowerShell 5.1 兼容脚本只从业务库执行 `pg_dump` 和只读计数。恢复写入发生在
`--network none` 的临时 PostgreSQL 容器及唯一临时卷中，不写入项目 `postgres-data`。
`finally` 只清理本次运行精确命名并带标签的临时资源；宿主备份和 SHA-256 留档：

~~~powershell
$ErrorActionPreference = 'Stop'
function Assert-Exit([string]$step) {
  if ($LASTEXITCODE -ne 0) { throw "$step failed, exit=$LASTEXITCODE" }
}

$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$token = "$stamp-$PID"
if ($token -notmatch '^\d{14}-\d+$') { throw 'Unsafe run token' }

$artifactDir = Join-Path $PWD "data\reports\acceptance\$token"
$sourceDump = "/tmp/odirag-acceptance-$token.dump"
$dumpPath = Join-Path $artifactDir "odirag-acceptance-$token.dump"
$restoreContainer = "odirag-pg-restore-$token"
$restoreVolume = "odirag-pg-restore-$token"
$restoreDb = "odirag_acceptance_restore_${stamp}_$PID"
if ($sourceDump -notmatch '^/tmp/odirag-acceptance-\d{14}-\d+\.dump$' -or
    $restoreContainer -notmatch '^odirag-pg-restore-\d{14}-\d+$' -or
    $restoreVolume -notmatch '^odirag-pg-restore-\d{14}-\d+$' -or
    $restoreDb -notmatch '^odirag_acceptance_restore_\d{14}_\d+$') {
  throw 'Unsafe restore resource name'
}

$pgUser = (@(docker compose exec -T postgres printenv POSTGRES_USER) -join '').Trim()
Assert-Exit 'read POSTGRES_USER'
$pgDb = (@(docker compose exec -T postgres printenv POSTGRES_DB) -join '').Trim()
Assert-Exit 'read POSTGRES_DB'
$pgContainer = (@(docker compose ps -q postgres) -join '').Trim()
Assert-Exit 'locate postgres container'
$pgImageId = (@(docker inspect --format '{{.Image}}' $pgContainer) -join '').Trim()
Assert-Exit 'inspect postgres image'
if ($pgImageId -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Invalid PostgreSQL image ID' }

if (@(docker container ls -a --format '{{.Names}}') -contains $restoreContainer) {
  throw "Container already exists: $restoreContainer"
}
Assert-Exit 'list containers'
if (@(docker volume ls --format '{{.Name}}') -contains $restoreVolume) {
  throw "Volume already exists: $restoreVolume"
}
Assert-Exit 'list volumes'

New-Item -ItemType Directory -Path $artifactDir | Out-Null
$sourceDumpCreated = $false
$containerCreated = $false
$volumeCreated = $false
$ok = $false

try {
  docker compose exec -T postgres pg_dump -U $pgUser -d $pgDb -Fc `
    --no-owner --no-privileges -f $sourceDump
  Assert-Exit 'pg_dump'
  $sourceDumpCreated = $true

  docker compose cp "postgres:$sourceDump" $dumpPath
  Assert-Exit 'copy dump'
  $dumpFile = Get-Item -LiteralPath $dumpPath
  if ($dumpFile.Length -lt 1024) { throw 'Dump is implausibly small' }
  Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath

  $countSql = "SELECT 'sources',count(*) FROM sources UNION ALL SELECT 'source_columns',count(*) FROM source_columns UNION ALL SELECT 'source_discovery_runs',count(*) FROM source_discovery_runs UNION ALL SELECT 'source_candidates',count(*) FROM source_candidates UNION ALL SELECT 'source_candidate_columns',count(*) FROM source_candidate_columns UNION ALL SELECT 'source_discovery_events',count(*) FROM source_discovery_events UNION ALL SELECT 'crawl_tasks',count(*) FROM crawl_tasks UNION ALL SELECT 'coze_invocations',count(*) FROM coze_invocations UNION ALL SELECT 'documents',count(*) FROM documents ORDER BY 1"
  $sourceCounts = @(docker compose exec -T postgres psql -U $pgUser -d $pgDb -At -v ON_ERROR_STOP=1 -c $countSql)
  Assert-Exit 'source counts'

  docker volume create --label "odirag.acceptance.run=$token" $restoreVolume | Out-Null
  Assert-Exit 'create isolated volume'
  $volumeCreated = $true

  $tempPassword = [guid]::NewGuid().ToString('N')
  $runArgs = @(
    'run','-d','--name',$restoreContainer,'--network','none',
    '--label',"odirag.acceptance.run=$token",
    '--mount',"type=volume,source=$restoreVolume,target=/var/lib/postgresql/data",
    '--env','POSTGRES_USER=restore_admin','--env',"POSTGRES_PASSWORD=$tempPassword",
    '--env',"POSTGRES_DB=$restoreDb",$pgImageId
  )
  & docker @runArgs | Out-Null
  Assert-Exit 'start isolated PostgreSQL'
  $containerCreated = $true

  $ready = $false
  for ($i = 0; $i -lt 60; $i++) {
    docker exec $restoreContainer pg_isready -U restore_admin -d $restoreDb *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw 'Isolated PostgreSQL did not become ready' }

  docker cp $dumpPath "${restoreContainer}:/tmp/source.dump"
  Assert-Exit 'copy dump to isolated PostgreSQL'
  docker exec $restoreContainer pg_restore -U restore_admin -d $restoreDb `
    --exit-on-error --no-owner --no-privileges /tmp/source.dump
  Assert-Exit 'isolated pg_restore'

  $restoreCounts = @(docker exec $restoreContainer psql -U restore_admin -d $restoreDb -At -v ON_ERROR_STOP=1 -c $countSql)
  Assert-Exit 'restored counts'
  if (Compare-Object $sourceCounts $restoreCounts) { throw 'Restored counts differ' }
  $ok = $true
}
finally {
  if ($containerCreated) { docker rm -f $restoreContainer | Out-Null }
  if ($volumeCreated) { docker volume rm $restoreVolume | Out-Null }
  if ($sourceDumpCreated) { docker compose exec -T postgres rm -f $sourceDump | Out-Null }
}
if (-not $ok) { throw 'Restore acceptance failed' }
~~~

预期：`pg_dump`、隔离 `pg_restore`、九张关键表计数对比全部退出 0；备份文件及
SHA-256 留档；按 `odirag.acceptance.run=$token` 查询不到残留容器或卷。当前仓库没有自动
备份调度器，目标环境仍需验证加密、保留策略、RPO/RTO 和生产数据量。

## 3. Alembic

~~~powershell
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads
docker compose exec -T backend alembic check
~~~

预期：current 和 heads 都指向 `0008_rerank_observability`，并标记 (head)；alembic check 无待生成迁移且退出码为 0。

使用专用验收数据库验证全链路迁移（不要在生产业务库直接 downgrade）：

~~~powershell
$acceptanceDb = 'odirag_acceptance_migration'
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $acceptanceDb;"
docker compose exec -T postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -c "CREATE DATABASE $acceptanceDb;"
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic upgrade head'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic downgrade 0003_crawl_reliability'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic upgrade head'
docker compose exec -T backend sh -lc 'export ODIRAG_DATABASE_URL="${ODIRAG_DATABASE_URL%/*}/odirag_acceptance_migration"; /opt/venv/bin/alembic current'
~~~

预期：upgrade、downgrade、再 upgrade 都退出 0，最终 `0008_rerank_observability (head)`。完成后清理专用数据库或按组织保留审计证据。

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

验证滚动替换不会让 Nginx 固定旧 Docker IP（会短暂重建单个 backend，只在验收环境执行）：

~~~powershell
docker compose exec -T nginx nginx -t
docker compose up -d --no-deps --force-recreate backend
docker compose ps backend nginx
1..15 | ForEach-Object {
  (Invoke-WebRequest "$base/api/system/health" -TimeoutSec 5).StatusCode
  Start-Sleep -Seconds 2
}
~~~

预期：`nginx -t` 成功，backend 和 Nginx 都恢复 healthy；Nginx 无需重启，15 次代理请求全部为 200。任何持续 502 或 `connect() failed` 都说明服务名仍被固定到旧容器 IP，不能通过该门禁。

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
docker build --pull --no-cache --file Dockerfile.backend --target builder --tag odirag/backend-builder:acceptance .
docker build --pull --no-cache --file Dockerfile.frontend --target builder --tag odirag/frontend-builder:acceptance .
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

2026-08-06 本机 live diagnostic：URL 与 Token 均只在未提交的 `.env` 中，三个消费服务确认
`enabled=true`、`batch_workflow_configured=true`、`token_configured=true`。task 4 证明部署入口要求
string `task_id`；task 5 证明 `coze.site/run` 返回 `run_id + batch_result` 外层；task 6 在两项修复后
HTTP 200、invocation completed、raw/normalized response 均持久化。其业务结果仍为 `NO_ARTICLES`、
0 discovered/fetched/documents/chunks/Qdrant points，故状态只能是 PARTIAL/LIVE-DIAGNOSTIC，不能算
真实内容验收通过。2026-08-07 Docker Desktop/Engine 已恢复，八服务 healthy，最终状态修复镜像已 rollout。

2026-08-07 task 7 真实执行记录（不输出 URL、Token 或 Authorization）：HTTP 200，invocation
`completed`，持久化 task `status=completed`、`provider_status=no_articles`，所有发现/抓取/成功/文档/
chunk/Qdrant point 计数均为 0；脚本结果为 `status=batch_result_empty`、exit code 1。该结果验证
鉴权、transport、raw/normalized 持久化和 no-articles 终态语义，但对已知存在内容的动态 SPA 属于
内容验收 FAIL，不得标为 `live_batch_verified`。

2026-08-07 新部署后的 task 8 真实执行记录（同样不记录部署 URL、Token、Authorization 或正文）：
HTTP 200、invocation `completed`、attempts `1`、retries `0`、duration `4141 ms`；normalized
`task_id` 为 string `"8"`，`workflow_version=batch_crawl-v1`。worker 正常结束异步执行，但业务任务
持久化为 `status=partial_failed`、`provider_status=partial_failed`，没有 provider error。statistics
只有 `pages_visited=1`；discovered/fetched/accepted/rejected/pending/failed、persisted failures、documents、
chunks 和 Qdrant points 均为 0。warnings 包含 `SPA_API_NOT_DISCOVERED`，并明确说明只取得基础 HTML、
未发现 API。验收脚本仍返回 `status=batch_result_empty`、exit code 1。

独立来源证据：`https://scsia.org/portal/news/264?pageNum=1&pageSize=5` 返回 HTTP 200 JSON、
`total=69`、五行，首行 ID `7587`；`https://scsia.org/portal/new/7587` 返回 data，`newsContent`
长度为 995。这里只保存状态、结构、ID 和长度，不保存正文。PostgreSQL 对 task 8 为 1 invocation、
0 documents、0 chunks；Qdrant collection 数为 0。监控打开 `high_failure_rate` high/open 告警，
observed `0.4` 超过 threshold `0.2`；相关回归 `49 passed`。这些仍是失败诊断证据。

2026-08-07 task 9 历史 bounded crawl checkpoint（不记录部署 URL、Token、Authorization、凭据或正文）：

- bounded 参数为 `max_pages=1`、`max_articles=5`；task/current stage/provider status 均为 `completed`，provider error 为 null；
- invocation HTTP 200/completed、attempts 1、retries 0、duration 22,757 ms；`raw_response_json=true`、`normalized=true`，normalized `task_id` 是 string `"9"`；
- 在当前 backend 容器中从 PostgreSQL 读取 raw response，再用 `parse_batch_crawl_response` 校验，Pydantic schema passed，articles/discovered/fetched 均为 5；
- accepted 0、rejected 5、pending 0、failed 0、provider failed URLs 0；task、normalized 和 persisted results 决策一致；
- PostgreSQL 为 5 documents、5 lineage、0 chunks、1 invocation；Qdrant 为 0 collections/points。

首篇元数据：标题“关于公布四川省2026年第六批软件企业及软件产品评估结果的通知”，URL
`https://www.scsia.org/portal/new/7587`，content length 0、needs OCR、image extraction、9 images、
decision rejected、index pending。五篇中三篇 image-only/needs-OCR/content length 0，另两篇 content length
349/203，全部 rejected。抓取层因此是 PASS-LIVE，但 OCR、正文可用性、质量复核、chunking、indexing 和
cited-answer 均不是 PASS-LIVE。

`embedding_provider=remote` 且 key 未配置，但 embedding 未参与本次 crawl；task 9 completed 且 failed 0，
不得据此把抓取判为失败。`live_accept_coze_batch.py` 在任务完成后读取 acceptance-summary 时收到 HTTP 503
`PROVIDER_UNAVAILABLE`，根因是不存在的 `odirag_chunks` collection count 在 Qdrant 返回 404；另有
qdrant-client 1.19/server 1.14 compatibility warning。两项均为后续本地修复，不撤销 task 9 抓取层 PASS-LIVE。

2026-08-08 当前证据替代上述 task 9 下游阻塞：task 13 保留为 Coze HTTP 200 后
`TASK_STATE_CHANGED` 的历史竞态失败；修复 source-column/row locking、queued→running 状态处理、
`image_ocr` schema、重复 URL 版本刷新和人工审核幂等后，task 14 成功。

Task 14 (`max_pages=1`, `max_articles=5`) 的 task/current stage/provider status 均 completed、provider error null；Coze
HTTP 200/completed、1 attempt/0 retries，raw/normalized persisted，strict BatchCrawlResult passed。
统计为 5 discovered/fetched/docs、1 accepted、4 rejected、0 pending、0 failed。五篇元数据依次为：

- length 0 / image / needs OCR / `OCR_FAILED` / rejected；
- length 0 / image / needs OCR / `OCR_FAILED` / rejected；
- length 5,358 / image_ocr / needs OCR false / `ocr_performed` / accepted / score 70；
- length 349 / html / rejected / score 0；
- length 203 / html / rejected / score 10。

Document 3 version history：v1 length 0/image/rejected/score 0 → v2 length 5,358/image_ocr/accepted/
score 0.70。现有 `POST /reviews/3/approve` 成功后文档为 approved，task 14 completed、pending 0。
acceptance-summary 的空状态曾真实返回 HTTP 200、`collection_exists=false`、points 0；索引后当前状态
为 HTTP 200、5 documents、8 chunks、`collection_exists=true`、8 points，并与 Qdrant REST 一致。

两次 pre-credential reindex 与一次 malformed-credential HTTP 401 保留为历史失败。修正 credential 后，
真实 remote `text-embedding-3-small`/1536 reindex 返回 HTTP 200、8 chunks、8 embeddings。Qdrant
直接查询为 1 collection/8 points。初次直查发现 payload 没有显式 `chunk_id`；适配器已补齐并测试，
第二次 reindex 原地回填，8 cache hits/0 embeddings，前后 point ID 集合哈希相同，全部 8 payload 合格。
真实 hybrid 检索返回 BM25/vector/fusion 8/8/8 和 5 final hits。当前 answer provider 是 `llm`，
LLM provider direct、model `gpt-4.1-mini`，密钥配置布尔值为 true；Direct 严格 AnswerResult provider 调用已执行。正式 `/api/chat` 因现有检索 hit 全部属于 association 而在模型前被 `official_source_required` 拒绝。

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

Task 9 的 summary 503 保留为历史证据。Task 14 已同时验证两种状态：索引前空 collection 返回 HTTP 200、
`collection_exists=false`、`qdrant_point_count=0`；真实 reindex 后返回 HTTP 200、
`collection_exists=true`、`qdrant_point_count=8`、`chunk_count=8`，并与 Qdrant REST 直查一致。

对已知存在文章的动态页面，`NO_ARTICLES`、0 discovered、0 persisted documents 或 0 Qdrant
points 均为 FAIL。HTTP 200 和 invocation `completed` 只证明鉴权与 transport，不证明文章发现、
正文抽取、质量判断、持久化或索引成功。动态 HTML 无链接时工作流必须报告
`DYNAMIC_CONTENT_UNSUPPORTED`，不得用 `NO_ARTICLES` 掩盖能力缺口。

栏目任务只能使用 `batch_crawl`。向 `POST /api/crawl-tasks` 提交
`provider=coze, contract_mode=legacy_single_article` 的预期结果是 HTTP 422、错误码
`COZE_LEGACY_SINGLE_ARTICLE_ONLY`；旧单篇部署只通过来源连通性/单篇兼容回归验证，不能创建栏目任务，
也不能用于证明批量抓取成功。

## 11. Embedding provider

~~~powershell
$env:ODIRAG_EMBEDDING_API_KEY = '<real-key>'
docker compose up -d --force-recreate backend
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.embedding_provider, s.embedding_base_url, bool(s.embedding_api_key), s.embedding_model, s.embedding_dimensions)"
$doc = Invoke-RestMethod "$base/api/documents?final_status=approved&limit=1" -Headers $headers | Select-Object -First 1
$reindex = Invoke-RestMethod "$base/api/documents/$($doc.id)/reindex" -Method Post -Headers $headers
$reindex.embedding_model
$reindex.embedding_version
$reindex.chunk_count
$reindex.vector_point_ids.Count
~~~

当前 OpenAI-compatible `remote` / `text-embedding-3-small` / 1536 已 PASS-LIVE。历史 document 3 为 8 chunks/8 points；task 23 official document 6 首次 reindex 为 6 chunks/6 embeddings，第二次为 6 cache hits/0 embeddings 且 ID 集合不变。PostgreSQL/Qdrant 当前均为 14 indexed chunks/points；payload 的 `chunk_id` 与 point ID 相等。历史 401 保留为 credential fail-closed 证据，没有 fake fallback 或半写入。

## 11.1 Phase B rerank and retrieval-matrix checkpoint

Run these checks after deploying a build containing migration `0008_rerank_observability`:

~~~powershell
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print({'provider': s.rerank_provider, 'configured': bool(s.rerank_api_key), 'model': s.rerank_model, 'timeout_seconds': s.rerank_timeout_seconds, 'failure_policy': s.rerank_failure_policy})"
~~~

Expected: Alembic reports `0008_rerank_observability (head)` and `No new upgrade operations detected`; the configuration output contains only `configured=true|false`, never a key. With `provider=none`, a protected `/api/search/debug` request using `mode=hybrid_rerank` must return `rerank_applied=false`, `rerank_metadata.provider=none`, `rerank_metadata.cost=null`, `rerank_metadata.cost_measurement=not_applicable`, and `warnings` containing `rerank_provider_disabled`, while ordinary Hybrid hits remain available.

For a remote provider, set `ODIRAG_RERANK_PROVIDER=remote`, `ODIRAG_RERANK_BASE_URL`, `ODIRAG_RERANK_MODEL`, `ODIRAG_RERANK_TIMEOUT_SECONDS`, `ODIRAG_RERANK_FAILURE_POLICY`, and inject `ODIRAG_RERANK_API_KEY` through the approved secret mechanism. Do not put it in this checklist output, a shell history artifact, or a response capture. Then verify a real `/api/search/debug` result has `rerank_applied=true`, a non-empty `rerank_results`, bounded `candidate_count`/`reranked_count`, a non-negative latency, and a cost measurement that is either provider-reported or explicitly `not_available`.

Test both policies with a controlled unreachable endpoint only in a non-production environment:

- `open`: response remains 200, final hit order equals fusion order, `rerank_applied=false`, and metadata contains a stable redacted error code.
- `closed`: the request returns the normal structured provider-unavailable error; it must not silently degrade.

Run the four-mode matrix against the same verified evaluation-question snapshot:

~~~powershell
# Authenticate normally, then post the same verified question IDs for all modes.
Invoke-RestMethod "$api/evaluations/matrix" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{
  matrix_name = "retrieval-matrix-$(Get-Date -Format yyyyMMddHHmmss)"
  question_ids = @('<verified-question-id>')
  top_k = 10
} | ConvertTo-Json)
~~~

Expected: exactly four runs named/marked `bm25`, `vector`, `hybrid`, and `hybrid_rerank`, all using the same returned `question_ids` snapshot and requested/effective `top_k`. Compare Recall@5/10, MRR, nDCG, citation precision/recall, answer-grounding rate, unsupported-answer rate, latency, and cost only when their report denominator is non-zero. A fixture or deterministic result is not remote rerank PASS-LIVE.

Actual 2026-08-10 local checkpoint: fresh backend image installed Alembic `1.18.5`; real PostgreSQL reached `0008_rerank_observability (head)` with no drift; all eight Compose services healthy; 8080 and health endpoint returned 200. The current runtime was `provider=none/configured=false`, and a real debug search produced five hits with the required disabled metadata. Remote rerank remains **BLOCKED-LIVE**.

## 11.2 Phase C bounded corpus expansion checkpoint

### 11.2.1 Generalized-crawl code gate (local/fixture only)

Run before any live corpus task:

~~~powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests\unit\test_crawler_adapters.py tests\unit\test_coze_crawl_provider.py -q
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\black.exe --check app tests
.\.venv\Scripts\mypy.exe app
Pop-Location
~~~

Expected current result: `356 passed`; Ruff, Black and mypy pass. This gate verifies deterministic HTML candidate scoring, URL normalization, bounded pagination, direct-detail extraction, attachment/image/OCR metadata, SPA/API fallback, site rules, stable failure codes and strict Coze relative-resource normalization. A separate read-only public-URL smoke in the backend container currently returns `UnsafeUrlError` from the existing SSRF/public resolver for the tested government domains; do not weaken that resolver or count the smoke as live acceptance. This gate must not be counted as a real document or provider acceptance.

### 11.2.2 Live C1 gate

Run each source through the authenticated Source/CrawlTask API after the backend runtime has loaded the new code. Use `max_pages=1` and `max_articles=5`. A task is eligible for C1 only when its persisted raw and normalized Coze response has `articles[]` with real URLs, `articles_discovered >= 1`, `articles_fetched >= 1`, and a strict `BatchCrawlResponse`; then continue through quality decision, manual approval, chunking and indexing. A HTTP 200 with `NO_ARTICLES`, a directory-page rejection, or a contract error is negative live evidence, not a success. Do not edit old task rows to pass.

Run each canary through the authenticated API with `max_pages=1` and `max_articles=5`; do not mark a task successful merely because the provider returned HTTP 200.

| Task | Column | Expected interpretation | Actual result |
| --- | ---: | --- | --- |
| 24 | 4 (gov.cn JSON) | `discovered >= 1` and a result-bearing `articles[]` | `0/0/0`, `no_articles`, HTTP 200 |
| 25 | 5 (JXT list) | article detail extraction followed by quality review | `1/1/1`, directory page rejected, quality `0.0` |
| 26 | 3 (KJT list) | article detail extraction followed by quality review | `1/1/1`, directory page rejected, quality `0.0` |
| 27 | 2 (KJT detail) | strict detail contract | task failed, `COZE_CONTRACT_MISMATCH` |

The historical pre-generalization baseline was 2 approved documents, 14 chunks and 14 Qdrant points. The three list-page canaries and one detail canary remain **BLOCKED-LIVE** evidence until a fresh invocation proves real detail expansion; task 27's historical relative-image contract error is now diagnosable and will only be re-evaluated by a new task. Do not create 100 speculative documents, use the local provider to inflate live counts, bypass manual review, or edit PostgreSQL directly. Stop C1 at the first requirement for manual Coze republish/API key/cloud action and report that exact blocker.

#### 11.2.3 Post-generalization live checkpoint (2026-08-10)

The backend rollout and local code gate passed, then tasks 28-34 were run through the authenticated API with `max_pages=1,max_articles=5`. Task 28 is the only new qualifying result: KJT detail `1/1/1`, strict response, manual approval, document 9, `government/official`, `region=四川省`, HTML word count 1619, quality 0.85. It generated 9 chunks and 9 real Qdrant points using `text-embedding-3-small`; a second reindex produced 9 cache hits and did not increase the direct Qdrant count (23). Its two attachments have `download_status=completed` but `parse_status=pending` and zero parsed text, so attachment parsing is not accepted.

Tasks 29, 30 and 32 each returned a single directory-page document and were rejected. Tasks 31, 33 and 34 returned `0/0/0` with HTTP 200. Together with tasks 25-27, these are independent negative live results across KJT, JXT, MIIT and gov.cn. They do not satisfy C1 (10 approved documents from at least 2 sources). The exact blocker is the deployed Coze batch workflow: it must be republished/deployed with list/API detail expansion and the strict `BatchCrawlResult` contract. Until that external action occurs, mark C1/C2/C3 **BLOCKED-LIVE/PENDING**, do not use Local provider or fixtures to inflate counts, and do not modify prior task rows.

Current persisted totals after this checkpoint: `documents=10`, `approved=3`, `rejected=7`, `chunks=23`, `crawl_tasks=34`, `reviews=20`, `lineage=78`, `attachments=3`. Regression commands and expected results: backend full suite `356 passed`; `ruff check`, `black --check`, and `mypy` pass; frontend lint/type-check/Vitest `18 passed`/build pass; live Playwright against `http://127.0.0.1:8080` `1 passed`; all eight Compose services healthy. These checks do not turn the blocked corpus gate into a live pass.

## 11.3 Phase D-E local gates

Run the source-discovery contract checks without a Brave key; the expected result is an explicit provider blocker, never a fixture claim:

~~~powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests\unit\test_source_discovery.py tests\integration\test_source_discovery_api.py tests\integration\test_source_discovery_scheduler.py -q
Pop-Location
npm --prefix frontend audit --json
npm --prefix frontend audit --omit=dev --json
docker scout cves --only-severity critical,high,medium,low odirag/backend:local
docker scout cves --only-severity critical,high,medium,low odirag/frontend:local
~~~

Expected: 19 source-discovery focused tests pass; a real Brave run is **BLOCKED-LIVE** when `ODIRAG_SOURCE_DISCOVERY_API_KEY` is absent; npm audit reports zero vulnerabilities; current Scout results are backend digest `b41a63d5b943` at `0C/0H/0M/0L` and frontend digest `7dcc62cebccd` at `0C/0H/0M/3L` for Alpine `libxml2 2.13.9-r2` with no fixed version. Do not mark the three low findings resolved and do not run a force/base-image major upgrade solely to clear them. Verify the actual builder dependency set with `docker build --target builder -t odirag/backend:builder-check -f Dockerfile.backend .` followed by `docker run --rm odirag/backend:builder-check python -m pip check`; remove only that exact temporary tag after confirming no container uses it.

## 11.4 Phase F live evaluation matrix

This command uses the existing authenticated API session (`$api` and `$headers` from the authentication section) and writes real evaluation questions, query traces, lineage and four report sets. It is not a fixture command. Do not place a password, token or provider key in this file or shell history.

~~~powershell
$matrixPayload = @{
  matrix_name = 'phase-f-live-miit-app-filing-20260810'
  category = 'phase-f-live'
  retrieval_version = 'phase-f-live-20260810'
  top_k = 5
  questions = @(
    @{
      question_id = 'phase-f-live-miit-app-filing-support-v2'
      question = '未履行备案手续的 APP 主办者能否从事 APP 互联网信息服务？'
      query_type = 'rag'
      expected_document_ids = @('868a6c55-5806-4237-875c-40163fa5b8e5')
      expected_chunk_ids = @('d7353b15-4d57-5a81-a034-708b616e93e6')
      expected_answer_points = @('不得从事APP互联网信息服务')
      difficulty = 'acceptance'
      category = 'phase-f-live'
      created_by = 'phase-f-live'
      verified = $true
    },
    @{
      question_id = 'phase-f-live-miit-app-filing-refusal-v2'
      question = '火星地表是否已经发现活体恐龙？'
      query_type = 'rag'
      should_refuse = $true
      difficulty = 'acceptance'
      category = 'phase-f-live'
      created_by = 'phase-f-live'
      verified = $true
    }
  )
}
$matrix = Invoke-RestMethod "$api/evaluations/matrix" -Method Post -Headers $headers -ContentType 'application/json' -Body ($matrixPayload | ConvertTo-Json -Depth 8)
if ($matrix.runs.Count -ne 4) { throw 'Expected all four retrieval modes' }
$hybridRerank = @($matrix.runs | Where-Object { $_.retrieval_mode -eq 'hybrid_rerank' })[0]
if ($null -eq $hybridRerank) { throw 'Missing hybrid_rerank result' }
$report = Invoke-RestMethod "$api/evaluations/$($hybridRerank.run_id)/report" -Headers $headers
$support = @($report.cases | Where-Object { $_.question_id -eq 'phase-f-live-miit-app-filing-support-v2' })[0]
$refusal = @($report.cases | Where-Object { $_.question_id -eq 'phase-f-live-miit-app-filing-refusal-v2' })[0]
if ($null -eq $support -or $support.refused -or $support.cited_chunk_ids -notcontains 'd7353b15-4d57-5a81-a034-708b616e93e6') { throw 'Expected real grounded MIIT citation' }
if ($null -eq $refusal -or -not $refusal.refused -or $refusal.cited_chunk_ids.Count -ne 0) { throw 'Expected no-evidence safe refusal' }
~~~

Expected: every mode must record its actual retrieval mode and top-k. The selected `hybrid_rerank` report must retrieve the real official MIIT chunk, use Direct LLM only when evidence is sufficient, return a non-empty cited answer, and safely refuse the no-evidence question. When `ODIRAG_RERANK_PROVIDER=none`, a `rerank_provider_disabled` warning is correct degradation and must not be reported as remote-rerank acceptance. A two-question matrix is a live plumbing gate only; retain a larger human-reviewed corpus for release-quality and SLA conclusions.

Actual local regression checkpoint (2026-08-10): backend `350 passed`; Ruff, Black (203 files), and mypy (155 source files) passed. Frontend lint, type-check, Vitest `18/18`, and production build passed; Playwright reported `10 passed, 1 skipped`. The skip is an explicit live-stack gate and is not reported as Live Acceptance. All eight Compose services were healthy, and 8080 root plus `/api/system/health` returned 200.

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
$env:ODIRAG_ANSWER_PROVIDER = 'llm'
$env:ODIRAG_DIRECT_LLM_API_KEY = '<real-key>'
docker compose up -d --force-recreate backend
docker compose exec -T backend python -c "from app.config import get_settings; s=get_settings(); print(s.llm_provider, s.answer_provider, s.direct_llm_base_url, bool(s.direct_llm_api_key), s.direct_llm_model)"
$chat = Invoke-RestMethod "$base/api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{ query = '企业研发投入有哪些支持措施？' } | ConvertTo-Json)
$trace = Invoke-RestMethod "$base/api/chat/traces/$($chat.trace_id)" -Headers $headers
$trace.model_name
$trace.token_usage_json
$trace.cost
~~~

Embedding/index/hybrid retrieval 已成功。当前 `llm_provider=direct`、model `gpt-4.1-mini`、answer provider `llm`，Direct 严格 schema/citation provider call 已真实通过。正式 Chat 对 association 来源返回 `official_source_required`，这不是 cited-answer PASS。下一次验收必须先由正常抓取路径产生满足 official-only policy 的文档；provider answer 只能引用 retrieval 返回的 chunk，trace model 必须等于配置模型，且 token usage 必须证明真实调用。若 provider 不返回价格，必须保留 `cost_measurement=not_available`，不能把 cost=0 解释为免费。

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
if (-not $candidate.official_evidence_json.same_host -or -not $candidate.official_evidence_json.status_ok) { throw 'Candidate failed exact-host or HTTP success validation' }
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

### 本机 development 栈证据（历史检查点；2026-08-09 当前补充）

以下结果是真实本地 Compose 运行结果，标记为 `VERIFIED-LOCAL`。它们证明当前 development 栈，但不能替代目标生产环境的 `PASS-LIVE`：

| 项目 | 结果 | 边界 |
| --- | --- | --- |
| Compose 服务 | 2026-08-09 当前 8 个服务均 healthy：backend、frontend、postgres、redis、qdrant、worker、scheduler、nginx | development 配置未证明生产 secret/TLS、目标持久化和 registry provenance |
| PostgreSQL | healthy；6 documents、2 approved、14 indexed chunks；task 23 completed 1/1 discovered/fetched, 1 accepted/approved official doc, pending/rejected/failed 0 | production scale/RPO/RTO unverified |
| Redis | PONG、backend ping=True、应用配置 `redis`、响应含限流 header、共享 `odirag:ratelimit:*` key 存在 | 未证明 ACL、故障转移、多副本公平性和持久化恢复 |
| Qdrant | health 正常；direct REST 1 collection/14 points；task 23 official payload 6/6；重复 reindex ID 集合不变；summary 1 doc/6 chunks/true/6 | live delete/compensation、备份和生产拓扑未验 |
| worker/scheduler | healthy；task 13 historical `TASK_STATE_CHANGED` retained；task 14 OCR and task 23 official closed loop completed | crawl/OCR/review/official answer PASS-LIVE；Brave/long-running failure recovery remains |
| monitoring | task 8 后 `high_failure_rate` 告警为 severity `high`、status `open`，observed `0.4`、threshold `0.2` | 证明本地规则检测到失败率；生产通知投递、升级、确认、恢复和多实例聚合未验证 |
| Nginx/frontend | `/`、`/api/system/health` 均 200；dependencies healthy；fixture Playwright 9 passed/1 skipped；真实 8080 live-stack 1 passed并展示正式 official citation；查询检查器可见 Evidence decision | HTTPS/目标生产浏览器门禁未通过 |
| Docker/WSL 恢复 | WSL 数据位于 D 盘且未删除 VHD/Volume/数据库；2026-08-07 Client/Server 29.6.2、Compose v5.3.1 与八服务通过 | 目标主机自动启动、生产 secret/TLS、容灾和 registry provenance 未验证 |
| fresh 镜像与供应链 | Current backend/frontend digest 为 `b41a63d5b943` / `7dcc62cebccd`；构建、`pip check`、Alembic、八服务和 npm 两种 audit 通过；Scout backend `0C/0H/0M/0L`, frontend `0C/0H/0M/3L` | 三项 libxml2 low 均无修复版本；目标 registry 仍必须生成新 SBOM/CVE、签名和 provenance |
| Alembic | 正式约束 `>=1.18,<1.19`，锁定并实装 1.18.5；existing PostgreSQL 到 `0008_rerank_observability` 且 `check` 无漂移；既有专用库 round-trip 通过 | 未对生产业务库直接 downgrade；目标维护窗口、锁等待和回滚审批未验证 |
| scsia.org | task 14 HTTP 200/completed、strict schema、5 docs；doc 3 OCR v2 length 5358 accepted/approved/indexed；8 chunks/8 points；hybrid retrieval 5 hits | association source is correctly refused by official-only grounding；region metadata `??` breaks province auto-filter；two docs remain OCR_FAILED/rejected |
| MIIT official | task 23 HTTP 200/completed、strict schema、1 doc accepted/approved/indexed；6 chunks/6 points；Hybrid 5 official hits；Direct answer 1 exact citation；zero-hit 与 non-empty irrelevant retrieval 均安全拒答 | Phase A PASS-LIVE；仍需 Phase B-F 的广泛评估与生产门禁 |

因此知识库真实闭环结论为 **PASS-LIVE / 5/5**，Phase A Evidence Sufficiency 也为 **PASS-LIVE**。Phase B/D/E 已完成本地门禁，Phase F 已完成两题真实矩阵但不代表代表性质量评估。整体生产发布仍为 **NOT ACCEPTED / EXTERNAL ACCEPTANCE REQUIRED**：真实 remote rerank、Phase C 最多 100 篇阶段语料、Phase D Brave、region `??` 历史数据、生产 TLS/secret、CI/registry 和代表性 Phase F 评估仍未全部验收。
