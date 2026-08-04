from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Protocol

from app.crawler.fetcher import Fetcher
from app.crawler.generic import CrawledDocument, GenericCrawler
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
        for index, item in enumerate(payload[: max_pages * page_size]):
            if not isinstance(item, dict) or not isinstance(item.get("URL"), str):
                continue
            if index and request_interval_seconds:
                await asyncio.sleep(request_interval_seconds)
            document = await self.detail_parser.parse_detail(
                normalize_url(item["URL"], base_url=response.url), selectors
            )
            published = item.get("DOCRELPUBTIME")
            if not document.publish_date_text and isinstance(published, str):
                document = replace(document, publish_date_text=published)
            documents.append(document)
        return documents
