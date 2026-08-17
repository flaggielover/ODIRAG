# 11 Vue 管理前端

## 1. 模块目的

前端提供真实 API 驱动的管理控制台，覆盖来源、抓取、文档、人工审查、问答证据、评估、实验、监控、告警和反馈。它负责展示状态与操作流程，不直接访问 PostgreSQL、Redis、Qdrant 或模型凭据。

## 2. 输入与输出

输入包括用户登录信息、表单、筛选器、路由参数和 FastAPI JSON 响应。

输出包括：

- 认证 session 与受保护路由；
- CRUD/任务/审核/索引/问答/评估/实验/告警/反馈 API 请求；
- loading、error、empty 和 retry 状态；
- 证据卡、trace、lineage、指标和告警操作；
- 响应式桌面/移动布局。

## 3. 数据流

```text
Vue View
  -> frontend/src/api/resources.ts
  -> apiRequest()
  -> Authorization Bearer token
  -> Vite proxy 或 Nginx /api
  -> FastAPI
  -> typed response
  -> view 的 ref/reactive state
  -> AsyncState / table / dialog / evidence UI
```

401 时 `api/client.ts` 只允许一个 `refreshPromise` 执行 token rotation，其他请求等待同一个 Promise；刷新成功后原请求重试一次，失败则清理 session 并触发 `odirag:auth-expired`。

## 4. 核心类与文件

- `frontend/src/main.ts`、`App.vue`：应用入口。
- `frontend/src/router/index.ts`：懒加载业务路由、登录守卫和过期跳转。
- `frontend/src/auth/state.ts`：登录、bootstrap、logout 和 reactive user 状态。
- `frontend/src/api/client.ts`：sessionStorage、fetch、单飞刷新、结构化 `ApiError`。
- `frontend/src/api/resources.ts`：全部后端资源函数。
- `frontend/src/api/types.ts`：手工维护的请求/响应 TypeScript 类型。
- `frontend/src/layouts/AppShell.vue`：导航、健康状态、移动菜单和 60 秒轮询。
- `frontend/src/components/AsyncState.vue`、`StatusBadge.vue`、`MarkdownContent.vue`、`ModalDialog.vue` 等共享组件。
- `frontend/src/views/`：Dashboard、Sources、CrawlTasks、Documents、DocumentDetail、Reviews、Chat、Evaluations、Experiments、Monitoring、Activity、Login。
- `frontend/src/styles/main.css`：完整布局和响应式样式。
- `frontend/src/**/*.spec.ts`：API、认证、Markdown、状态与反馈行为测试。

## 5. 主要设计决策

1. 所有页面调用 `api/resources.ts`，不在组件中散落 URL 和认证逻辑。
2. API client 把后端错误 envelope 转为包含 status/code/details/requestId 的 `ApiError`。
3. access/refresh token 存在 `sessionStorage`，关闭标签页后失效；logout 先请求后端撤销，再保证本地清理。
4. 路由按页面懒加载，未登录用户保留 redirect 参数。
5. `AsyncState` 统一 loading/error/empty/retry，避免页面无反馈。
6. Markdown 使用 `marked` 渲染并经 DOMPurify 清洗，不能直接 `v-html` 输出模型文本。
7. 状态不只依赖颜色，`StatusBadge` 同时显示文本。
8. 当前实际实现使用原生 `fetch`、Vue reactive module 和定制 CSS；没有使用指南目标栈中的 Axios、Pinia、Element Plus/Naive UI 或 ECharts，这必须按现状说明。
9. API 类型目前手工维护，后端 schema 变更需要同步更新。

## 6. 技术选型原因

- Vue 3 Composition API：页面状态和异步操作可以用小型可组合函数组织。
- TypeScript + vue-tsc：在构建前发现响应字段和组件 props 错误。
- Vue Router：受保护路由、深链接和页面懒加载。
- Lucide Vue：统一可访问图标，不维护自绘 SVG。
- marked + DOMPurify：兼顾回答可读性和 XSS 防护。
- Vitest + Vue Test Utils：与 Vite 构建链一致，适合组件和 API client 单测。
- 原生 fetch：当前依赖较少，但相较 Axios 需要自行维护刷新、错误和超时逻辑。

## 7. 常见故障模式

- 页面循环回登录：access token 过期且 refresh 已被轮换/注销，或 `/auth/me` 失败。
- 多请求同时 401：应只有一个 refresh；若仍多次刷新，检查 `refreshPromise` 生命周期。
- 后端返回新字段但 UI 类型错误：`api/types.ts` 与 Pydantic schema 漂移。
- Markdown XSS：检查内容是否始终经过 `MarkdownContent` 和 DOMPurify。
- 健康状态一直 unavailable：`AppShell` 公共 `/system/health` 请求失败或 Nginx `/api` 代理错误。
- 监控页等待较久：health 会等待不可用依赖的 timeout，需要保留 loading 而非误报空数据。
- 移动端横向滚动：检查 table/grid 的 min-width、`minmax(0, ...)` 和文本换行。
- sessionStorage 不跨标签页同步；当前没有 BroadcastChannel 或集中状态库。
- 大部分业务页面尚无独立组件测试，也没有自动化 Playwright E2E。

## 8. 调试步骤

1. 浏览器 Network 查看 `/api` 路径、Authorization 和后端 request ID。
2. 在 Session Storage 检查 `odirag.session` 是否包含两个 token，但不要复制到日志。
3. 模拟 access 401，确认只有一个 `/auth/refresh` 且原请求最多重试一次。
4. 检查 `ApiError.code`，不要只显示 `fetch failed`。
5. 对空页面依次确认 loading、error、empty 条件，防止状态互相覆盖。
6. 用桌面与 390px 移动 viewport 检查导航、表格、弹窗和最长文本。
7. 运行 `npm run type-check`、`npm run lint`、`npm test`、`npm run build`。
8. 若后端契约变化，先改 `api/types.ts` 和 `resources.ts`，再修页面。

## 9. 面试问题与参考答案

### 9.1 为什么刷新请求要 single-flight？

多个并发请求同时 401 时，如果各自刷新，refresh rotation 会让后续刷新 token 立即失效。共享 Promise 保证只轮换一次。

### 9.2 为什么不用 localStorage？

sessionStorage 生命周期更短且按标签页隔离，降低长期残留；但两者都可被同源 XSS 读取，所以仍需严格 CSP、DOMPurify 和短 token 生命周期。

### 9.3 前端如何处理后端结构化错误？

`responseError()` 解析 `error.message/code/details/request_id` 为 `ApiError`，页面可显示可理解信息并把 requestId 用于日志定位。

### 9.4 Markdown 为什么需要清洗？

回答内容可能来自外部模型或文档，不可信。Markdown 转 HTML 后必须移除脚本、事件属性和危险 URL，否则 `v-html` 会形成 XSS。

### 9.5 手工 API 类型的风险是什么？

后端 Pydantic schema 改动不会自动更新前端，容易运行时漂移。更稳妥的后续方案是从 OpenAPI 生成类型并在 CI 检查差异。

## 10. 答辩问题与参考答案

### 10.1 如何证明前端不是 mock？

所有视图通过 `api/resources.ts` 调真实 FastAPI。真实浏览器 QA 已完成登录、RAG/SQL/拒答、引用、trace、反馈写入和 Activity 回显。

### 10.2 前端能否直接读取 Qdrant？

不能。它只请求 `/api`；向量库、数据库和模型凭据都在后端 Provider/Service 层，符合边界要求。

### 10.3 logout 在网络断开时怎么办？

后端撤销请求会失败，但 `finally` 仍清理本地 session；服务器 token 只能等待过期，这是网络不可达时的诚实限制。

### 10.4 当前是否使用 Pinia 和 Axios？

没有。认证用 Vue reactive module，HTTP 用 fetch。文档按实际实现说明；若严格对齐目标栈，可在后续重构，但不能声称已使用。

### 10.5 前端测试覆盖是否充分？

最终验收记录包含 18 个 Vitest 测试、10 个 fixture Playwright 场景、1 个明确跳过的
live-stack 场景，以及公网 HTTPS 的真实 headless Chrome 验收。覆盖仍不算充分：多数业务
页面缺少独立组件测试，类型尚未从 OpenAPI 生成，生产后端全流程也不应由 fixture E2E
替代。

## 11. 代码阅读路线

1. `frontend/src/main.ts` 与 `App.vue`
2. `frontend/src/router/index.ts`
3. `frontend/src/api/client.ts`
4. `frontend/src/auth/state.ts`
5. `frontend/src/api/types.ts`、`resources.ts`
6. `frontend/src/layouts/AppShell.vue`
7. 共享组件
8. 按 Dashboard -> Documents -> Chat -> Evaluation -> Monitoring 顺序读 views
9. 对应 Vitest 测试和 `main.css`

## 12. 实践修改练习

从 `/api/openapi.json` 自动生成 TypeScript API 类型，并在 CI 中验证生成结果无差异。保留现有 `apiRequest` 的 refresh/error 行为，逐步把 `api/types.ts` 的手工接口替换为生成类型，并为一个后端字段变更编写失败再修复的契约测试。
