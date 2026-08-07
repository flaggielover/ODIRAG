from __future__ import annotations

import json

import httpx
import pytest

from app.crawler.fetcher import FetchResponse
from app.crawler.providers import CozeCrawlProvider, CrawlProviderError, LocalCrawlProvider
from app.schemas.coze import BatchCrawlResponse, parse_batch_crawl_response


def _response(*, article_decision: str = "accepted") -> dict:
    article = {
        "title": "公告",
        "url": "https://example.com/article/1",
        "published_at": None,
        "content": "正文",
        "content_length": 2,
        "attachments": [],
        "extraction_method": "html",
        "needs_ocr": False,
        "image_urls": [],
        "image_count": 0,
        "image_alt_texts": [],
        "decision": article_decision,
        "accepted": article_decision == "accepted",
        "quality_score": 85,
        "decision_reason": "ok",
        "warnings": [],
    }
    return {
        "success": True,
        "task_id": "1",
        "source": {"source_url": "https://example.com/", "source_name": "example"},
        "statistics": {
            "pages_visited": 1,
            "articles_discovered": 1,
            "articles_fetched": 1,
            "articles_accepted": int(article_decision == "accepted"),
            "articles_rejected": int(article_decision == "rejected"),
            "articles_pending_review": int(article_decision == "pending_review"),
            "articles_failed": 0,
        },
        "articles": [article],
        "failed_urls": [],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_batch_contract_posts_utf8_and_normalizes() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=_response())

    provider = CozeCrawlProvider(
        api_token="secret",
        legacy_api_url="https://legacy.example/run",
        batch_api_url="https://batch.example/run",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    result = await provider.start_crawl(
        {"task_id": "1", "source_url": "https://example.com/", "source_name": "中文"},
        contract="batch_crawl",
    )
    normalized, batch = provider.normalize_result(result.raw_response, contract="batch_crawl")
    assert batch is not None
    assert batch.statistics.articles_accepted == 1
    assert normalized["statistics"]["articles_accepted"] == 1
    assert "中文" in bytes(seen["body"]).decode("utf-8")
    assert seen["auth"] == "Bearer secret"


@pytest.mark.asyncio
async def test_batch_contract_retries_server_errors() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="temporary")
        return httpx.Response(200, json=_response())

    provider = CozeCrawlProvider(
        api_token="secret",
        legacy_api_url=None,
        batch_api_url="https://batch.example/run",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=1,
        backoff_base_seconds=0,
    )
    result = await provider.start_crawl({"task_id": "1", "source_url": "https://example.com/"})
    assert calls == 2
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_auth_and_invalid_json_are_classified() -> None:
    async def unauthorized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="no")

    provider = CozeCrawlProvider(
        api_token="secret",
        legacy_api_url="https://legacy.example/run",
        batch_api_url="https://batch.example/run",
        client=httpx.AsyncClient(transport=httpx.MockTransport(unauthorized)),
        max_retries=2,
    )
    with pytest.raises(CrawlProviderError, match="credentials") as error:
        await provider.start_crawl({"task_id": "1", "source_url": "https://example.com/"})
    assert error.value.code == "COZE_AUTH_FAILED"

    async def invalid(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(invalid))
    with pytest.raises(CrawlProviderError) as error:
        await provider.start_crawl({"task_id": "1", "source_url": "https://example.com/"})
    assert error.value.code == "COZE_INVALID_JSON"


@pytest.mark.asyncio
async def test_parseable_wrong_batch_contract_is_classified() -> None:
    async def wrong_contract(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": "single article"})

    provider = CozeCrawlProvider(
        api_token="secret",
        legacy_api_url="https://legacy.example/run",
        batch_api_url="https://batch.example/run",
        client=httpx.AsyncClient(transport=httpx.MockTransport(wrong_contract)),
        max_retries=0,
    )
    result = await provider.start_crawl({"task_id": "1", "source_url": "https://example.com/"})
    with pytest.raises(CrawlProviderError) as error:
        provider.normalize_result(result.raw_response, contract="batch_crawl")
    assert error.value.code == "COZE_CONTRACT_MISMATCH"


@pytest.mark.asyncio
async def test_batch_contract_rejects_numeric_task_id_before_request() -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_response())

    provider = CozeCrawlProvider(
        api_token="secret",
        legacy_api_url=None,
        batch_api_url="https://batch.example/run",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )

    with pytest.raises(CrawlProviderError) as error:
        await provider.start_crawl({"task_id": 1, "source_url": "https://example.com/"})

    assert error.value.code == "COZE_REQUEST_INVALID"
    assert called is False


def test_batch_response_is_strict() -> None:
    response = BatchCrawlResponse.model_validate(_response())
    assert response.source.source_url.host == "example.com"
    with pytest.raises(ValueError):
        BatchCrawlResponse.model_validate({**_response(), "unexpected": True})


def test_batch_response_accepts_complete_historical_json_fence() -> None:
    response, raw = parse_batch_crawl_response(
        "```json\n" + json.dumps(_response(), ensure_ascii=False) + "\n```"
    )
    assert response.statistics.articles_discovered == 1
    assert isinstance(raw, str)


def test_batch_response_accepts_deployed_batch_result_wrapper() -> None:
    payload = {"run_id": "fixture-run", "batch_result": _response()}

    response, raw = parse_batch_crawl_response(payload)

    assert response.statistics.articles_discovered == 1
    assert raw is payload


def test_batch_response_rejects_surrounding_markdown_text() -> None:
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_batch_crawl_response("Here is the result:\n```json\n{}\n```")


@pytest.mark.asyncio
async def test_local_provider_runs_real_selector_crawler_and_tracks_status() -> None:
    class MappingFetcher:
        async def fetch(self, url: str) -> FetchResponse:
            pages = {
                "https://local.example/column": ('<a class="item" href="/article/1">article</a>'),
                "https://local.example/article/1": (
                    "<h1>\u4e2d\u6587\u6807\u9898</h1><time>2026-08-04</time>"
                    "<main>\u4e2d\u6587\u6b63\u6587</main>"
                ),
            }
            return FetchResponse(url, 200, pages[url].encode("utf-8"), "text/html", "utf-8")

    provider = LocalCrawlProvider(MappingFetcher())
    result = await provider.start_crawl(
        {
            "task_id": 7,
            "source_url": "https://local.example/column",
            "source_name": "\u672c\u5730\u6765\u6e90",
            "max_articles": 1,
            "max_pages": 1,
            "selectors": {
                "list_link": "a.item",
                "title": "h1",
                "content": "main",
                "publish_date": "time",
            },
            "pagination": {},
        }
    )

    assert result.batch is not None
    assert result.batch.articles[0].title == "\u4e2d\u6587\u6807\u9898"
    assert result.batch.articles[0].decision == "pending_review"
    assert await provider.get_task_status("7") is result
    assert await provider.cancel_task("7") is False


@pytest.mark.asyncio
async def test_local_provider_cancels_only_before_start() -> None:
    class UnusedFetcher:
        async def fetch(self, _url: str) -> FetchResponse:
            raise AssertionError("fetch must not run")

    provider = LocalCrawlProvider(UnusedFetcher())
    assert await provider.cancel_task("8") is True
    with pytest.raises(CrawlProviderError) as error:
        await provider.start_crawl(
            {
                "task_id": 8,
                "source_url": "https://local.example/column",
                "selectors": {},
                "pagination": {},
            }
        )
    assert error.value.code == "LOCAL_TASK_CANCELLED"
