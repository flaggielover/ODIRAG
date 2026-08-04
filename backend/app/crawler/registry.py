from __future__ import annotations

from app.crawler.adapters import CrawlerAdapter, GovCnLatestJsonAdapter
from app.crawler.fetcher import Fetcher
from app.crawler.generic import GenericCrawler


class CrawlerAdapterRegistry:
    def __init__(self, adapters: dict[str, CrawlerAdapter]) -> None:
        self._adapters = adapters

    @classmethod
    def default(cls, fetcher: Fetcher) -> CrawlerAdapterRegistry:
        generic = GenericCrawler(fetcher)
        return cls(
            {
                "html": generic,
                "generic_html": generic,
                "govcn_latest_json": GovCnLatestJsonAdapter(fetcher),
            }
        )

    def get(self, parser_type: str) -> CrawlerAdapter:
        try:
            return self._adapters[parser_type]
        except KeyError as exc:
            raise ValueError(f"unknown crawler adapter: {parser_type}") from exc
