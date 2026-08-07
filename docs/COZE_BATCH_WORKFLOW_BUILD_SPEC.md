# `batch_crawl` Coze 工作流节点级施工说明

版本：`v1`  
适用部署：复制现有单篇筛选工作流后，新建的 Coze Coding 部署  
调用方式：`POST https://<new-deployment>.coze.site/run`，`Authorization: Bearer <token>`  
重要边界：现有 `https://c6z3nhnzg7.coze.site/run` 是 `legacy_single_article`，不要修改、不要用它宣称批量抓取已验收。
本地栏目任务对该契约返回 `422 COZE_LEGACY_SINGLE_ARTICLE_ONLY`；只有新部署可作为 `batch_crawl` 任务目标。

本文是控制台施工规格，不是 Live 验收证明。Coze 未发布新部署前，所有本地测试只能标为 fixture/contract verified。

## 1. 整体节点图

按以下顺序在 Coze 中连接节点。节点类型写在括号内：`HTTP` 为 HTTP 请求，`CODE` 为代码，`LLM` 为大模型，`LOOP` 为循环，`BRANCH` 为条件分支，`AGG` 为变量聚合。

```text
开始节点 (INPUT)
  -> 参数校验 (CODE)
  -> URL 规范化 (CODE)
  -> 栏目首页请求 (HTTP)
  -> URL 类型识别 (LLM)
  -> 页面结构识别 (LLM)
  -> 文章链接提取 (LLM)
  -> 链接绝对化/去重 (CODE)
  -> 翻页策略分支 (BRANCH)
       -> 下一页 URL 生成 (CODE) -> 栏目首页请求 (LOOP)
       -> 页码 URL 生成 (CODE)   -> 栏目首页请求 (LOOP)
       -> 动态加载不支持 (AGG warning)
  -> max_pages/max_articles 截断 (CODE)
  -> 文章循环 (LOOP)
       -> 详情页请求 (HTTP)
       -> 详情字段提取 (LLM)
       -> 正文/图片判断 (LLM)
       -> 附件链接提取 (CODE)
       -> 附件循环 (LOOP)
            -> 附件请求/解析 (HTTP + CODE)
       -> 质量判断 (LLM)
       -> 单篇结果标准化 (CODE)
       -> 文章结果聚合 (AGG)
  -> 失败 URL 聚合 (AGG)
  -> 统计计算 (CODE)
  -> 最终 JSON 组装 (CODE)
  -> 结束节点 (OUTPUT)
```

### 节点职责和运行参数

| 顺序 | 节点 | 类型 | 输入 | 输出 | 失败分支 | 重试/超时 |
|---:|---|---|---|---|---|---|
| 1 | 开始节点 | INPUT | 见第 2 节 | `input` 对象 | 结束节点返回 `INVALID_INPUT` | 不重试 |
| 2 | 参数校验 | CODE | `input` | `validated_input`、`warnings[]` | 非法 URL/类型进入失败聚合 | 不重试，2 秒 |
| 3 | URL 规范化 | CODE | `validated_input.source_url` | `normalized_source_url` | 非法 URL 终止，不发 HTTP | 不重试，2 秒 |
| 4 | 栏目首页请求 | HTTP | `normalized_source_url` | `status_code`、`final_url`、`html`、`content_type` | `SOURCE_FETCH_FAILED` | 最多 2 次，20 秒/次 |
| 5 | URL 类型识别 | LLM | `normalized_source_url`、首页标题/面包屑/HTML 摘要 | `url_kind`、`confidence` | 置信度低时按栏目页尝试并加 warning | 1 次，30 秒 |
| 6 | 页面结构识别 | LLM | `html`、`url_kind` | `list_selector`、`next_page`、`pagination_mode` | 结构未知时 warning，仍尝试通用链接 | 1 次，30 秒 |
| 7 | 文章链接提取 | LLM | 页面 HTML、结构信息 | `candidate_links[]` | 空列表进入无文章分支 | 1 次，30 秒 |
| 8 | 绝对化/去重 | CODE | `candidate_links[]` | `article_links[]` | 单链接解析失败只记 warning | 不重试，2 秒 |
| 9 | 翻页分支 | BRANCH/CODE | `pagination_mode` | 下一页或停止 | 翻页请求失败进入失败聚合并保留已发现链接 | 每页最多 2 次，20 秒 |
| 10 | 数量截断 | CODE | 去重链接、限制参数 | `selected_links[]` | 无链接返回 `NO_ARTICLES` | 不重试，2 秒 |
| 11 | 文章循环 | LOOP | `selected_links[]` | 单篇结果数组 | 单篇异常进入 `failed_urls[]`，循环继续 | 并发/总时长由平台限制 |
| 12 | 详情页请求 | HTTP | 单篇 URL | HTML/内容类型 | `ARTICLE_FETCH_FAILED` | 最多 2 次，20 秒 |
| 13 | 详情字段提取 | LLM | HTML、URL、来源元数据 | 标题、日期、正文、附件候选 | 字段缺失保留 null 并 warning | 1 次，30 秒 |
| 14 | 正文/图片判断 | LLM | 正文候选、图片节点 | `extraction_method`、`needs_ocr` | 不得把图片正文改成空正文 | 1 次，30 秒 |
| 15 | 附件链接提取 | CODE | 详情 HTML、字段结果 | `attachments[]` | 解析失败只记 warning | 不重试，2 秒 |
| 16 | 附件循环 | LOOP | 附件列表 | 附件结果 | 单附件失败不丢弃文章 | 每附件 1 次，30 秒 |
| 17 | 质量判断 | LLM | 标题、正文、附件摘要、旧规则 | 决策字段 | 模型异常为 `pending_review` 或单篇 failed | 1 次，30 秒 |
| 18 | 单篇标准化 | CODE | LLM 字段、附件、warning | 严格 `ArticleResult` | Schema 错误进入单篇 failed | 不重试，2 秒 |
| 19 | 结果聚合 | AGG | 单篇结果 | `articles[]` | 保留已完成结果 | 不重试 |
| 20 | 失败聚合 | AGG | 所有失败事件 | `failed_urls[]` | 保留错误码和 retryable | 不重试 |
| 21 | 统计计算 | CODE | articles、failed_urls、页计数 | `statistics` | 计数必须由数组计算 | 不重试，2 秒 |
| 22 | JSON 组装 | CODE | 所有标准字段 | 最终对象 | 缺关键字段返回 `success=false` | 不重试，2 秒 |

HTTP 节点只负责受限请求和响应传递；确定性 URL、计数、去重和聚合必须放在代码节点，不能交给模型凭感觉完成。对于需要 JavaScript 执行的页面，第一阶段不绕过限制，返回 `DYNAMIC_CONTENT_UNSUPPORTED` warning。

### 1.1 控制台变量绑定与连线条件

在 Coze 中使用以下稳定节点 ID 命名节点；变量名照表填写，避免后续本地契约无法定位失败阶段。

| 节点 ID | 直接上游 | 读取变量 | 写出变量 | 下一跳条件 |
|---|---|---|---|---|
| `N00_START` | 无 | 开始节点全部字段 | `input` | 总是到 `N01_VALIDATE` |
| `N01_VALIDATE` | `N00_START` | `input` | `validated_input`、`validation_errors[]`、`warnings[]` | 无错误到 `N02_CANONICALIZE_SOURCE`；有错误到 `N22_OUTPUT_ERROR`，不得执行 HTTP |
| `N02_CANONICALIZE_SOURCE` | `N01_VALIDATE` | `validated_input.source_url` | `normalized_source_url` | 成功到 `N03_FETCH_LIST_PAGE`；失败到 `N22_OUTPUT_ERROR` |
| `N03_FETCH_LIST_PAGE` | `N02` 或 `N09_NEXT_PAGE` | `current_page_url` | `page_status`、`page_final_url`、`page_content_type`、`page_html` | 2xx HTML 到 `N04_CLASSIFY_URL`（首轮）或 `N05_PAGE_STRUCTURE`（后续页）；失败到 `N19_FAILURES` |
| `N04_CLASSIFY_URL` | `N03_FETCH_LIST_PAGE` 首轮 | URL、标题、面包屑、前 12,000 字符 HTML | `url_kind`、`url_kind_confidence`、`url_kind_reason` | 总是到 `N05_PAGE_STRUCTURE` |
| `N05_PAGE_STRUCTURE` | `N04` 或后续页 `N03` | `page_final_url`、`page_html`、`url_kind` | `candidate_links[]`、`next_page_url`、`pagination_mode`、`page_warnings[]` | 到 `N06_FILTER_LINKS` |
| `N06_FILTER_LINKS` | `N05` | 页面 URL/HTML、候选链接、来源 host | `filtered_links[]`、`link_warnings[]` | 到 `N07_CANONICALIZE_LINKS` |
| `N07_CANONICALIZE_LINKS` | `N06` | `filtered_links[]`、已发现集合 | `discovered_links[]`、`duplicate_count` | 到 `N08_PAGE_BRANCH` |
| `N08_PAGE_BRANCH` | `N07` | `pagination_mode`、页计数、`next_page_url` | `continue_pages` | `continue_pages=true` 到 `N09_NEXT_PAGE`；否则到 `N10_LIMIT_LINKS` |
| `N09_NEXT_PAGE` | `N08` | 下一页信息、已访问页集合 | `current_page_url` | 回到 `N03_FETCH_LIST_PAGE`；禁止访问已出现的规范 URL |
| `N10_LIMIT_LINKS` | `N08` | `discovered_links[]`、`max_articles` | `selected_links[]` | 非空到 `N11_ARTICLE_LOOP`；空到 `N20_STATISTICS` 并加入 `NO_ARTICLES` |
| `N11_ARTICLE_LOOP` | `N10` | `selected_links[]` | `article_url`（逐项） | 每项到 `N12_FETCH_ARTICLE`；单项完成后继续下一项 |
| `N12_FETCH_ARTICLE` | `N11` | `article_url` | `article_status`、`article_content_type`、`article_html` | 2xx 到 `N13_EXTRACT_FIELDS`；失败写入 `N19_FAILURES` 后继续循环 |
| `N13_EXTRACT_FIELDS` | `N12` | HTML、URL、来源元数据 | `raw_fields` | 到 `N14_CONTENT_KIND` |
| `N14_CONTENT_KIND` | `N13` | 正文、图片、附件候选 | `content_kind`、`needs_ocr`、`content_warnings[]` | 到 `N15_ATTACHMENT_LINKS` |
| `N15_ATTACHMENT_LINKS` | `N14` | HTML、`raw_fields.attachments` | `attachment_links[]` | 非空到 `N16_ATTACHMENT_LOOP`；空到 `N17_QUALITY` |
| `N16_ATTACHMENT_LOOP` | `N15` | 单个附件 URL | `attachments[]` | 每项完成后回到循环；循环结束到 `N17_QUALITY` |
| `N17_QUALITY` | `N16` 或 `N15` | 字段、正文、附件、质量参数 | `quality_result` | 到 `N18_NORMALIZE_ARTICLE` |
| `N18_NORMALIZE_ARTICLE` | `N17` | 单篇全部中间值 | 严格 `article_result` | 合法结果加入 `N19_ARTICLES`；非法结果加入 `N19_FAILURES`；随后继续 `N11` |
| `N19_ARTICLES` / `N19_FAILURES` | 多个单篇分支 | 单篇结果/失败事件 | `articles[]`、`failed_urls[]` | 文章循环完成后到 `N20_STATISTICS` |
| `N20_STATISTICS` | `N10` 或 `N19` | 数组和页计数 | `statistics`、`batch_success` | 到 `N21_ASSEMBLE` |
| `N21_ASSEMBLE` | `N20` | 全部最终变量 | `batch_result` | 到 `N22_OUTPUT` |
| `N22_OUTPUT` | `N21` | `batch_result` | 唯一 JSON 对象 | 结束 |
| `N22_OUTPUT_ERROR` | `N01` 或 `N02` | 输入校验错误 | 平台校验失败 | 结束；不伪造满足批量 schema 的成功响应 |

循环必须满足以下停止条件：页循环在 `pages_visited == max_pages`、没有下一页、下一页重复或动态加载不支持时停止；文章循环最多执行 `max_articles` 次；附件循环每篇最多 10 个附件。所有聚合数组由 AGG 节点追加，不允许 LLM 重写已有元素。HTTP 节点仅接受 `http/https`，响应正文上限 5 MiB，重定向最多 5 次；超限记录可追踪失败，不把截断内容当完整正文。

## 2. 开始节点字段

开始节点直接接收一个 JSON 对象。只有 `task_id` 和 `source_url` 必填，其余字段有默认值；不要增加隐式必填的工作流变量。

| 字段 | 类型 | 必填 | 默认值 | 说明 | 示例 |
|---|---|:---:|---|---|---|
| `task_id` | string | 是 | 无 | 本地任务 ID；部署入口在工作流节点运行前执行类型校验，因此调用方必须发送非空字符串 | `"1842"` |
| `source_url` | string | 是 | 无 | 网站首页、栏目页或列表页 URL | `"https://scsia.org/industry"` |
| `source_name` | string | 否 | `null` | 来源名称，未知时 null | `"四川省软件行业协会"` |
| `region` | string | 否 | `null` | 地区 | `"四川省"` |
| `column_name` | string | 否 | `null` | 栏目名称 | `"行业动态"` |
| `max_articles` | integer | 否 | `5` | 第一阶段最大文章数，范围 1-100 | `5` |
| `max_pages` | integer | 否 | `1` | 最大列表页数，范围 1-100；首次 Live 验收固定为 1 | `1` |
| `minimum_content_length` | integer | 否 | `3000` | 有效正文长度提示，不替代质量判断 | `3000` |
| `start_date` | string/null | 否 | `null` | ISO 日期下限 | `"2026-01-01"` |
| `end_date` | string/null | 否 | `null` | ISO 日期上限 | `"2026-12-31"` |
| `include_html` | boolean | 否 | `true` | 是否保存 HTML 正文 | `true` |
| `include_pdf` | boolean | 否 | `true` | 是否处理 PDF 附件 | `true` |
| `include_docx` | boolean | 否 | `true` | 是否处理 DOC/DOCX 附件 | `true` |
| `include_xlsx` | boolean | 否 | `true` | 是否处理 XLS/XLSX 附件 | `true` |
| `deduplicate` | boolean | 否 | `true` | URL、标题、正文指纹去重 | `true` |
| `crawl_rules` | object | 否 | `{}` | 已批准的站点规则，不放秘密 | `{}` |
| `quality_rules` | object | 否 | `{}` | 仅允许覆盖阈值，不得关闭硬过滤 | `{}` |

UTF-8 是请求和响应的唯一编码。真实部署入口已验证会在 `N01_VALIDATE` 运行前拒绝数字 `task_id`，因此本地调用方和所有工作流节点都只传字符串，结束节点也必须作为字符串回传。

## 3. 栏目与文章发现

1. 先解析 URL 的 scheme、host、path；`http` 可在工作流内升级为 `https` 并记录 warning，其他 scheme 直接 `INVALID_URL`。
2. `url_kind` 允许 `homepage`、`column`、`list`、`article`、`unknown`。输入详情页时先从面包屑、栏目链接或站点导航寻找所属列表；无法找到时把该页作为单篇候选并标记 `SOURCE_URL_IS_ARTICLE`。
3. 所有链接使用基准 URL 绝对化，删除 fragment；只删除明确的跟踪参数（`utm_*`、`spm`、`from`、`share`），保留业务查询参数。host 小写、默认端口删除、path 合并重复斜线。
4. 文章候选必须是同站或明确官方关联域名；导航、登录、搜索、下载按钮、图片、脚本、mailto、javascript 和锚点不是文章候选。
5. 翻页按优先级处理：明确 `next` 链接、`rel=next`、页码链接、`page/pn/pageIndex` 参数。每次请求前检查已经访问过的规范 URL；超过 `max_pages` 停止。
6. 动态加载列表如果 HTML 没有文章链接，不能假设抓取成功；返回 `DYNAMIC_CONTENT_UNSUPPORTED`。对已知存在文章的 SPA 返回 `NO_ARTICLES` 属于误分类和验收失败。
7. `max_articles` 在 URL 去重后截断，顺序保持页面出现顺序；`deduplicate=false` 只关闭批内指纹，不得关闭安全 URL 规范化。

## 4. 文章详情与附件

每篇输出字段（与本地 `BatchArticle` 严格 Pydantic 契约一致）：

`url`、`title`、`published_at`、`organization`、`organization_inferred`、`region`、`column_name`、`content`、`content_length`、`attachments[]`、`accepted`、`quality_score`、`decision`、`decision_reason`、`document_type`、`summary`、`keywords[]`、`extraction_method`、`needs_ocr`、`image_urls[]`、`image_count`、`image_alt_texts[]`、`warnings[]`。不要额外返回 `external_id` 或其他未列出的字段。

正文为空、乱码或只有导航时 `content` 使用空字符串，不能编造；无法确认日期使用 `null`；机构未知使用 `null`，若从来源元数据推断必须在 warning 写明 `organization_inferred_from_source`。

附件对象必须包含：

```json
{
  "name": "规范.pdf",
  "url": "https://example.org/files/spec.pdf",
  "file_type": "pdf",
  "extracted_text": "",
  "download_status": "success",
  "error_message": null
}
```

支持 `pdf`、`doc`、`docx`、`xls`、`xlsx` 和图片。`file_type` 可以是字符串或 `null`；大小超过工作流限制返回 `too_large`，不支持格式返回 `unsupported`，请求失败返回 `failed`，尚未处理返回 `pending`，已处理也可返回 `completed`；这些状态均保留 URL 和错误信息，不能丢弃文章。正文主要由图片组成时必须返回 `extraction_method="image"`、`needs_ocr=true`，并保存图片 URL、数量、alt 文本和 warning `ocr_required`。

## 5. 质量判断规则

质量节点继续使用旧工作流规则，扩展为新字段，不另造一套互相冲突的标准：

- 标题含“征求”立即 `rejected`，类型为“征求意见材料”，不下载附件。
- 正文读取失败、严重不完整，且可能存在有效附件时 `pending_review`；没有可复核材料时仍保留单篇失败原因。
- 会议、培训、报名、竞赛、合同模板、表格、协会内部制度、纯广告、招聘、祝福和明显无关内容 `rejected`。
- “关于印发《办法》的通知”不能仅因“通知”拒绝；若正文含完整办法、政策、正式标准或技术规范，继续判断。
- `accepted` 要求来源官方或可验证、主题相关、正文具有可独立复用的政策、数据、技术、标准、研究、项目方法或成果知识。
- 只有时间、地点、人员、议程、费用、联系方式、报名和宣传口号不构成知识价值。
- 正文短于 `minimum_content_length` 不是自动拒绝；结合正文完整性和附件判断。无法确定时 `pending_review`。
- 日期不在 `start_date/end_date` 范围时 `rejected`，日期未知时不得伪造。
- 重复文章、同正文不同 URL 或明显导航模板进入 `rejected`，并记录 `duplicate_content` warning。

输出 `quality_score` 为 0-100 的数值或 `null`；无法稳定判断时 `decision=pending_review`。`decision` 只允许 `accepted`、`rejected`、`pending_review`、`failed`。

## 6. 最终 JSON 契约

结束节点必须输出一个 JSON 对象，不能有 Markdown 围栏、前后解释或额外文本。下面是结构示例（字段名即契约）：

```json
{
  "success": true,
  "task_id": "1842",
  "source": {
    "source_url": "https://scsia.org/industry",
    "source_name": "四川省软件行业协会",
    "region": "四川省",
    "organization": "四川省软件行业协会",
    "column_name": "行业动态"
  },
  "statistics": {
    "pages_visited": 1,
    "articles_discovered": 5,
    "articles_fetched": 4,
    "articles_accepted": 2,
    "articles_rejected": 1,
    "articles_pending_review": 1,
    "articles_failed": 1
  },
  "articles": [],
  "failed_urls": [],
  "warnings": [],
  "workflow_version": "batch_crawl-v1",
  "started_at": "2026-08-04T09:00:00Z",
  "completed_at": "2026-08-04T09:02:00Z"
}
```

`articles` 中每项必须满足 `ArticleResult` schema；`failed_urls` 每项必须包含 `url`、`stage`、`error_code`、`error_message`、`retryable`。完整 Draft 2020-12 JSON Schema 位于 `docs/coze_batch_test_cases/batch_crawl_result.schema.json`。本地 Provider 对 HTTP 响应先保存 raw JSON，再进行 Pydantic 校验；顶层非法 JSON、缺少 `success/task_id/articles/statistics` 或类型错误时任务为 `failed`，但 raw response 仍可追踪。文章级失败允许批次 `success=true`，本地任务状态改为 `partial_failed`。

`BatchCrawlResult` 是严格业务对象。真实 `coze.site/run` transport 已观察到外层
`{"run_id":"...","batch_result":{...}}`；这不是业务 schema 的新增字段。后端保存完整 raw envelope，
只解包并校验 `batch_result`。直接返回业务对象以及历史 `data/output/result` 包装仍由兼容解析器支持，
但工作流不得在业务对象外添加自然语言或 Markdown。

请求和响应的 `task_id` 都是 strict non-empty string。后端在发网前校验请求，并在任何文章持久化前
核对响应 ID 与请求 ID；主批次和失败 URL 重试只要不一致就记录 `COZE_TASK_ID_MISMATCH`、终止处理且
不保存文档。工作流必须原样回传该值，不能生成新 ID、转换为数字或复用上一轮响应。

全零发现/抓取计数且没有失败项时，只有两种输入可使用终态 `completed` 和
`provider_status=no_articles`：业务结果明确包含 `NO_ARTICLES`，或 provider 明确返回 `success=true`
的干净空批次。其他 `success=false` 空结果属于 `partial_failed`。无论哪种 no-articles 形式，Live
Acceptance 对已知有内容的栏目仍要求至少一个真实持久化文档，因此该状态不会被误当成内容验收通过。
`SPA_API_NOT_DISCOVERED` 属于明确的能力缺口：即使 `failed_count=0` 且没有 provider error，只要批次
`success=false` 且未产出文章，本地任务必须为 `partial_failed/provider_status=partial_failed`，不能降级为
`no_articles`。

## 7. 可复制 Prompt

以下 Prompt 均要求 UTF-8、只输出合法 JSON、不得编造；缺失字段使用 `null`、空数组或空字符串，并加入 warning。

### 7.1 URL 类型识别

```text
你是 URL 分类节点。输入变量：source_url、page_title、breadcrumbs、html_excerpt。
只输出 {"url_kind":"homepage|column|list|article|unknown","confidence":0,"reason":""}。
不要访问网络，不要编造页面内容；无法确定时返回 unknown 和低 confidence。
```

### 7.2 栏目结构识别

```text
你是栏目结构识别节点。输入变量：normalized_source_url、url_kind、html。
只输出 {"article_link_hints":[],"next_page_url":null,"pagination_mode":"next_link|page_param|page_links|none|dynamic|unknown","warnings":[]}。
链接必须来自输入 HTML；不要生成未出现过的域名或路径。动态内容不可见时返回 dynamic 并加 DYNAMIC_CONTENT_UNSUPPORTED。
```

### 7.3 文章链接筛选

```text
你是文章链接筛选节点。输入变量：page_url、html、candidate_links、source_host。
只输出 {"links":[{"url":"","title_hint":"","external_id":null}],"warnings":[]}。
排除导航、登录、搜索、图片、脚本、下载按钮和 javascript/mailto；保留同站文章详情链接。不能凭空补 URL。
```

### 7.4 详情字段提取

```text
你是详情字段提取节点。输入变量：article_url、source_name、region、column_name、html。
只输出 title、published_at、organization、content、attachments、warnings 五类字段；日期不确定为 null，正文不存在为 ""，机构推断必须写 warning。不得改写或补造正文。
```

### 7.5 正文完整性判断

```text
你是正文完整性节点。输入变量：title、content、content_length、image_urls、alt_texts、attachments。
只输出 {"extraction_method":"html|pdf|doc|docx|xls|xlsx|image|mixed","needs_ocr":false,"content_complete":false,"warnings":[]}。
图片主体必须 needs_ocr=true；不要把图片正文判成普通空正文；不得编造 OCR 内容。
```

### 7.6 文章质量筛选

```text
你是行业知识质量节点。输入变量：title、content、published_at、organization、source_name、region、column_name、attachments、minimum_content_length、start_date、end_date。
严格按旧规则：标题含“征求”先拒绝；会议/培训/报名/合同/表格/内部制度/广告/无关内容拒绝；正文不完整或附件可能承载知识时 pending_review；只有可独立复用的政策、数据、技术、标准、研究、项目方法或成果才可接受。
只输出 decision(accepted|rejected|pending_review|failed)、accepted(boolean)、quality_score(0-100)、decision_reason、document_type、summary、keywords、warnings。不得编造证据。
```

### 7.7 结果标准化

```text
你是结果校验前的字段整理节点。输入变量：raw_article_result、article_url、task_id。
只输出符合 ArticleResult 字段的 JSON；缺失值使用 null/[]/""，不修改原始 URL，不把自然语言包在 JSON 外。无法满足类型时 decision=failed 并写 schema_error warning。
```

### 7.8 最终 JSON 聚合

```text
你是批次聚合节点。输入变量：task_id、source、articles、failed_urls、pages_visited、started_at、completed_at。
统计必须由数组和失败列表确定性计算。只输出最终 BatchCrawlResult JSON，不输出 Markdown 或解释文字；即使部分文章失败也保留成功文章和 failed_urls。
```

## 8. 代码节点示例

下面代码可改写为 Coze 代码节点使用；它只做确定性处理，不承担网络或质量判断。

```python
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import hashlib

TRACKING_KEYS = {"spm", "from", "share"}

def canonical_url(base: str, href: str) -> str | None:
    absolute = urljoin(base, href.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k not in TRACKING_KEYS and not k.lower().startswith("utm_")]
    path = parts.path or "/"
    while "//" in path:
        path = path.replace("//", "/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path,
                       urlencode(query, doseq=True), ""))

def unique_links(base: str, links: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for href in links:
        url = canonical_url(base, href)
        if url and url not in seen:
            seen.add(url)
            result.append(url)
        if len(result) >= limit:
            break
    return result

def content_fingerprint(text: str) -> str:
    normalized = " ".join((text or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def calculate_statistics(articles: list[dict], failed_urls: list[dict], pages: int) -> dict:
    decisions = [a.get("decision") for a in articles]
    return {
        "pages_visited": pages,
        "articles_discovered": len(articles) + len(failed_urls),
        "articles_fetched": len(articles),
        "articles_accepted": decisions.count("accepted"),
        "articles_rejected": decisions.count("rejected"),
        "articles_pending_review": decisions.count("pending_review"),
        "articles_failed": decisions.count("failed") + len(failed_urls),
    }
```

### 8.1 参数校验节点

`N01_VALIDATE` 使用下面的确定性代码。它只生成标准输入或校验错误；出现错误时走
`N22_OUTPUT_ERROR`，不得调用任何 HTTP 节点。

```python
from urllib.parse import urlsplit

def validate_input(value: dict) -> dict:
    errors: list[str] = []
    task_id = str(value.get("task_id", "")).strip()
    source_url = str(value.get("source_url", "")).strip()
    parts = urlsplit(source_url)
    if not task_id:
        errors.append("INVALID_TASK_ID")
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        errors.append("INVALID_URL")
    max_articles = value.get("max_articles", 5)
    max_pages = value.get("max_pages", 1)
    if not isinstance(max_articles, int) or isinstance(max_articles, bool) or not 1 <= max_articles <= 100:
        errors.append("INVALID_MAX_ARTICLES")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 100:
        errors.append("INVALID_MAX_PAGES")
    start_date = value.get("start_date")
    end_date = value.get("end_date")
    if start_date and end_date and str(end_date) < str(start_date):
        errors.append("INVALID_DATE_RANGE")
    normalized = {
        "task_id": task_id,
        "source_url": source_url,
        "source_name": value.get("source_name"),
        "region": value.get("region"),
        "column_name": value.get("column_name"),
        "max_articles": max_articles,
        "max_pages": max_pages,
        "minimum_content_length": value.get("minimum_content_length", 3000),
        "start_date": start_date,
        "end_date": end_date,
        "include_html": value.get("include_html", True),
        "include_pdf": value.get("include_pdf", True),
        "include_docx": value.get("include_docx", True),
        "include_xlsx": value.get("include_xlsx", True),
        "deduplicate": value.get("deduplicate", True),
        "crawl_rules": value.get("crawl_rules") or {},
        "quality_rules": value.get("quality_rules") or {},
    }
    return {"validated_input": normalized, "validation_errors": errors, "warnings": []}
```

### 8.2 最终组装和输出节点

`N21_ASSEMBLE` 必须使用代码节点，不使用 LLM。`source` 固定只包含 schema 中的五个字段；
文章数组已经在 `N18_NORMALIZE_ARTICLE` 去除额外字段。时间使用 UTC ISO-8601。

```python
from datetime import datetime, timezone

def assemble_result(task_id, source, articles, failed_urls, warnings, pages, started_at):
    statistics = calculate_statistics(articles, failed_urls, pages)
    return {
        "success": bool(articles),
        "task_id": str(task_id),
        "source": {
            "source_url": source["source_url"],
            "source_name": source.get("source_name"),
            "region": source.get("region"),
            "organization": source.get("organization"),
            "column_name": source.get("column_name"),
        },
        "statistics": statistics,
        "articles": articles,
        "failed_urls": failed_urls,
        "warnings": warnings,
        "contract_version": "1.0",
        "workflow_version": "batch_crawl-v1",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
```

`N22_OUTPUT` 的输出模式选择“对象/JSON”，唯一输出变量绑定 `N21_ASSEMBLE.batch_result`；
不要把变量放入 Markdown 代码块，不要添加说明文本。`N22_OUTPUT_ERROR` 只用于开始参数非法，
在 Coze 控制台中应显示明确校验失败并停止；它不伪造一个能通过正常批量 schema 的结果。
Coze 部署 API 可以自动把该对象放入 `batch_result` transport 字段；不要在 `N21_ASSEMBLE` 中手工
再套一层同名字段，否则会形成双重包装。

## 9. 测试和验收

控制台试运行至少覆盖 `docs/coze_batch_test_cases/` 中的十组输入。工作流发布后，在本机未提交的 `.env` 中填写 `COZE_ENABLED=true`、新的 `COZE_BATCH_API_URL` 和 `COZE_API_TOKEN`；旧部署如需保留测试则单独填写 `COZE_LEGACY_API_URL`。不要配置 `workflow_id` 或 Coze 远端轮询变量，当前部署是同步 `coze.site/run`。

启动后端、worker 和界面：

```powershell
docker compose build backend
docker compose build frontend
docker compose --profile async --profile ui up -d --no-build
python scripts/live_accept_coze_batch.py --source-column-id <column_id>
```

脚本通过认证 API 创建真实 `queued` 任务，固定发送 `provider=coze`、`contract_mode=batch_crawl`、`max_articles=5` 和 `max_pages=1`，随后只轮询本地任务状态。管理员密码未在环境变量中提供时，交互式输入不会回显；脚本永远不输出 token、部署 URL、请求头或 Coze raw response。

成功时退出码为 0，单行 JSON 的 `status` 为 `live_batch_verified`，并包含 `task_id`、`task_status`、`accepted_count`、`rejected_count`、`pending_review_count`、`failed_count`、`batch_invocation_count` 和脱敏 HTTP 状态。没有新批量 URL 时退出码为 2，输出必须是 `{"status":"batch_workflow_not_published"}`；不能宣称 Live 成功。

2026-08-06 真实诊断：task 4 因数字 `task_id` 被入口拒绝；task 5 观察到真实 `batch_result`
transport；task 6 在两项本地修复后 HTTP 200 且 invocation completed，但对
`https://scsia.org/Industry_information/Industry_information_1` 返回 `NO_ARTICLES` 和全零计数。
公开站点 API 已证明该栏目有 69 条记录，因此 task 6 是内容验收 FAIL，不是成功样例。工作流应先修复
动态页面识别（至少返回 `DYNAMIC_CONTENT_UNSUPPORTED` 或更具体的诊断），再重新发布并执行同一限量验收。

2026-08-07 task 7 live-diagnostic 镜像 `sha256:2bcc5e6530c673d4736c35f19a79c84a39bf3004c81fe48c27655d5457d4746b`
已滚动到 backend/worker/scheduler，task 7 再次调用真实部署并得到
HTTP 200、invocation `completed`、task `completed/provider_status=no_articles`。文档、chunk 和 Qdrant
point 仍全部为 0，验收脚本返回 `status=batch_result_empty`、exit code 1。该结果只验证 transport、
响应解包和 no-articles 终态，不改变上述内容验收 FAIL；施工完成标准仍是发现并持久化真实文章，或对
不支持的动态页面明确返回 `DYNAMIC_CONTENT_UNSUPPORTED`。

同日后续生产审查将 canonical request/response schema 收紧为 strict string，并在主批次和失败 URL
重试路径增加 fail-closed ID 匹配。当前运行镜像为 `sha256:7f090ada232d349cdf8999be1308f26192cc297627a51972dca9920fb6bbc7a7`，
并已通过本地回归、Compose rollout 与 Scout。

新 Coze 部署后的 task 8 是当前最新真实诊断证据：HTTP 200、invocation `completed`、attempts `1`、
retries `0`、duration `4141 ms`，normalized `task_id` 是 string `"8"`，workflow version 是
`batch_crawl-v1`。worker 正常完成执行，但业务任务为 `partial_failed/provider_status=partial_failed`，
没有 provider error。statistics 只有 `pages_visited=1`，其余发现、抓取、审核和失败计数均为 0；
warning `SPA_API_NOT_DISCOVERED` 明确说明只取得基础 HTML、没有发现 API。数据库为一条 invocation、
0 persisted failures/documents/chunks，Qdrant 为 0 collection，验收 `batch_result_empty`、exit code 1。
这比 task 7 的 `NO_ARTICLES` 更可诊断，但仍是内容验收 FAIL。

独立 API 验证已把下一次云端修复范围收窄：

- `https://scsia.org/portal/news/264?pageNum=1&pageSize=5` 返回 HTTP 200 JSON、`total=69`、五行；
- 首行 ID 为 `7587`，`https://scsia.org/portal/new/7587` 返回 data，`newsContent` 长度为 995；
- 仓库只记录结构、ID、计数和长度，不保存正文。

针对该已验证站点规则，工作流应让列表节点按 `max_pages`/`max_articles` 有界调用 list JSON API，
从 rows 提取文章 ID，再调用 detail JSON API 并映射到规范 `articles[]`；所有 URL 仍需通过既有域名、
协议、重定向和响应大小限制。下一次 bounded acceptance 至少必须返回一个真实 article 并形成持久化文档；
只返回 `SPA_API_NOT_DISCOVERED`、HTTP 200 或 completed invocation 仍不能通过。

task 8 后本地监控打开 `high_failure_rate` high/open 告警（observed `0.4`，threshold `0.2`），相关
回归 `49 passed`。该告警证明失败可见，不证明生产告警投递和恢复闭环。

## 10. 施工后的人工检查清单

1. 在 Coze 中复制旧工作流，不改旧部署。
2. 将开始节点输入变量改为第 2 节，只有 `task_id` 和 `source_url` 必填。
3. 按第 1 节加入 HTTP、循环、代码、分支和聚合节点。
4. 将旧质量判断 Prompt 的硬过滤规则复制到第 7.6 节节点。
5. 将结束节点设为严格 JSON 输出，禁止自然语言包裹。
6. 用十组测试输入逐项试运行，并检查 `needs_ocr`、部分失败和中文 UTF-8。
7. 发布为新的 `coze.site/run` 地址，单独配置 `COZE_BATCH_API_URL`。
8. 按第 9 节先执行 5 篇/1 页 Live Acceptance；真实结果未出现前保持未验收状态。
