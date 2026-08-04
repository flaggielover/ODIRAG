from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.crawler import FetchResponse
from app.crawler.adapters import GovCnLatestJsonAdapter
from app.crawler.registry import CrawlerAdapterRegistry
from app.services.source_config import load_source_config


class MappingFetcher:
    def __init__(self, mapping: dict[str, FetchResponse]) -> None:
        self.mapping = mapping

    async def fetch(self, url: str) -> FetchResponse:
        return self.mapping[url]


async def test_govcn_json_adapter_uses_public_feed_contract() -> None:
    feed_url = "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json"
    detail_url = "https://www.gov.cn/zhengce/content/2026/policy.htm"
    fetcher = MappingFetcher(
        {
            feed_url: FetchResponse(
                feed_url,
                200,
                json.dumps(
                    [
                        {
                            "URL": detail_url,
                            "TITLE": "policy",
                            "DOCRELPUBTIME": "2026-08-03",
                        }
                    ]
                ).encode(),
                "application/json",
                "utf-8",
            ),
            detail_url: FetchResponse(
                detail_url,
                200,
                b'<html><h1>Policy title</h1><div id="UCAP-CONTENT">Body</div></html>',
                "text/html",
                "utf-8",
            ),
        }
    )
    documents = await GovCnLatestJsonAdapter(fetcher).crawl_column(
        column_url=feed_url,
        selectors={"title": "h1", "content": "#UCAP-CONTENT"},
        pagination={"page_size": 20},
        max_pages=1,
        request_interval_seconds=0,
    )
    assert len(documents) == 1
    assert documents[0].title == "Policy title"
    assert documents[0].publish_date_text == "2026-08-03"


def test_registry_rejects_unknown_adapter() -> None:
    with pytest.raises(ValueError, match="unknown crawler adapter"):
        CrawlerAdapterRegistry({}).get("missing")


def test_sites_yaml_matches_source_schema() -> None:
    config = load_source_config(Path("../config/sites.yaml"))
    assert config.sources[0].columns[0].parser_type == "govcn_latest_json"
