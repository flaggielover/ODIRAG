from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Protocol

import httpx

from app.crawler.fetcher import Fetcher
from app.crawler.generic import (
    CrawlColumnResult,
    CrawlDiagnostics,
    CrawledDocument,
    CrawlFailure,
    GenericCrawler,
)
from app.crawler.urls import normalize_url


class CrawlerAdapter(Protocol):
    async def crawl_column(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        request_interval_seconds: int,
    ) -> list[CrawledDocument]: ...

    async def crawl_column_with_diagnostics(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        request_interval_seconds: int,
        max_articles: int | None = None,
    ) -> CrawlColumnResult: ...


class GovCnLatestJsonAdapter:
    """Adapter for the public latest-policy JSON feed on www.gov.cn."""

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self.detail_parser = GenericCrawler(fetcher)

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
            request_interval_seconds=request_interval_seconds,
            max_articles=None,
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
        response = await self.fetcher.fetch(normalize_url(column_url))
        payload = json.loads(response.text)
        if not isinstance(payload, list):
            raise ValueError("gov.cn latest-policy feed must be a JSON array")
        raw_page_size = pagination.get("page_size", 20)
        if isinstance(raw_page_size, bool) or not isinstance(raw_page_size, (int, str)):
            raise ValueError("page_size must be a positive integer")
        page_size = int(raw_page_size)
        if page_size <= 0:
            raise ValueError("page_size must be a positive integer")
        documents: list[CrawledDocument] = []
        failures: list[CrawlFailure] = []
        limit = max_pages * page_size
        if max_articles is not None:
            limit = min(limit, max_articles)
        candidates: list[dict[str, object]] = []
        for item in payload[:limit]:
            if isinstance(item, dict) and isinstance(item.get("URL"), str):
                candidates.append(item)
        for index, item in enumerate(candidates):
            if not isinstance(item, dict) or not isinstance(item.get("URL"), str):
                continue
            if index and request_interval_seconds:
                await asyncio.sleep(request_interval_seconds)
            detail_url = normalize_url(item["URL"], base_url=response.url)
            try:
                document = await self.detail_parser.parse_detail(detail_url, selectors)
            except Exception as exc:
                failures.append(
                    CrawlFailure(
                        url=detail_url,
                        stage="detail",
                        error_code=(
                            "DETAIL_SCHEMA_UNKNOWN"
                            if "selector" in str(exc).lower()
                            else "ARTICLE_FETCH_FAILED"
                        ),
                        error_message=str(exc)[:500] or exc.__class__.__name__,
                        retryable=isinstance(exc, (httpx.TimeoutException, TimeoutError)),
                    )
                )
                continue
            published = item.get("DOCRELPUBTIME")
            if not document.publish_date_text and isinstance(published, str):
                document = replace(document, publish_date_text=published)
            documents.append(document)
        diagnostics = CrawlDiagnostics(
            pages_visited=1,
            candidate_links=tuple(
                {
                    "url": normalize_url(str(item["URL"]), base_url=response.url),
                    "anchor_text": str(item.get("TITLE", "")),
                    "score": 1,
                    "reasons": ["govcn_json_item"],
                }
                for item in candidates
            ),
            normalized_links=tuple(
                normalize_url(str(item["URL"]), base_url=response.url) for item in candidates
            ),
            page_classifications=(
                {
                    "url": normalize_url(response.url),
                    "kind": "json_api",
                    "status_code": response.status_code,
                },
            ),
            pagination_events=(
                {"page": 1, "stop": "max_pages" if max_pages <= 1 else "feed_limit"},
            ),
            api_discovery={
                "mode": "configured",
                "endpoint": normalize_url(response.url),
                "items": len(candidates),
            },
            warnings=("NO_ARTICLES",) if not documents and not failures else (),
            failures=tuple(failures),
        )
        return CrawlColumnResult(tuple(documents), diagnostics)
