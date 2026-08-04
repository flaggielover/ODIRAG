# 03 解析、清洗、去重与版本化

## 1. 模块目的

该模块把 HTML、PDF、DOCX、XLSX、TXT 和 ZIP 元数据转换为统一的 `ParsedArtifact`，清理噪声，计算内容指纹，并在内容变化时创建不可变版本和血缘记录。它为审查、分块和索引提供稳定正文。

## 2. 输入与输出

输入包括下载后的附件字节、文档 `raw_content`、文件名扩展名以及可选元数据更新。

输出包括：

- `ParsedArtifact.text`、sections、tables、pages、metadata 和 `requires_ocr`；
- 清洗后的 `Attachment.parsed_text`、页数和解析状态；
- 更新后的 `Document.content`、SHA256、SimHash、word_count、version 和 stale 索引状态；
- `DocumentVersion` 快照及对应 `DataLineage`；
- 内容未变化时 `changed=False` 的幂等结果。

## 3. 数据流

```text
附件字节或 raw HTML
  -> ParserRegistry 按扩展名选择 Parser
  -> ParsedArtifact
  -> clean_text()
  -> content_hash 比较
  -> 未变化：保持版本
  -> 有变化：保存旧/新快照，version + 1，index_status=stale
  -> DataLineage
```

`ParsingService.parse_attachment()` 使用线程池读取本地文件并运行同步解析器，避免阻塞事件循环。`reparse_html_document()` 则把存储的原始 HTML重新交给 `HtmlParser`，再由 `VersioningService` 决定是否创建新版本。

## 4. 核心类与文件

- `backend/app/parsers/base.py`：`ParsedArtifact`、`ParsedSection`、`ParsedTable` 和 `Parser` 协议。
- `backend/app/parsers/registry.py`：扩展名到解析器的映射。
- `backend/app/parsers/html.py`：正文根节点、标题、列表、表格和链接提取。
- `backend/app/parsers/pdf.py`：PyMuPDF 页面文本、页眉页脚消减、OCR 标记。
- `backend/app/parsers/docx.py`：段落、Heading、表格和 hyperlink relationship。
- `backend/app/parsers/xlsx.py`：read-only workbook、sheet 元数据、Markdown 表格和行字典。
- `backend/app/parsers/text.py`：UTF-8-SIG、GB18030、UTF-16 解码回退。
- `backend/app/parsers/zip_metadata.py`：只读目录元数据和不安全路径标记。
- `backend/app/cleaners/text.py`：NFKC、空白归一、样板行和重复段落清理。
- `backend/app/deduplication/core.py`：内容哈希、SimHash、汉明距离和权威来源选择。
- `backend/app/services/parsing.py`、`versioning.py`：解析状态和版本事务。
- `backend/app/repositories/documents.py`：文档、附件、版本和血缘访问。
- `backend/tests/unit/test_parsers_cleaning_dedup.py` 与 `backend/tests/integration/test_versioning_lineage.py`。

## 5. 主要设计决策

1. 所有解析器返回同一个不可变 `ParsedArtifact`，下游无需判断具体文件类型。
2. 表格转换为 Markdown，同时保留结构化 headers/rows，兼顾检索文本和结构数据。
3. PDF 按页保留文本并去掉多数页面重复的首尾行，方便后续引用页码。
4. PDF 文本过少时只设置 `requires_ocr=True`，当前没有伪造 OCR 结果。
5. ZIP 只枚举 metadata，不自动解压，避免 Zip Slip 和解压炸弹风险。
6. 精确去重使用去空白后的 SHA256；近重复使用 64 位 SimHash 和汉明距离。
7. 首次内容变化前保存原文快照，更新后保存新版本；索引立即标为 stale。
8. `choose_authoritative()` 已实现并测试，但当前抓取主链主要执行 URL 去重，完整语义近重复归并仍是待扩展边界。

## 6. 技术选型原因

- BeautifulSoup/lxml：适合清理 HTML 容器并使用 CSS selector。
- PyMuPDF：页面级文本提取速度快，并提供明确页面边界。
- python-docx：可读取 Word 样式、表格和底层 relationship。
- openpyxl read-only：降低大工作簿的内存占用，并可读取公式计算值。
- Unicode NFKC：统一全角/兼容字符，减少哈希和检索噪声。
- SHA256 + SimHash：前者判断完全相同，后者用低成本近似内容相似性。
- anyio thread offload：同步文件与解析库不会直接阻塞 FastAPI 事件循环。

## 7. 常见故障模式

- `unsupported parser extension`：文件后缀不在 `ParserRegistry`。
- PDF 页面为空：扫描件会 `requires_ocr=True`，但不会产生虚假文本。
- DOCX 标题未识别：段落样式不是 Heading 系列，需要检查实际 style name。
- XLSX 数据被截断：每个 sheet 默认最多读取 10,000 行。
- ZIP 中含 `../`：metadata 的 `unsafe_path=True`；当前不会解压。
- 文档内容看似变化但版本不变：`content_hash()` 会移除所有空白，纯排版变化被视为相同。
- 解析失败：附件 `parse_status=failed` 并记录异常类型，错误仍向调用者抛出。
- 新内容已入库但检索仍旧：应检查 `index_status=stale` 并执行 reindex。

## 8. 调试步骤

1. 先用 `ParserRegistry.get(filename)` 确认后缀分派。
2. 在测试中直接检查 `ParsedArtifact` 的 text、sections、tables、pages 和 metadata。
3. PDF 问题逐页比较原始提取文本与 `_remove_repeated_headers_and_footers()` 结果。
4. 清洗问题检查 NFKC 后字符、boilerplate 正则和段落指纹。
5. 版本问题比较旧 `content_hash` 与 `content_hash(clean_text(parsed.text))`。
6. 查询 `document_versions.changed_fields_json` 和 `data_lineage` 是否同时创建。
7. 若索引未更新，确认版本服务已将 `index_status` 设为 stale。
8. 定向运行：`python -m pytest tests/unit/test_parsers_cleaning_dedup.py tests/integration/test_versioning_lineage.py`。

## 9. 面试问题与参考答案

### 9.1 为什么不让每个解析器直接返回字符串？

下游还需要标题层级、表格、页码、链接和 OCR 状态。统一 `ParsedArtifact` 保留这些结构，同时让清洗和版本服务只依赖一个协议。

### 9.2 SHA256 和 SimHash 的职责有什么不同？

SHA256 适合判断规范化内容是否完全相同；SimHash 的汉明距离可快速发现轻微改写或模板差异的近重复文本。

### 9.3 为什么纯空白变化不创建新版本？

`content_hash()` 去除空白后计算哈希，避免网页排版调整造成无意义版本和索引重建。真实文字或元数据变化仍会记录。

### 9.4 如何避免解析器阻塞异步服务器？

解析库大多是同步 CPU/文件操作，`ParsingService` 通过 `anyio.to_thread.run_sync` 读取和执行，从事件循环移出。

### 9.5 为什么 ZIP 只读 metadata？

直接解压会引入路径穿越、压缩炸弹和嵌套归档风险。当前需求只保证 ZIP metadata 支持，因此诚实返回目录信息更安全。

## 10. 答辩问题与参考答案

### 10.1 如何证明版本可追溯？

集成测试更新同一文档后检查版本号、`DocumentVersion` 快照、changed_fields、stale 状态和 `DataLineage.document_version_id`。

### 10.2 扫描 PDF 能否被系统检索？

当前只能检测为 `requires_ocr`，没有内置 OCR 引擎，因此不能声称已提取扫描文字。后续应接入 OCR Provider 并保留页码与置信度。

### 10.3 权威来源如何选择？

`choose_authoritative()` 按 official、source_priority、发布日期、字数和稳定 ID 排序。但这一算法尚未完整接入抓取后的近重复归并流程，属于明确限制。

### 10.4 表格为什么转 Markdown？

Markdown 保留行列可读性，适合分块和模型上下文；同时 `ParsedTable.rows` 和 XLSX sheet metadata 保留结构化值供后续处理。

### 10.5 为什么更新后只标 stale，不直接同步重建索引？

版本事务必须先可靠落库，向量和 BM25 属于外部/派生状态。标 stale 允许异步重建并暴露一致性状态，而不是在事务中假装全部成功。

## 11. 代码阅读路线

1. `backend/app/parsers/base.py`
2. `backend/app/parsers/registry.py`
3. 依次阅读 HTML、PDF、DOCX、XLSX、TXT、ZIP 解析器
4. `backend/app/cleaners/text.py`
5. `backend/app/deduplication/core.py`
6. `backend/app/services/parsing.py`
7. `backend/app/services/versioning.py`
8. `backend/app/repositories/documents.py`
9. 解析单测与版本血缘集成测试

## 12. 实践修改练习

实现一个可注入的 `OcrProvider` 协议，并只在 `PdfParser` 标记 `requires_ocr` 后由 Service 调用。要求按页保存 OCR 文本和置信度，Provider 不可用时保留原附件及 `requires_ocr` 状态，新增确定性测试 Provider、失败测试和页码引用测试。
