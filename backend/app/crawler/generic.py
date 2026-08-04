from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from app.crawler.fetcher import Fetcher
from app.crawler.urls import normalize_url


@dataclass(frozen=True, slots=True)
class CrawledAttachment:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class CrawledDocument:
    title: str
    url: str
    raw_html: str
    text: str
    publish_date_text: str | None
    attachments: tuple[CrawledAttachment, ...]


class GenericCrawler:
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
        detail_urls = await self._discover(
            column_url=column_url,
            selectors=selectors,
            pagination=pagination,
            max_pages=max_pages,
            request_interval_seconds=request_interval_seconds,
        )
        documents: list[CrawledDocument] = []
        for index, detail_url in enumerate(detail_urls):
            if index and request_interval_seconds:
                await asyncio.sleep(request_interval_seconds)
            documents.append(await self.parse_detail(detail_url, selectors))
        return documents

    async def _discover(
        self,
        *,
        column_url: str,
        selectors: dict[str, object],
        pagination: dict[str, object],
        max_pages: int,
        request_interval_seconds: int,
    ) -> list[str]:
        link_selector = _required_selector(selectors, "list_link")
        next_selector = _optional_selector(pagination, "next_selector")
        current_url: str | None = normalize_url(column_url)
        visited_pages: set[str] = set()
        detail_urls: list[str] = []
        seen_details: set[str] = set()
        for page_index in range(max_pages):
            if current_url is None or current_url in visited_pages:
                break
            if page_index and request_interval_seconds:
                await asyncio.sleep(request_interval_seconds)
            visited_pages.add(current_url)
            response = await self.fetcher.fetch(current_url)
            soup = BeautifulSoup(response.text, "lxml")
            for element in soup.select(link_selector):
                if isinstance(element, Tag) and element.get("href"):
                    url = normalize_url(str(element["href"]), base_url=response.url)
                    if url not in seen_details:
                        seen_details.add(url)
                        detail_urls.append(url)
            current_url = None
            if next_selector:
                next_element = soup.select_one(next_selector)
                if isinstance(next_element, Tag) and next_element.get("href"):
                    current_url = normalize_url(str(next_element["href"]), base_url=response.url)
        return detail_urls

    async def parse_detail(self, url: str, selectors: dict[str, object]) -> CrawledDocument:
        response = await self.fetcher.fetch(url)
        soup = BeautifulSoup(response.text, "lxml")
        title_element = soup.select_one(_required_selector(selectors, "title"))
        content_element = soup.select_one(_required_selector(selectors, "content"))
        if title_element is None or content_element is None:
            raise ValueError(f"detail page does not match configured selectors: {url}")
        date_selector = _optional_selector(selectors, "publish_date")
        date_element = soup.select_one(date_selector) if date_selector else None
        attachment_selector = _optional_selector(selectors, "attachment") or "a[href]"
        attachments = []
        for element in content_element.select(attachment_selector):
            if not isinstance(element, Tag) or not element.get("href"):
                continue
            attachment_url = normalize_url(str(element["href"]), base_url=response.url)
            extension = urlsplit(attachment_url).path.lower().rsplit(".", 1)
            if len(extension) == 2 and f".{extension[1]}" in {
                ".pdf",
                ".docx",
                ".xlsx",
                ".txt",
                ".zip",
            }:
                attachments.append(
                    CrawledAttachment(
                        element.get_text(" ", strip=True) or attachment_url.rsplit("/", 1)[-1],
                        attachment_url,
                    )
                )
        return CrawledDocument(
            title=title_element.get_text(" ", strip=True),
            url=normalize_url(response.url),
            raw_html=response.text,
            text=content_element.get_text("\n", strip=True),
            publish_date_text=date_element.get_text(" ", strip=True) if date_element else None,
            attachments=tuple(attachments),
        )


def _required_selector(config: dict[str, object], name: str) -> str:
    value = config.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"selector '{name}' is required")
    return value.strip()


def _optional_selector(config: dict[str, object], name: str) -> str | None:
    value = config.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None
