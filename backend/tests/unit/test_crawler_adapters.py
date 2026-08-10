from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.crawler import FetchResponse, GenericCrawler, score_candidate
from app.crawler.adapters import GovCnLatestJsonAdapter
from app.crawler.registry import CrawlerAdapterRegistry
from app.services.source_config import load_source_config


class MappingFetcher:
    def __init__(self, mapping: dict[str, FetchResponse]) -> None:
        self.mapping = mapping

    async def fetch(self, url: str) -> FetchResponse:
        return self.mapping[url]


@pytest.mark.asyncio
async def test_generic_html_discovery_scores_links_and_stops_at_article_limit() -> None:
    pages = {
        "https://example.gov/column?page=1": (
            '<a href="/login">登录</a>'
            '<a class="title" href="/notice/2026/1">通知一</a>'
            '<a class="title" href="/notice/2026/2?utm_source=x">通知二</a>'
            '<a rel="next" href="/column?page=2">下一页</a>'
        ),
        "https://example.gov/column?page=2": (
            '<a class="title" href="/notice/2026/3">通知三</a>'
            '<a rel="next" href="/column?page=1">下一页</a>'
        ),
        **{
            f"https://example.gov/notice/2026/{index}": (
                f"<h1>通知{index}</h1><main>" + ("完整正文 " * 80) + "</main>"
            )
            for index in (1, 2, 3)
        },
    }
    result = await GenericCrawler(
        MappingFetcher(
            {
                url: FetchResponse(url, 200, html.encode(), "text/html", "utf-8")
                for url, html in pages.items()
            }
        )
    ).crawl_column_with_diagnostics(
        column_url="https://example.gov/column?page=1",
        selectors={"list_link": "a[href]"},
        pagination={"next_selector": "a[rel='next']"},
        max_pages=3,
        max_articles=2,
        request_interval_seconds=0,
    )
    assert [document.url for document in result.documents] == [
        "https://example.gov/notice/2026/1",
        "https://example.gov/notice/2026/2",
    ]
    assert result.diagnostics.pages_visited == 1
    assert result.diagnostics.candidate_links[0]["score"] >= 2
    assert any(
        event.get("stop") == "max_articles" for event in result.diagnostics.pagination_events
    )


@pytest.mark.asyncio
async def test_generic_direct_detail_and_attachment_image_metadata() -> None:
    url = "https://dept.gov.cn/notice/2026/08/10/123456.shtml"
    html = (
        "<html><head><title>详情</title></head><body>"
        "<h1>政策通知</h1><article><p>简短说明</p>"
        '<img src="/images/scan.png" alt="扫描件">'
        '<a href="/files/notice.DOC">附件下载</a></article></body></html>'
    )
    result = await GenericCrawler(
        MappingFetcher({url: FetchResponse(url, 200, html.encode(), "text/html", "utf-8")})
    ).crawl_column_with_diagnostics(
        column_url=url,
        selectors={"detail_url": True},
        pagination={},
        max_pages=1,
        max_articles=1,
        request_interval_seconds=0,
    )
    document = result.documents[0]
    assert document.extraction_method == "image"
    assert document.needs_ocr is True
    assert document.image_urls == ("https://dept.gov.cn/images/scan.png",)
    assert document.attachments[0].file_type == "doc"
    assert "SHORT_TEXT_WITH_ATTACHMENT" in document.warnings


@pytest.mark.asyncio
async def test_generic_spa_api_fallback_discovers_items_and_inline_content() -> None:
    column = "https://api.gov.cn/column"
    api = "https://api.gov.cn/api/news?page=1"
    html = '<script>fetch("/api/news?page=1")</script>'
    api_payload = {"items": [{"id": "7", "title": "API通知", "content": "正文 " * 80}]}
    result = await GenericCrawler(
        MappingFetcher(
            {
                column: FetchResponse(column, 200, html.encode(), "text/html", "utf-8"),
                api: FetchResponse(
                    api, 200, json.dumps(api_payload).encode(), "application/json", "utf-8"
                ),
            }
        )
    ).crawl_column_with_diagnostics(
        column_url=column,
        selectors={},
        pagination={
            "site_rules": {
                "mode": "api",
                "list": {
                    "list_endpoint": api,
                    "items_path": "items",
                    "detail_url_template": "https://api.gov.cn/article/{id}",
                },
            }
        },
        max_pages=1,
        max_articles=1,
        request_interval_seconds=0,
    )
    assert result.documents[0].title == "API通知"
    assert result.diagnostics.api_discovery is not None
    assert result.diagnostics.api_discovery["items"] == 1


def test_candidate_score_explains_date_and_navigation_penalty() -> None:
    score, reasons = score_candidate(
        url="https://example.gov/zcwj/2026/08/10/123456.shtml", anchor_text="关于产业发展的通知"
    )
    assert score >= 5
    assert "path:date" in reasons


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
