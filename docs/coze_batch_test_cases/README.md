# `batch_crawl` 测试用例

每个输入 JSON 文件包含 `input` 和 `expected` 两部分；`sample_*_response.json` 是可直接送入本地 `BatchCrawlResponse` 校验器的响应样例。`expected` 是验收重点，不要求 Coze 返回完全相同的文章文本；任何未列出的字段仍必须符合 `BatchCrawlResult` schema。

| 文件 | 场景 | 核心验收 |
|---|---|---|
| `01_minimal_valid.json` | 最小合法输入 | 任务 ID 和 URL 原样回传，默认 5 篇/1 页 |
| `02_complete_input.json` | 完整输入 | 所有开关和日期被尊重 |
| `03_html_column.json` | 普通 HTML 栏目 | 发现并去重文章，至少一篇可提取正文 |
| `04_pdf_attachments.json` | PDF 附件 | 附件状态和 extracted_text 字段存在 |
| `05_no_articles.json` | 没有文章 | `success=false` 或 warning `NO_ARTICLES`，数组不伪造 |
| `06_partial_failed.json` | 部分失败 | 成功文章保留，`failed_urls` 完整，`articles_failed>0` |
| `07_image_content.json` | 图片正文 | `extraction_method=image` 且 `needs_ocr=true` |
| `08_utf8_chinese.json` | 中文内容 | 标题/正文不出现替换字符，JSON UTF-8 可解析 |
| `09_duplicate_links.json` | 重复链接 | canonical URL 去重后不重复入库 |
| `10_invalid_url.json` | 非法 URL | `INVALID_URL`，不发起外部请求 |

Live 试运行仍需在 Coze 控制台完成；这些文件不是 Live 成功证明。

本地契约检查：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit/test_coze_batch_samples.py -q
```

预期所有 `sample_*_response.json` 均能通过严格模型校验；该结果只能标记为
`fixture/contract verified`，不能替代真实新批量部署验收。
