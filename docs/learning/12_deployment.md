# 12 容器化、部署与 CI/CD

## 1. 模块目的

部署模块把后端、前端、PostgreSQL、Redis、Qdrant、Celery worker、scheduler 和 Nginx 组合为可重复启动的平台，并在 CI 中验证代码质量、迁移、测试、镜像和非 root 运行。

根 `docker-compose.yml` 是开发/demo 拓扑；`deploy/production/compose.yml` 与 release
脚本构成生产拓扑。当前 `v0.1.0-r6` 已在 Linux 主机完成 8/8 健康、TLS、监控、DR、
不可变镜像、事务部署/回滚和公网 E2E 验收。当前证据以
`PRODUCTION_READINESS_REPORT.md` 为准。

## 2. 输入与输出

输入包括 `.env`/环境变量、Docker build args、Compose profiles、镜像标签、管理员密码和持久卷。

输出包括：

- 后端与前端镜像；
- 8 个必需 Compose 服务及 app/postgres/redis/qdrant volumes；
- Nginx 暴露的 UI 与 `/api`；
- 自动 Alembic 升级、健康检查、demo seed/reindex；
- GitHub Actions 的 lint、type、test、coverage、migration、build 和容器 smoke 结果。

## 3. 数据流

```text
scripts/start_demo.ps1 或 start_demo.sh
  -> 设置 deterministic demo Provider + Qdrant
  -> docker compose build backend
  -> docker compose build frontend
  -> docker compose --profile ui --profile async up -d --no-build
  -> postgres/redis/qdrant healthy
  -> backend entrypoint 创建目录 + alembic upgrade head
  -> backend healthy
  -> worker、scheduler、frontend、nginx 服务
  -> initialize-demo.sh
     -> seed_demo.py
     -> 登录 API
     -> 对 approved demo documents 调 reindex
  -> http://127.0.0.1:8080
```

worker/scheduler 设置 `ODIRAG_RUN_MIGRATIONS=false` 并依赖 backend healthy，避免多个容器同时迁移。

## 4. 核心类与文件

- `docker-compose.yml`：服务、profiles、环境、depends_on、healthcheck 和 volumes。
- `Dockerfile.backend`：多阶段 Python 构建、非 root UID/GID 10001、数据目录。
- `Dockerfile.frontend`：`npm ci`/Vite 构建和 Nginx 静态运行时。
- `deployment/container-entrypoint.sh`：目录创建、迁移重试和 exec。
- `deployment/initialize-demo.sh`：seed 后通过真实 API reindex。
- `deployment/nginx.conf`：边缘反向代理和安全头。
- `deployment/frontend.nginx.conf`：SPA fallback、CSP 和静态缓存。
- `scripts/start_demo.ps1`、`scripts/start_demo.sh`：跨平台一键启动。
- `scripts/seed_demo.py`：幂等 demo 基础记录，可选真实 index/evaluate pipeline。
- `.github/workflows/ci.yml`：backend、frontend、containers 三个 job。
- `.github/workflows/release.yml`、`production-deploy.yml`：GHCR digest、SBOM/provenance、
  生产部署与回滚门禁。
- `deploy/production/compose.yml`、`deploy/production/scripts/`、
  `deploy/production/monitoring/`：生产网络、资源、秘密挂载、监控、备份恢复和不可变
  release transaction。
- `runbooks/`：部署、回滚、监控、告警、备份恢复、灾备和事件响应。
- `.env.example`：可配置部署参数模板。

## 5. 主要设计决策

1. Compose 默认启动基础依赖和 backend；`ui` profile 加 frontend 与 nginx，`async` profile 加 worker 与 scheduler。
2. 数据库、Redis、Qdrant 和对外端口默认绑定 `127.0.0.1`，降低开发机暴露面。
3. backend 镜像以 `odirag` 非 root 用户运行，`/app/data` 在构建时创建并挂载共享 volume。
4. entrypoint 在启动 Uvicorn 前重试 Alembic，最大次数和间隔可配置。
5. 所有异步服务复用同一 backend 镜像和 app-data，但只有 backend 执行迁移。
6. 一键 demo 明确使用 deterministic embedding、Qdrant 和 deterministic rerank，不声称使用外部商业模型。
7. seed 只写真实基础记录和 verified question；索引通过真实 API pipeline 完成，避免预造 Qdrant 成功状态。
8. Nginx 把 `/api/` 代理给 backend，其余流量给 frontend；前端自身支持 history fallback。
9. CI 除单元/集成测试外，还升级-降级-再升级迁移，并以非 root SQLite 容器完成健康、可写数据和登录 smoke。

## 6. 技术选型原因

- Docker Compose：适合本项目八服务的本地演示和开源复现。
- 多阶段镜像：构建依赖不必全部进入运行时层，前端只交付静态产物。
- Nginx：统一入口、SPA 静态服务、反向代理、安全头和缓存策略。
- Healthcheck + depends_on：将启动顺序建立在真实健康状态，而非固定 sleep。
- Named volumes：容器重建后保留数据库、Redis、Qdrant 和应用 artifact。
- GitHub Actions：对 push/PR 给出可重复质量门，容器 job 依赖后端和前端通过。
- PowerShell + POSIX shell：覆盖 Windows 本地演示和 Linux/macOS/CI 环境。

## 7. 常见故障模式

- Docker/Compose 不存在：一键脚本在启动前明确失败。
- backend 迁移反复失败：数据库未 healthy、连接串错误或 Alembic revision 问题，达到上限容器退出。
- worker/scheduler unhealthy：检查 Redis、backend health、Celery task 注册和 pid/inspect healthcheck。
- seed 登录失败：`ODIRAG_ADMIN_PASSWORD` 未设置或与已存在管理员哈希不一致。
- Qdrant dimension mismatch：旧 collection 与 demo `embedding_dimensions` 不同，应使用版本化 collection 名或迁移重建。
- Nginx 502：backend 或 frontend 不 healthy、upstream 名错误或 profile 未启动。
- Windows 脚本环境污染：脚本在 finally 恢复临时 demo 环境变量。
- CI 能构建但本机不能：镜像、端口、Docker Desktop 和文件共享环境不同，需要实际运行日志。
- 根 demo Compose 允许 tag override，不能作为生产身份；生产 release 以 GHCR digest 固定。
  Python 生产与开发依赖均有 lock 文件，更新时必须由 CI 重新验证。

## 8. 调试步骤

1. 运行 `docker compose config --quiet` 检查变量展开和 YAML 模型。
2. 查看 `docker compose ps` 的 health 状态与启用 profiles。
3. 迁移问题执行 `docker compose logs backend`，再在容器内运行 `python -m alembic current`。
4. worker 问题查看 `docker compose logs worker scheduler` 和 Celery inspect ping。
5. 数据权限检查容器 `id -u` 应为 10001，且 `/app/data` 可写。
6. Nginx 配置用 `nginx -t`，再分别请求 `/healthz`、`/api/system/health` 和 SPA 深链接。
7. seed 后查询 approved documents、chunks、Qdrant collection 和 BM25 snapshot。
8. CI 本地复现顺序：backend checks -> frontend checks -> Compose/Nginx validation -> image build/smoke。

## 9. 面试问题与参考答案

### 9.1 为什么 worker 不自己执行迁移？

多个副本并发迁移会产生竞态。backend 作为单一迁移入口，worker/scheduler 等待其 healthy 后启动。

### 9.2 为什么容器要非 root？

应用被利用时可降低对容器文件系统和宿主映射资源的权限。CI 还断言 UID=10001 和数据目录可写。

### 9.3 Healthcheck 与 depends_on 有什么关系？

Compose 使用 `condition: service_healthy`，只有 PostgreSQL、Redis、Qdrant 或 backend 真正响应健康检查后，下游服务才启动。

### 9.4 为什么 demo 仍使用 Qdrant？

一键启动要验证真实向量存储适配器。Embedding 和 rerank 可 deterministic 以免要求凭据，但向量点实际写入 Qdrant。

### 9.5 多阶段前端镜像的好处是什么？

Node 只在 builder 阶段编译，运行镜像只有 Nginx 和静态文件，体积和攻击面更小。

## 10. 答辩问题与参考答案

### 10.1 Docker Compose 是否已经在当前机器验收？

开发工作站状态不能替代生产证据。根 demo Compose 曾在本地验收；更重要的是生产 Linux
主机已运行 `v0.1.0-r6`，8/8 服务健康，Phase 1-5 为 `PASS-LIVE`。答辩时必须区分本地
demo、CI 镜像 smoke 和真实生产三类证据。

### 10.2 CI 具体验证了什么？

Ruff、Black、mypy、迁移升降级、pytest coverage；前端 lint/type/test/build；Compose/Nginx 配置；后端/前端镜像 build；后端非 root SQLite 健康、数据可写和管理员登录 smoke。

### 10.3 当前是否达到生产部署标准？

达到当前声明的单节点生产标准：TLS、受保护运行时 secrets、资源限制、私网依赖、
Redis 限流、Prometheus/Grafana/Alertmanager、DR、GHCR digest、SBOM/provenance、事务发布和
回滚均有 live evidence。它不是 HA，也没有第三方持久 paging/SLA；Gold 回答质量仍为
`PARTIAL / FAIL-LIVE-QUALITY`。

### 10.4 demo 数据是否硬编码评估成功指标？

当前 seed 不再预写成功 metrics，只创建 verified question 和 pending experiment；可用 `--index --evaluate` 运行真实 pipeline 后生成实际 run。

### 10.5 如何备份和恢复？

仓库已有 PostgreSQL logical/base/WAL/PITR、Qdrant snapshot、Redis、attachment、manifest
和跨组件演练脚本，恢复只进入隔离资源。Phase 2 实测 RPO/RTO 并验证 821-ID 与 69 个
attachment checksum。调度和 retention deletion 仍由 operator 驱动，首个 off-host sink
也不是 immutable/object-locked。

## 11. 代码阅读路线

1. `.env.example`
2. `docker-compose.yml` 的 anchors、基础服务、backend、profiles
3. `Dockerfile.backend` 与 entrypoint
4. `Dockerfile.frontend` 与两个 Nginx 配置
5. `scripts/start_demo.sh`、`start_demo.ps1`
6. `deployment/initialize-demo.sh`、`scripts/seed_demo.py`
7. `.github/workflows/ci.yml`
8. `.github/workflows/release.yml`、`production-deploy.yml`
9. `deploy/production/compose.yml`、release/backup/restore scripts
10. `runbooks/` 与 `backend/app/services/health.py`

## 12. 实践修改练习

在不改变现有单节点生产的前提下，设计一个 disposable 第二主机恢复演练：只读取现有
manifest 和 off-host artifacts，恢复 PostgreSQL/Qdrant/Redis/attachments，验证 182/821/69
不变量与 Provider smoke，记录 RPO/RTO，并确保任何失败都不会接触生产卷或 active Qdrant
collection。
