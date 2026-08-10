from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.crawler.fetcher import Fetcher, FetchResponse
from app.crawler.site_rules import site_rules_from_configs
from app.crawler.urls import UnsafeUrlError, normalize_url

_ARTICLE_PATH_TERMS = (
    "/art/",
    "/article/",
    "/content/",
    "/detail/",
    "/news/",
    "/xxgk/",
    "/zwgk/",
    "/zc/",
    "/zcwj/",
    "/zcfg/",
    "/tzgg/",
    "/wjfb/",
    "/notice/",
    "/公告/",
    "/通知/",
)
_ARTICLE_TEXT_TERMS = (
    "通知",
    "公告",
    "政策",
    "规定",
    "办法",
    "意见",
    "方案",
    "规划",
    "标准",
    "条例",
    "细则",
    "解读",
    "名单",
    "公示",
    "批复",
    "决定",
    "报告",
    "article",
    "policy",
    "notice",
    "announcement",
)
_NAVIGATION_TERMS = (
    "登录",
    "注册",
    "搜索",
    "分享",
    "首页",
    "返回顶部",
    "打印",
    "字体",
    "上一页",
    "下一页",
    "next",
    "prev",
    "更多",
    "网站地图",
    "备案",
    "隐私",
    "联系我们",
)
_NEXT_TERMS = ("下一页", "下页", "后一页", "next", "下一篇")
_PAGE_PARAMETERS = ("page", "p", "pagenum", "page_num", "pageindex", "page_index", "pn")
_NON_ARTICLE_EXTENSIONS = (
    ".css",
    ".js",
    ".json",
    ".xml",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp4",
    ".mp3",
    ".wav",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
    ".rar",
)
_ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".txt",
        ".zip",
        ".rar",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
    }
)
_DATE_PATH_RE = re.compile(r"/(?:19|20)\d{2}(?:[-_/]\d{1,2}){0,2}(?:/|$)")
_NUMERIC_ID_RE = re.compile(r"(?:^|[/_-])\d{3,}(?:$|[/_.-])")
_API_HINT_RE = re.compile(
    r"[\"'](?P<url>(?:https?://[^\"']+|/[^\"']*(?:api|ajax|json)[^\"']*))[\"']",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CrawledAttachment:
    name: str
    url: str
    file_type: str | None = None


@dataclass(frozen=True, slots=True)
class CrawledDocument:
    title: str
    url: str
    raw_html: str
    text: str
    publish_date_text: str | None
    attachments: tuple[CrawledAttachment, ...]
    extraction_method: str = "html"
    needs_ocr: bool = False
    image_urls: tuple[str, ...] = ()
    image_alt_texts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    discovery_score: int = 0


@dataclass(frozen=True, slots=True)
class CrawlFailure:
    url: str
    stage: str
    error_code: str
    error_message: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class CrawlDiagnostics:
    pages_visited: int
    candidate_links: tuple[dict[str, Any], ...] = ()
    normalized_links: tuple[str, ...] = ()
    page_classifications: tuple[dict[str, Any], ...] = ()
    pagination_events: tuple[dict[str, Any], ...] = ()
    api_discovery: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()
    failures: tuple[CrawlFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class CrawlColumnResult:
    documents: tuple[CrawledDocument, ...]
    diagnostics: CrawlDiagnostics


@dataclass(frozen=True, slots=True)
class CandidateLink:
    url: str
    anchor_text: str
    score: int
    reasons: tuple[str, ...]
    api_item: Mapping[str, Any] | None = None


@dataclass(slots=True)
class _DiscoveryState:
    candidates: list[CandidateLink]
    visited_pages: list[str]
    normalized_links: list[str]
    page_classifications: list[dict[str, Any]]
    pagination_events: list[dict[str, Any]]
    warnings: list[str]
    failures: list[CrawlFailure]
    api_discovery: dict[str, Any] | None = None
    api_documents: list[CrawledDocument] | None = None


class CrawlDiscoveryError(ValueError):
    """A bounded list/API discovery failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class GenericCrawler:
    """Deterministic crawler for government HTML columns and configured JSON APIs.

    The crawler keeps the old selector contract, but treats selectors as hints.  A
    broad ``a[href]`` selector therefore receives deterministic URL/text scoring,
    while a narrow selector (for example ``a.article-title``) remains authoritative.
    """

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    async def crawl_column(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        request_interval_seconds: int,
    ) -> list[CrawledDocument]:
        result = await self.crawl_column_with_diagnostics(
            column_url=column_url,
            selectors=selectors,
            pagination=pagination,
            max_pages=max_pages,
            max_articles=None,
            request_interval_seconds=request_interval_seconds,
        )
        return list(result.documents)

    async def crawl_column_with_diagnostics(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        request_interval_seconds: int,
        max_articles: int | None = None,
    ) -> CrawlColumnResult:
        if max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        if max_articles is not None and max_articles < 1:
            raise ValueError("max_articles must be a positive integer")
        state = await self._discover_result(
            column_url=column_url,
            selectors=selectors,
            pagination=pagination,
            max_pages=max_pages,
            max_articles=max_articles,
            request_interval_seconds=request_interval_seconds,
        )
        documents: list[CrawledDocument] = []
        candidates = state.candidates
        if max_articles is not None:
            candidates = candidates[:max_articles]
        for index, candidate in enumerate(candidates):
            if max_articles is not None and len(documents) >= max_articles:
                break
            if index and request_interval_seconds:
                await asyncio.sleep(request_interval_seconds)
            try:
                if candidate.api_item is not None and _api_item_has_content(candidate.api_item):
                    document = self._document_from_api_item(candidate.api_item, candidate.url)
                else:
                    document = await self.parse_detail(candidate.url, selectors)
                documents.append(_with_discovery_score(document, candidate.score))
            except Exception as exc:
                state.failures.append(
                    CrawlFailure(
                        url=candidate.url,
                        stage="detail",
                        error_code=_classify_detail_error(exc),
                        error_message=_safe_error_message(exc),
                        retryable=_retryable_exception(exc),
                    )
                )
        if max_articles is not None:
            documents = documents[:max_articles]
        diagnostics = CrawlDiagnostics(
            pages_visited=len(state.visited_pages),
            candidate_links=tuple(
                {
                    "url": item.url,
                    "anchor_text": item.anchor_text,
                    "score": item.score,
                    "reasons": list(item.reasons),
                }
                for item in state.candidates
            ),
            normalized_links=tuple(state.normalized_links),
            page_classifications=tuple(state.page_classifications),
            pagination_events=tuple(state.pagination_events),
            api_discovery=state.api_discovery,
            warnings=tuple(dict.fromkeys(state.warnings)),
            failures=tuple(state.failures),
        )
        return CrawlColumnResult(tuple(documents), diagnostics)

    async def _discover(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        request_interval_seconds: int,
    ) -> list[str]:
        """Compatibility wrapper retained for callers and older tests."""

        state = await self._discover_result(
            column_url=column_url,
            selectors=selectors,
            pagination=pagination,
            max_pages=max_pages,
            max_articles=None,
            request_interval_seconds=request_interval_seconds,
        )
        return [candidate.url for candidate in state.candidates]

    async def _discover_result(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        max_articles: int | None,
        request_interval_seconds: int,
    ) -> _DiscoveryState:
        site_rules = site_rules_from_configs(selectors, pagination)
        if not site_rules.enabled:
            raise CrawlDiscoveryError(
                "SITE_ADAPTER_DISABLED",
                "the configured site adapter is disabled",
                retryable=False,
            )
        selectors = _merge_selector_rules(selectors, site_rules)
        pagination = {**site_rules.merged(), **pagination}
        current_url: str | None = normalize_url(column_url)
        base_host = str(urlsplit(current_url).hostname or "").lower().rstrip(".")
        visited_pages: set[str] = set()
        state = _DiscoveryState([], [], [], [], [], [], [])
        seen_details: set[str] = set()
        no_new_pages = 0
        page_limit = max_articles if max_articles is not None else 10_000
        for page_index in range(max_pages):
            if current_url is None or current_url in visited_pages:
                if current_url in visited_pages:
                    state.warnings.append("PAGINATION_LOOP_GUARD")
                break
            if len(state.candidates) >= page_limit:
                state.pagination_events.append({"stop": "max_articles", "page": page_index})
                break
            if page_index and request_interval_seconds:
                await asyncio.sleep(request_interval_seconds)
            visited_pages.add(current_url)
            try:
                response = await self.fetcher.fetch(current_url)
            except Exception as exc:
                code = "PAGINATION_FAILED" if page_index else _classify_list_error(exc)
                failure = CrawlFailure(
                    url=current_url,
                    stage="pagination" if page_index else "list",
                    error_code=code,
                    error_message=_safe_error_message(exc),
                    retryable=_retryable_exception(exc),
                )
                state.failures.append(failure)
                if page_index:
                    state.warnings.append(code)
                    break
                if isinstance(exc, UnsafeUrlError):
                    raise
                raise CrawlDiscoveryError(code, str(exc), retryable=failure.retryable) from exc
            state.visited_pages.append(normalize_url(response.url))
            soup = BeautifulSoup(response.text, "lxml")
            state.page_classifications.append(_classify_page(response, soup))
            before = len(state.candidates)
            candidates = _extract_candidates(
                soup,
                response.url,
                base_host=base_host,
                selectors=selectors,
                pagination=pagination,
                current_url=current_url,
            )
            for candidate in candidates:
                if candidate.url not in seen_details:
                    seen_details.add(candidate.url)
                    state.candidates.append(candidate)
                    state.normalized_links.append(candidate.url)
                    if len(state.candidates) >= page_limit:
                        break
            if before == len(state.candidates):
                no_new_pages += 1
            else:
                no_new_pages = 0
            if (
                not state.candidates
                and page_index == 0
                and _looks_like_detail_page(soup, response.url, selectors)
            ):
                direct = CandidateLink(
                    normalize_url(response.url),
                    soup.title.get_text(" ", strip=True) if soup.title else response.url,
                    100,
                    ("detail_url_fallback",),
                )
                state.candidates.append(direct)
                state.normalized_links.append(direct.url)
            if not state.candidates and page_index == 0:
                await self._discover_api_fallback(
                    response=response,
                    soup=soup,
                    selectors=selectors,
                    pagination=pagination,
                    base_host=base_host,
                    state=state,
                    seen_details=seen_details,
                    page_limit=page_limit,
                    request_interval_seconds=request_interval_seconds,
                )
            if len(state.candidates) >= page_limit:
                state.pagination_events.append(
                    {
                        "page": page_index + 1,
                        "stop": "max_articles",
                        "new_candidates": before != len(state.candidates),
                    }
                )
                break
            if no_new_pages >= _int_config(pagination, "stop_after_no_new_pages", 2):
                state.pagination_events.append(
                    {"page": page_index + 1, "stop": "no_new_articles", "new_candidates": 0}
                )
                break
            current_url = _find_next_page(
                soup,
                response.url,
                pagination,
                visited_pages=visited_pages,
            )
            state.pagination_events.append(
                {
                    "page": page_index + 1,
                    "next_url": current_url,
                    "new_candidates": len(state.candidates) - before,
                }
            )
            if current_url is None:
                break
        if not state.candidates and not state.failures:
            state.warnings.append("NO_ARTICLES")
        return state

    async def _discover_api_fallback(
        self,
        *,
        response: FetchResponse,
        soup: BeautifulSoup,
        selectors: dict[str, object],
        pagination: dict[str, object],
        base_host: str,
        state: _DiscoveryState,
        seen_details: set[str],
        page_limit: int,
        request_interval_seconds: int,
    ) -> None:
        config = _api_config(selectors, pagination)
        endpoint = config.get("list_endpoint") or config.get("endpoint")
        hints: list[str] = []
        if isinstance(endpoint, str) and endpoint.strip():
            hints.append(endpoint.strip())
        else:
            hints = _discover_api_hints(response.text, response.url)
        if not hints:
            state.warnings.append("SPA_API_NOT_DISCOVERED")
            return
        state.api_discovery = {
            "mode": "configured" if endpoint else "inline_hint",
            "candidates": hints[:10],
            "requests": 0,
            "items": 0,
        }
        state.api_documents = []
        for hint_index, hint in enumerate(hints[:3]):
            try:
                api_url = normalize_url(hint, base_url=response.url)
                page_url = api_url
                for page_index in range(_int_config(pagination, "api_max_pages", 100)):
                    if page_index and request_interval_seconds:
                        await asyncio.sleep(request_interval_seconds)
                    if page_url in state.visited_pages:
                        break
                    api_response = await self.fetcher.fetch(page_url)
                    state.visited_pages.append(normalize_url(api_response.url))
                    state.api_discovery["requests"] += 1
                    payload = json.loads(api_response.text)
                    items = _extract_api_items(payload, config, base_url=api_response.url)
                    state.api_discovery["items"] += len(items)
                    if not items:
                        break
                    for item in items:
                        candidate = _candidate_from_api_item(item, config, api_response.url)
                        if candidate is None or candidate.url in seen_details:
                            continue
                        if not _same_site(base_host, (urlsplit(candidate.url).hostname or "")):
                            continue
                        seen_details.add(candidate.url)
                        state.candidates.append(candidate)
                        state.normalized_links.append(candidate.url)
                        if len(state.candidates) >= page_limit:
                            break
                    if len(state.candidates) >= page_limit:
                        break
                    next_api = _next_api_url(payload, page_url, config, page_index)
                    if next_api is None or next_api in state.visited_pages:
                        break
                    page_url = next_api
                if state.candidates:
                    break
            except (json.JSONDecodeError, ValueError, httpx.HTTPError) as exc:
                state.failures.append(
                    CrawlFailure(
                        url=hint,
                        stage="api",
                        error_code=(
                            "SPA_API_REQUEST_FAILED" if hint_index else "LIST_SCHEMA_UNKNOWN"
                        ),
                        error_message=_safe_error_message(exc),
                        retryable=_retryable_exception(exc),
                    )
                )
        if not state.candidates:
            state.warnings.append("SPA_API_REQUEST_FAILED" if state.failures else "NO_ARTICLES")

    async def parse_detail(self, url: str, selectors: dict[str, object]) -> CrawledDocument:
        response = await self.fetcher.fetch(url)
        return self.parse_detail_response(response, selectors)

    def parse_detail_response(
        self, response: FetchResponse, selectors: dict[str, object]
    ) -> CrawledDocument:
        soup = BeautifulSoup(response.text, "lxml")
        title_selector = _optional_selector(selectors, "title")
        content_selector = _optional_selector(selectors, "content")
        title_element = _select_first(
            soup, title_selector, ("h1", "h2", "meta[property='og:title']", "title")
        )
        content_element = _select_first(
            soup,
            content_selector,
            (
                "article",
                "main",
                "[role='main']",
                ".article",
                ".content",
                ".detail",
                ".TRS_Editor",
                ".pages_content",
                ".article-content",
                ".news-content",
                "#UCAP-CONTENT",
                "#content",
            ),
        )
        if title_element is None:
            raise ValueError("DETAIL_SCHEMA_UNKNOWN: title selector did not match")
        if content_element is None:
            raise ValueError("DETAIL_SCHEMA_UNKNOWN: content selector did not match")
        # Work on the selected subtree so navigation/share/related links never
        # become part of the indexed source text.
        for node in content_element.select(
            "script,style,noscript,nav,header,footer,aside,form,.share,.print,.related,.pager,.pagination"
        ):
            node.decompose()
        title = (
            _tag_value(title_element, "content")
            if title_element.name == "meta"
            else title_element.get_text(" ", strip=True)
        )
        title = title.strip()
        text = content_element.get_text("\n", strip=True)
        date_selector = _optional_selector(selectors, "publish_date")
        date_element = _select_first(
            soup,
            date_selector,
            ("time", "meta[property='article:published_time']", ".date", ".time"),
        )
        publish_date = (
            _tag_value(date_element, "content")
            if date_element is not None and date_element.name == "meta"
            else date_element.get_text(" ", strip=True) if date_element is not None else None
        )
        attachment_selector = _optional_selector(selectors, "attachment") or "a[href]"
        attachments: list[CrawledAttachment] = []
        seen_attachments: set[str] = set()
        for element in soup.select(attachment_selector):
            if not isinstance(element, Tag) or not element.get("href"):
                continue
            try:
                attachment_url = normalize_url(str(element["href"]), base_url=response.url)
            except ValueError:
                continue
            extension = _extension(attachment_url)
            if extension not in _ATTACHMENT_EXTENSIONS or attachment_url in seen_attachments:
                continue
            seen_attachments.add(attachment_url)
            attachments.append(
                CrawledAttachment(
                    element.get_text(" ", strip=True) or attachment_url.rsplit("/", 1)[-1],
                    attachment_url,
                    extension.lstrip(".") or None,
                )
            )
        image_urls: list[str] = []
        image_alt_texts: list[str] = []
        for image in content_element.select("img[src], img[data-src]"):
            if not isinstance(image, Tag):
                continue
            raw_url = image.get("src") or image.get("data-src")
            if not isinstance(raw_url, str) or not raw_url.strip():
                continue
            try:
                image_url = normalize_url(raw_url, base_url=response.url)
            except ValueError:
                continue
            if image_url not in image_urls:
                image_urls.append(image_url)
                alt = image.get("alt")
                if isinstance(alt, str) and alt.strip():
                    image_alt_texts.append(alt.strip())
        warnings: list[str] = []
        if attachments and len(text) < 300:
            warnings.append("SHORT_TEXT_WITH_ATTACHMENT")
        if image_urls and len(text) < 300:
            warnings.append("OCR_REQUIRED")
        if len(text) < 120 and image_urls:
            extraction_method = "image"
            needs_ocr = True
        elif image_urls:
            extraction_method = "mixed"
            needs_ocr = len(text) < 300
        else:
            extraction_method = "html"
            needs_ocr = False
        if not title or (not text and not attachments and not image_urls):
            raise ValueError("DETAIL_SCHEMA_UNKNOWN: title or content is empty")
        return CrawledDocument(
            title=title,
            url=normalize_url(response.url),
            raw_html=response.text,
            text=text,
            publish_date_text=publish_date,
            attachments=tuple(attachments),
            extraction_method=extraction_method,
            needs_ocr=needs_ocr,
            image_urls=tuple(image_urls),
            image_alt_texts=tuple(image_alt_texts),
            warnings=tuple(warnings),
        )

    def _document_from_api_item(self, item: Mapping[str, Any], url: str) -> CrawledDocument:
        content = _first_string(item, ("content", "正文", "body", "text")) or ""
        title = _first_string(item, ("title", "TITLE", "name", "subject")) or url
        published = _first_string(item, ("published_at", "publish_date", "date", "DOCRELPUBTIME"))
        attachments = _attachments_from_api_item(item, url)
        return CrawledDocument(
            title=title.strip(),
            url=normalize_url(url),
            raw_html=json.dumps(dict(item), ensure_ascii=False),
            text=content.strip(),
            publish_date_text=published,
            attachments=tuple(attachments),
            extraction_method="html",
            warnings=("API_CONTENT",) if content else ("API_DETAIL_REQUIRED",),
        )


def _with_discovery_score(document: CrawledDocument, score: int) -> CrawledDocument:
    return CrawledDocument(
        title=document.title,
        url=document.url,
        raw_html=document.raw_html,
        text=document.text,
        publish_date_text=document.publish_date_text,
        attachments=document.attachments,
        extraction_method=document.extraction_method,
        needs_ocr=document.needs_ocr,
        image_urls=document.image_urls,
        image_alt_texts=document.image_alt_texts,
        warnings=document.warnings,
        discovery_score=score,
    )


def _extract_candidates(
    soup: BeautifulSoup,
    page_url: str,
    *,
    base_host: str,
    selectors: Mapping[str, object],
    pagination: Mapping[str, object],
    current_url: str,
) -> list[CandidateLink]:
    selector = _optional_selector(selectors, "list_link")
    selected_ids: set[int] | None = None
    if selector and selector not in {"a", "a[href]", "a[href*='']"}:
        selected_ids = {id(item) for item in soup.select(selector) if isinstance(item, Tag)}
    minimum_score = _int_config(pagination, "candidate_min_score", 2)
    allow_subdomains = bool(pagination.get("allow_subdomains", True))
    candidates: list[CandidateLink] = []
    for element in soup.select("a[href]"):
        if not isinstance(element, Tag):
            continue
        if selected_ids is not None and id(element) not in selected_ids:
            continue
        raw_href = element.get("href")
        if not isinstance(raw_href, str) or _excluded_href(raw_href):
            continue
        try:
            url = normalize_url(raw_href, base_url=page_url)
        except ValueError:
            continue
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if not host or not _same_site(base_host, host, allow_subdomains=allow_subdomains):
            continue
        if url == current_url or _extension(url) in _NON_ARTICLE_EXTENSIONS:
            continue
        label = element.get_text(" ", strip=True)
        score, reasons = score_candidate(url=url, anchor_text=label, element=element)
        if _is_navigation_label(label) or (selected_ids is None and score < minimum_score):
            continue
        candidates.append(CandidateLink(url, label, score, tuple(reasons)))
    candidates.sort(key=lambda item: (-item.score, item.url))
    return candidates


def score_candidate(
    *, url: str, anchor_text: str, element: Tag | None = None
) -> tuple[int, list[str]]:
    """Return a deterministic article-likelihood score and explainable reasons."""

    parsed = urlsplit(url)
    path = parsed.path.lower()
    label = anchor_text.strip().lower()
    score = 0
    reasons: list[str] = []
    path_hits = [term.strip("/") for term in _ARTICLE_PATH_TERMS if term in path]
    if path_hits:
        score += min(6, 2 * len(path_hits))
        reasons.extend(f"path:{term}" for term in path_hits[:3])
    if _DATE_PATH_RE.search(path):
        score += 3
        reasons.append("path:date")
    if _NUMERIC_ID_RE.search(path):
        score += 1
        reasons.append("path:id")
    text_hits = [term for term in _ARTICLE_TEXT_TERMS if term.lower() in label]
    if text_hits:
        score += min(4, len(text_hits))
        reasons.extend(f"text:{term}" for term in text_hits[:4])
    if element is not None:
        classes = " ".join(_tag_values(element, "class"))
        parent_classes = " ".join(
            _tag_values(element.parent, "class") if isinstance(element.parent, Tag) else []
        )
        if any(
            term in f"{classes} {parent_classes}".lower()
            for term in ("list", "title", "item", "news")
        ):
            score += 1
            reasons.append("dom:list")
    if any(term in path for term in ("/list", "index.", "newschild", "common_list")):
        score -= 4
        reasons.append("path:directory")
    if not label:
        score -= 1
        reasons.append("text:empty")
    return score, reasons


def _find_next_page(
    soup: BeautifulSoup,
    page_url: str,
    pagination: Mapping[str, object],
    *,
    visited_pages: set[str],
) -> str | None:
    selectors: list[str] = []
    explicit = _optional_selector(pagination, "next_selector")
    if explicit:
        selectors.append(explicit)
    selectors.append("a[rel='next'], link[rel='next']")
    for selector in selectors:
        element = soup.select_one(selector)
        if isinstance(element, Tag) and element.get("href"):
            candidate = _safe_normalize(str(element["href"]), page_url)
            if candidate and candidate not in visited_pages:
                return candidate
    page_links: list[tuple[int, str]] = []
    current_page = _current_page_number(page_url, pagination)
    for element in soup.select("a[href]"):
        if not isinstance(element, Tag) or not element.get("href"):
            continue
        label = element.get_text(" ", strip=True).lower()
        aria = str(element.get("aria-label", "")).lower()
        if any(term in f"{label} {aria}" for term in _NEXT_TERMS):
            candidate = _safe_normalize(str(element["href"]), page_url)
            if candidate and candidate not in visited_pages:
                return candidate
        candidate_url = _safe_normalize(str(element["href"]), page_url)
        if candidate_url is None:
            continue
        number = _page_number(candidate_url, pagination)
        if number is not None and (current_page is None or number > current_page):
            page_links.append((number, candidate_url))
    if page_links:
        return min(page_links, key=lambda item: item[0])[1]
    page_param = _page_parameter(pagination, page_url)
    if page_param:
        next_number = (current_page or _int_config(pagination, "page_start", 1)) + 1
        return _replace_query(page_url, page_param, str(next_number))
    return None


def _api_config(
    selectors: Mapping[str, object], pagination: Mapping[str, object]
) -> dict[str, Any]:
    raw: object = (
        pagination.get("api") or pagination.get("site_rules") or selectors.get("site_rules") or {}
    )
    if not isinstance(raw, Mapping):
        return {}
    if isinstance(raw.get("list"), Mapping):
        merged = dict(raw)
        merged.update(dict(raw["list"]))
        return merged
    return dict(raw)


def _merge_selector_rules(selectors: Mapping[str, object], site_rules: object) -> dict[str, object]:
    values = dict(selectors)
    merged = getattr(site_rules, "list", {})
    detail = getattr(site_rules, "detail", {})
    if isinstance(merged, Mapping):
        for source_key, target_key in (("link_selector", "list_link"), ("list_link", "list_link")):
            value = merged.get(source_key)
            if target_key not in values and isinstance(value, str) and value.strip():
                values[target_key] = value
    if isinstance(detail, Mapping):
        for key in ("title", "content", "publish_date", "attachment"):
            value = detail.get(key)
            if key not in values and isinstance(value, str) and value.strip():
                values[key] = value
    return values


def _discover_api_hints(html: str, base_url: str) -> list[str]:
    hints: list[str] = []
    for match in _API_HINT_RE.finditer(html):
        value = match.group("url")
        candidate = _safe_normalize(value, base_url)
        if candidate and candidate not in hints:
            hints.append(candidate)
    return hints


def _extract_api_items(
    payload: Any, config: Mapping[str, Any], *, base_url: str
) -> list[Mapping[str, Any]]:
    current: Any = payload
    path = config.get("items_path")
    if isinstance(path, str) and path.strip():
        for part in path.strip(".").split("."):
            if isinstance(current, Mapping):
                current = current.get(part)
            else:
                current = None
                break
    if not isinstance(current, list):
        current = _find_item_list(payload)
    if not isinstance(current, list):
        return []
    return [item for item in current if isinstance(item, Mapping)]


def _find_item_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        if any(isinstance(item, Mapping) for item in value):
            return value
        for item in value:
            found = _find_item_list(item)
            if found:
                return found
    elif isinstance(value, Mapping):
        for nested in value.values():
            found = _find_item_list(nested)
            if found:
                return found
    return None


def _candidate_from_api_item(
    item: Mapping[str, Any], config: Mapping[str, Any], base_url: str
) -> CandidateLink | None:
    url_value = _first_string(
        item,
        (
            str(config.get("url_field", "")),
            "url",
            "URL",
            "link",
            "href",
            "article_url",
            "detail_url",
        ),
    )
    template = config.get("detail_url_template")
    if not url_value and isinstance(template, str):
        identifier = _first_string(item, (str(config.get("id_field", "id")), "id", "ID"))
        if identifier:
            try:
                values = dict(item)
                values["id"] = identifier
                url_value = template.format(**values)
            except (KeyError, IndexError):
                url_value = None
    if not url_value:
        return None
    url = _safe_normalize(url_value, base_url)
    if not url:
        return None
    title = (
        _first_string(
            item, (str(config.get("title_field", "")), "title", "TITLE", "name", "subject")
        )
        or ""
    )
    score, reasons = score_candidate(url=url, anchor_text=title)
    return CandidateLink(url, title, max(score, 2), tuple(["api_item", *reasons]), api_item=item)


def _next_api_url(
    payload: Any, current_url: str, config: Mapping[str, Any], page_index: int
) -> str | None:
    if isinstance(payload, Mapping):
        for key in ("next", "next_url", "nextPage", "next_page"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _safe_normalize(value, current_url)
        has_more = payload.get("has_more", payload.get("hasNext"))
        if has_more is False:
            return None
    page_param = str(config.get("page_param", "")).strip()
    if not page_param:
        return None
    page = _current_page_number(current_url, {"page_param": page_param}) or page_index + 1
    return _replace_query(current_url, page_param, str(page + 1))


def _api_item_has_content(item: Mapping[str, Any]) -> bool:
    return bool(_first_string(item, ("content", "正文", "body", "text")))


def _attachments_from_api_item(item: Mapping[str, Any], base_url: str) -> list[CrawledAttachment]:
    raw = item.get("attachments")
    if not isinstance(raw, list):
        return []
    result: list[CrawledAttachment] = []
    for attachment in raw:
        if not isinstance(attachment, Mapping):
            continue
        value = _first_string(attachment, ("url", "href", "source_url"))
        if not value:
            continue
        url = _safe_normalize(value, base_url)
        if not url:
            continue
        result.append(
            CrawledAttachment(
                _first_string(attachment, ("name", "title")) or url.rsplit("/", 1)[-1],
                url,
                _extension(url).lstrip(".") or None,
            )
        )
    return result


def _first_string(value: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if not key:
            continue
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _select_first(
    soup: BeautifulSoup, configured: str | None, fallbacks: tuple[str, ...]
) -> Tag | None:
    selectors = [configured] if configured else []
    selectors.extend(fallbacks)
    for selector in selectors:
        if not selector:
            continue
        try:
            element = soup.select_one(selector)
        except Exception as exc:
            raise ValueError(f"DETAIL_SCHEMA_UNKNOWN: invalid selector {selector!r}") from exc
        if isinstance(element, Tag):
            return element
    return None


def _looks_like_detail_page(soup: BeautifulSoup, url: str, selectors: Mapping[str, object]) -> bool:
    if selectors.get("detail_url") is True or selectors.get("mode") == "detail":
        return True
    if not (_DATE_PATH_RE.search(urlsplit(url).path) or _NUMERIC_ID_RE.search(urlsplit(url).path)):
        return False
    content = _select_first(
        soup,
        _optional_selector(selectors, "content"),
        ("article", "main", ".content", ".detail", ".pages_content", "#UCAP-CONTENT"),
    )
    if content is None:
        return False
    text_length = len(content.get_text(" ", strip=True))
    link_count = len(content.select("a[href]"))
    return text_length >= 180 and text_length > max(1, link_count) * 20


def _classify_page(response: FetchResponse, soup: BeautifulSoup) -> dict[str, Any]:
    content_type = response.content_type.lower()
    if "json" in content_type or response.text.lstrip().startswith(("{", "[")):
        kind = "json_api"
    elif soup.select_one("article, .article, .detail, .pages_content, #UCAP-CONTENT") is not None:
        kind = "html_detail_or_mixed"
    elif soup.select_one("a[href]") is not None:
        kind = "html_list_or_navigation"
    elif soup.select_one("script") is not None:
        kind = "spa_shell"
    else:
        kind = "unknown"
    return {"url": normalize_url(response.url), "kind": kind, "status_code": response.status_code}


def _excluded_href(value: str) -> bool:
    stripped = value.strip().lower()
    return not stripped or stripped.startswith(("javascript:", "mailto:", "tel:", "#"))


def _is_navigation_label(value: str) -> bool:
    label = value.strip().lower()
    return not label or any(term in label for term in _NAVIGATION_TERMS)


def _same_site(base_host: str, host: str, *, allow_subdomains: bool = True) -> bool:
    base = base_host.lower().rstrip(".")
    candidate = host.lower().rstrip(".")
    if not base or not candidate:
        return False
    if candidate == base:
        return True
    return allow_subdomains and (candidate.endswith("." + base) or base.endswith("." + candidate))


def _safe_normalize(value: str, base_url: str | None = None) -> str | None:
    try:
        return normalize_url(value, base_url=base_url)
    except ValueError:
        return None


def _extension(url: str) -> str:
    path = urlsplit(url).path.lower()
    if "." not in path.rsplit("/", 1)[-1]:
        return ""
    return "." + path.rsplit(".", 1)[-1]


def _int_config(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool):
        return default
    try:
        if not isinstance(value, (int, float, str)):
            return default
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _page_parameter(config: Mapping[str, object], url: str) -> str | None:
    explicit = config.get("page_param")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    keys = {key.lower() for key, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)}
    for key in _PAGE_PARAMETERS:
        if key in keys:
            return key
    return None


def _current_page_number(url: str, config: Mapping[str, object]) -> int | None:
    param = _page_parameter(config, url)
    if not param:
        return None
    for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if key.lower() == param.lower():
            try:
                number = int(value)
            except ValueError:
                return None
            return number if number >= 0 else None
    return None


def _page_number(url: str, config: Mapping[str, object]) -> int | None:
    return _current_page_number(url, config)


def _replace_query(url: str, key: str, value: str) -> str:
    parsed = urlsplit(url)
    query = [
        (name, item)
        for name, item in parse_qsl(parsed.query, keep_blank_values=True)
        if name != key
    ]
    query.append((key, value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError, httpx.ConnectError)):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in {408, 425, 429, 500, 502, 503, 504}


def _classify_list_error(exc: Exception) -> str:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "RATE_LIMITED" if "429" in str(exc) else "ARTICLE_FETCH_FAILED"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return "SOURCE_BLOCKED"
        if status == 429:
            return "RATE_LIMITED"
    return "ARTICLE_FETCH_FAILED"


def _classify_detail_error(exc: Exception) -> str:
    message = str(exc)
    if "DETAIL_SCHEMA_UNKNOWN" in message:
        return "DETAIL_SCHEMA_UNKNOWN"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in {401, 403}:
            return "SOURCE_BLOCKED"
        if exc.response.status_code == 429:
            return "RATE_LIMITED"
    if isinstance(exc, (httpx.TimeoutException, TimeoutError, httpx.ConnectError)):
        return "ARTICLE_FETCH_FAILED"
    return "ARTICLE_FETCH_FAILED"


def _safe_error_message(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:500] if text else exc.__class__.__name__


def _optional_selector(config: Mapping[str, object], name: str) -> str | None:
    value = config.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _tag_value(tag: Tag, name: str) -> str:
    value = tag.get(name)
    return value.strip() if isinstance(value, str) else ""


def _tag_values(tag: Tag, name: str) -> list[str]:
    value = tag.get(name)
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []
