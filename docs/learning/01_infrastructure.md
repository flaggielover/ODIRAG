# 01 基础设施与核心后端

## 1. 模块目的

基础设施层负责把 ODIRAG 的配置、数据库、认证、错误处理、日志、指标和 Provider 组装成一个可启动的 FastAPI 应用。它不是业务流程本身，而是所有抓取、索引、检索、评估接口共同依赖的运行底座。

当前入口是 `backend/app/main.py` 的 `create_app()`。生产对象由 `backend/app/runtime.py` 的 `build_application_runtime()` 创建，数据库生命周期由 `backend/app/database/session.py` 的 `DatabaseManager` 管理。

## 2. 输入与输出

输入包括：

- 以 `ODIRAG_` 为前缀的环境变量和可选 `.env`；
- `config/chunking.yaml`、提示词文件及其他运行配置；
- HTTP 请求中的 JWT、JSON 请求体和 `X-Request-ID`；
- PostgreSQL、Redis、Qdrant 以及远程模型服务的连接信息。

输出包括：

- `/api` 下的 FastAPI 路由和 `/api/docs` OpenAPI 页面；
- 统一的 `ErrorResponse`；
- 结构化日志、请求延迟和数据库延迟指标；
- `ApplicationRuntime` 中可复用的分块、Embedding、向量库、BM25、重排和 LLM 对象；
- `/health/live`、`/health/ready`、内部 `/metrics`、`/api/system/health`、
  `/api/system/metrics` 和告警数据。

## 3. 数据流

```text
环境变量/.env
  -> Settings 校验
  -> create_app()
  -> DatabaseManager + MetricsRegistry + RateLimiter
  -> build_application_runtime()
  -> 中间件链（CORS、限流、请求上下文、指标）
  -> lifespan：建表（仅显式开启时）+ 管理员引导
  -> api_router
  -> Service
  -> Repository/Provider
```

请求进入后，认证依赖在 `backend/app/dependencies.py` 解码访问令牌，并将令牌中的 `ver` 与 `users.token_version` 比较。业务异常进入 `backend/app/errors.py` 的处理器，返回带错误码和请求 ID 的 JSON，而 Provider 的原始原因只写日志，不直接泄露给客户端。

## 4. 核心类与文件

- `backend/app/main.py`：应用工厂、生命周期、中间件和路由注册。
- `backend/app/config.py`：`Settings`、生产环境安全校验、Redis/Celery URL 派生。
- `backend/app/runtime.py`：`ApplicationRuntime` 和 Provider 选择逻辑。
- `backend/app/database/session.py`：异步/同步 SQLAlchemy 引擎和会话工厂。
- `backend/app/dependencies.py`：数据库会话、当前用户、管理员和运行时依赖。
- `backend/app/security.py`：密码哈希、JWT 签发和 `TokenIdentity` 解码。
- `backend/app/services/auth.py`：登录、刷新、注销和管理员引导。
- `backend/app/rate_limit.py`：固定窗口限流和 429 响应头。
- `backend/app/errors.py`：应用异常、验证异常、Provider 异常和兜底异常。
- `backend/app/logging.py`、`backend/app/metrics.py`：结构化日志与延迟采样。
- `backend/alembic/versions/`：业务数据库迁移历史。
- `backend/tests/unit/test_core_api.py`、`test_security.py`、`test_rate_limit.py`、`test_config.py`：核心行为验证。

## 5. 主要设计决策

1. 使用应用工厂而不是在模块导入时散落初始化，测试可注入独立 `Settings` 和 `DatabaseManager`。
2. API 只调用 Service，Service 再调用 Repository/Provider，避免路由直接承载业务逻辑。
3. `Settings` 在 staging/production 拒绝短 JWT 密钥、明文管理员密码、关闭限流、debug 和非 HTTPS CORS 来源。
4. 刷新令牌采用 token version 轮换。刷新或注销后提升数据库版本，使旧 access/refresh token 同时失效。
5. 外部服务不可用时返回明确的 `PROVIDER_UNAVAILABLE`，健康接口显示 degraded，不伪造成功。
6. `auto_create_schema` 只适合测试或显式开发模式；正式部署以 Alembic 为准。
7. 非 test 环境使用 Redis Lua 原子固定窗口限流器；Redis 不可用时 fail-closed 返回结构化 503。test 环境才使用内存实现，生产仍需验收 Redis ACL、故障转移和多副本公平性。

## 6. 技术选型原因

- FastAPI + Pydantic v2：请求/响应模型、依赖注入和 OpenAPI 能保持同一份契约。
- SQLAlchemy 2.x async：业务请求使用异步会话，同时保留同步引擎给 Alembic和数据库指标事件。
- Alembic：模型演进可审计、可升级和降级，避免生产环境依赖 `create_all()`。
- structlog：请求 ID、组件和异常类型可以结构化检索。
- PyJWT + Passlib：JWT 类型、发行方、有效期和密码哈希均由成熟库处理。
- Redis/Celery/Qdrant Provider 化：开发测试可使用确定性实现，生产仍保留真实适配器。

## 7. 常见故障模式

- 启动时报配置校验错误：通常是生产环境仍使用默认 JWT、明文管理员密码或 HTTP CORS。
- 数据库连接失败：管理员引导会记录 warning，但业务数据库接口仍无法工作，健康状态为 degraded。
- Redis 或 Qdrant 未运行：依赖健康显示 unavailable；仅依赖这些服务的功能失败。
- 旧令牌突然 401：用户的 `token_version` 已因刷新或注销递增。
- 429：命中了 auth、expensive 或 default 限流 profile，响应包含 `Retry-After`。
- 多 worker 下限流不一致：确认 `ODIRAG_RATE_LIMIT_BACKEND=redis` 且检查 `odirag:ratelimit:*` 共享 key；若 Redis 不可用，应用应返回 `RATE_LIMIT_BACKEND_UNAVAILABLE`，不能偷偷退回内存计数。
- 只改模型未执行迁移：运行时结构与数据库结构不一致，应先执行 `alembic upgrade head`。

## 8. 调试步骤

1. 在 `backend` 目录运行 `python -m app.main` 前先确认 `.env` 的 `ODIRAG_DATABASE_URL`。
2. 执行 `alembic current` 和 `alembic heads`，确认数据库位于最新 revision。
3. 请求 `/api/system/health`，分别查看 database、redis、qdrant 的状态和延迟。
4. 请求失败时根据 `error.code` 和 `request_id` 查结构化日志，不只看 HTTP 状态码。
5. 认证问题先调用 `/api/auth/login`，再检查 JWT 的 type、iss、exp 和 ver；不要在日志中输出完整令牌。
6. 指标问题调用管理员接口 `/api/system/metrics`，核对路由样本数及数据库样本数。
7. 定向运行：`python -m pytest tests/unit/test_core_api.py tests/unit/test_security.py tests/unit/test_rate_limit.py`。

## 9. 面试问题与参考答案

### 9.1 为什么使用应用工厂？

`create_app(settings, database=...)` 允许测试注入内存 SQLite 和独立配置，也避免全局状态难以替换。生产仍由模块级 `app = create_app()` 提供 ASGI 入口。

### 9.2 为什么 JWT 还要保存 token version？

纯无状态 JWT 在签发后难以立即撤销。ODIRAG 把 `ver` 写入令牌并与数据库比较，刷新和注销通过递增版本一次性撤销旧令牌族。

### 9.3 为什么健康检查不直接让进程退出？

系统采用诚实降级。数据库、Redis、Qdrant 分别报告状态，缺失的外部能力不会被伪装，但应用可以保留仍可用的接口和诊断入口。

### 9.4 异步 SQLAlchemy 的事务边界在哪里？

依赖层为每个请求提供 `AsyncSession`，Repository 执行查询，Service 决定何时 commit/rollback。`DatabaseManager.session()` 在异常时回滚。

### 9.5 当前限流方案的扩展瓶颈是什么？

非 test 环境已经使用 Redis Lua 原子固定窗口，多进程/多容器共享计数，Redis
不可用时 fail-closed。扩展瓶颈转为 Redis 容量与故障转移、受信代理的客户端身份、
热点 key、公平性，以及整个 BM25/cache/task/runtime 的多副本一致性，而不是进程内计数。

## 10. 答辩问题与参考答案

### 10.1 如何证明项目不是只有接口壳？

路由后面有真实 Service、Repository 和 Provider；测试通过 ASGITransport 创建数据库记录、索引文档、检索和生成 trace，而不是返回固定 JSON。

### 10.2 外部服务没有凭据时系统做什么？

真实适配器仍存在并验证配置；调用时返回结构化 503，健康接口显示不可用。测试/明确 demo 模式才选择 deterministic 或 memory Provider。

### 10.3 生产配置如何防止误用开发默认值？

`Settings.validate_security()` 在 staging/production 强制安全密钥、哈希管理员密码、HTTPS CORS、关闭 debug 且开启限流。

### 10.4 如何定位一次慢请求？

先按请求 ID 查日志，再查看内部 `/metrics`、Grafana/Prometheus 和
`/api/system/metrics`，随后结合 `query_traces` 中的各检索阶段耗时判断是 HTTP、DB、
Embedding、向量检索、重排还是 Direct LLM。

### 10.5 数据库迁移与自动建表有什么区别？

`create_schema()` 只按当前模型创建缺失表，不能表达可靠的升级/降级历史；Alembic revision 才是生产结构演进和回滚依据。

## 11. 代码阅读路线

1. `backend/app/main.py`
2. `backend/app/config.py`
3. `backend/app/database/session.py`
4. `backend/app/api/router.py` 与 `backend/app/dependencies.py`
5. `backend/app/runtime.py`
6. `backend/app/errors.py`、`backend/app/logging.py`、`backend/app/metrics.py`
7. `backend/app/security.py`、`backend/app/services/auth.py`
8. `backend/tests/conftest.py` 和核心单元测试

## 12. 实践修改练习

扩展现有 `/health/ready` 诊断：保持 database、Redis、Qdrant 必须全部 healthy
才返回 200，不泄露连接串或异常文本；为超时、Qdrant disabled、Redis 限流后端故障和
探针限流旁路补测试，并说明为什么 `/health/live` 不能依赖外部服务。
