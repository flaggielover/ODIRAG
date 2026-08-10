from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from pydantic import ValidationError

from app.crawler.fetcher import Fetcher
from app.crawler.generic import CrawlColumnResult, CrawlDiscoveryError
from app.crawler.urls import UnsafeUrlError
from app.schemas.coze import BatchCrawlRequest, BatchCrawlResponse, parse_batch_crawl_response

CrawlContract = Literal["legacy_single_article", "batch_crawl"]


class CrawlProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        raw_response: str | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.raw_response = raw_response
        self.attempts = attempts


@dataclass(slots=True)
class CrawlProviderResult:
    contract: CrawlContract
    status: Literal["completed"]
    status_code: int
    attempts: int
    duration_ms: int
    raw_response: Any
    normalized_response: dict[str, Any] | None = None
    batch: BatchCrawlResponse | None = None


@dataclass(slots=True)
class CrawlProviderConnection:
    available: bool
    contract: CrawlContract
    status_code: int | None
    latency_ms: int
    error_code: str | None = None


@runtime_checkable
class CrawlProvider(Protocol):
    async def test_connection(
        self, *, contract: CrawlContract | None = None, source_url: str | None = None
    ) -> CrawlProviderConnection: ...

    async def start_crawl(
        self,
        payload: Mapping[str, Any],
        *,
        contract: CrawlContract | None = None,
    ) -> CrawlProviderResult: ...

    async def get_task_status(self, provider_task_id: str) -> CrawlProviderResult: ...

    async def cancel_task(self, provider_task_id: str) -> bool: ...

    def normalize_result(
        self, payload: Any, *, contract: CrawlContract
    ) -> tuple[dict[str, Any], BatchCrawlResponse | None]: ...


class CozeCrawlProvider:
    """Direct Coze deployment client supporting legacy and batch contracts."""

    def __init__(
        self,
        *,
        api_token: str | None,
        legacy_api_url: str | None,
        batch_api_url: str | None,
        default_contract: CrawlContract = "batch_crawl",
        timeout_seconds: float = 90.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.25,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_token = api_token
        self.legacy_api_url = _clean_url(legacy_api_url)
        self.batch_api_url = _clean_url(batch_api_url)
        self.default_contract = default_contract
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self._client = client

    async def test_connection(
        self, *, contract: CrawlContract | None = None, source_url: str | None = None
    ) -> CrawlProviderConnection:
        selected = contract or self.default_contract
        started = time.perf_counter()
        payload: dict[str, Any]
        if selected == "batch_crawl":
            payload = {
                "task_id": "connection-test",
                "source_url": source_url or "https://example.com/",
                "max_articles": 1,
                "max_pages": 1,
            }
        else:
            payload = {"title": "connection-test", "content": "connection-test"}
        try:
            result = await self.start_crawl(payload, contract=selected)
            self.normalize_result(result.raw_response, contract=selected)
            return CrawlProviderConnection(
                available=True,
                contract=selected,
                status_code=result.status_code,
                latency_ms=result.duration_ms,
            )
        except CrawlProviderError as exc:
            return CrawlProviderConnection(
                available=False,
                contract=selected,
                status_code=exc.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                error_code=exc.code,
            )

    async def start_crawl(
        self,
        payload: Mapping[str, Any],
        *,
        contract: CrawlContract | None = None,
    ) -> CrawlProviderResult:
        selected = contract or self.default_contract
        endpoint = self._endpoint(selected)
        if not self.api_token:
            raise CrawlProviderError(
                "COZE_TOKEN_NOT_CONFIGURED",
                "Coze API token is not configured",
                retryable=False,
            )
        request_payload = dict(payload)
        if selected == "batch_crawl":
            try:
                request_payload = BatchCrawlRequest.model_validate(payload).model_dump(
                    mode="json", exclude_none=True
                )
            except ValidationError as exc:
                raise CrawlProviderError(
                    "COZE_REQUEST_INVALID",
                    "Coze batch crawl request is invalid",
                    retryable=False,
                ) from exc
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        started = time.perf_counter()
        try:
            response, attempts = await self._post_with_retry(
                client, endpoint=endpoint, payload=request_payload
            )
            try:
                raw_payload = response.json()
            except ValueError as exc:
                raise CrawlProviderError(
                    "COZE_INVALID_JSON",
                    "Coze returned invalid JSON",
                    retryable=False,
                    status_code=response.status_code,
                    raw_response=response.text,
                    attempts=attempts,
                ) from exc
            return CrawlProviderResult(
                contract=selected,
                status="completed",
                status_code=response.status_code,
                attempts=attempts,
                duration_ms=round((time.perf_counter() - started) * 1000),
                raw_response=raw_payload,
            )
        finally:
            if owns_client:
                await client.aclose()

    async def get_task_status(self, provider_task_id: str) -> CrawlProviderResult:
        raise CrawlProviderError(
            "COZE_DIRECT_DEPLOYMENT_IS_SYNCHRONOUS",
            f"Direct deployment has no pollable task: {provider_task_id}",
            retryable=False,
        )

    async def cancel_task(self, provider_task_id: str) -> bool:
        raise CrawlProviderError(
            "COZE_DIRECT_DEPLOYMENT_CANNOT_CANCEL",
            f"Direct deployment cannot cancel task: {provider_task_id}",
            retryable=False,
        )

    def normalize_result(
        self, payload: Any, *, contract: CrawlContract
    ) -> tuple[dict[str, Any], BatchCrawlResponse | None]:
        try:
            if contract == "batch_crawl":
                batch, _raw = parse_batch_crawl_response(payload)
                return batch.model_dump(mode="json"), batch
            candidate = payload
            for _ in range(3):
                if isinstance(candidate, str):
                    candidate = json.loads(candidate)
                    continue
                if isinstance(candidate, dict):
                    nested = next(
                        (
                            candidate[key]
                            for key in ("data", "output", "result")
                            if isinstance(candidate.get(key), (dict, str))
                        ),
                        None,
                    )
                    if nested is not None:
                        candidate = nested
                        continue
                break
            if not isinstance(candidate, dict):
                raise ValueError("legacy response must normalize to a JSON object")
            return candidate, None
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise CrawlProviderError(
                "COZE_CONTRACT_MISMATCH",
                "Coze response does not match the configured contract",
                retryable=False,
                raw_response=_raw_response_text(payload),
            ) from exc

    def _endpoint(self, contract: CrawlContract) -> str:
        endpoint = self.batch_api_url if contract == "batch_crawl" else self.legacy_api_url
        if not endpoint:
            code = (
                "COZE_BATCH_WORKFLOW_NOT_PUBLISHED"
                if contract == "batch_crawl"
                else "COZE_LEGACY_WORKFLOW_NOT_CONFIGURED"
            )
            raise CrawlProviderError(code, "Coze workflow URL is not configured", retryable=False)
        return endpoint

    async def _post_with_retry(
        self, client: httpx.AsyncClient, *, endpoint: str, payload: dict[str, Any]
    ) -> tuple[httpx.Response, int]:
        attempts = 0
        while True:
            attempts += 1
            try:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json; charset=utf-8",
                        "Accept": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise CrawlProviderError(
                    "COZE_TIMEOUT", "Coze request timed out", retryable=True, attempts=attempts
                ) from exc
            except httpx.HTTPError as exc:
                if attempts <= self.max_retries:
                    await self._backoff(attempts)
                    continue
                raise CrawlProviderError(
                    "COZE_NETWORK_ERROR",
                    "Coze request failed at the network layer",
                    retryable=True,
                    attempts=attempts,
                ) from exc
            error = _response_error(response, attempts=attempts)
            if error is None:
                return response, attempts
            if error.retryable and attempts <= self.max_retries:
                await self._backoff(attempts)
                continue
            raise error

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(self.backoff_base_seconds * (2 ** (attempt - 1)))


class LocalCrawlProvider:
    """Run the existing selector-based crawler behind the provider contract.

    Local crawling does not make a quality decision, so successfully parsed
    articles are deliberately marked ``pending_review``.  It is primarily an
    explicit fallback and network-diagnostic provider, never an implicit Coze
    success path.
    """

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self._results: dict[str, CrawlProviderResult] = {}
        self._cancelled: set[str] = set()

    async def test_connection(
        self, *, contract: CrawlContract | None = None, source_url: str | None = None
    ) -> CrawlProviderConnection:
        started = time.perf_counter()
        if contract not in {None, "batch_crawl"}:
            return CrawlProviderConnection(
                available=False,
                contract="batch_crawl",
                status_code=None,
                latency_ms=0,
                error_code="LOCAL_CONTRACT_UNSUPPORTED",
            )
        if not source_url:
            return CrawlProviderConnection(
                available=False,
                contract="batch_crawl",
                status_code=None,
                latency_ms=0,
                error_code="LOCAL_SOURCE_URL_REQUIRED",
            )
        try:
            response = await self.fetcher.fetch(source_url)
        except UnsafeUrlError:
            code = "LOCAL_SSRF_REJECTED"
        except (httpx.TimeoutException, TimeoutError):
            code = "LOCAL_TIMEOUT"
        except httpx.ConnectError:
            code = "LOCAL_DNS_OR_CONNECT_ERROR"
        except Exception:
            code = "LOCAL_NETWORK_ERROR"
        else:
            return CrawlProviderConnection(
                available=True,
                contract="batch_crawl",
                status_code=response.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        return CrawlProviderConnection(
            available=False,
            contract="batch_crawl",
            status_code=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_code=code,
        )

    async def start_crawl(
        self,
        payload: Mapping[str, Any],
        *,
        contract: CrawlContract | None = None,
    ) -> CrawlProviderResult:
        if contract not in {None, "batch_crawl"}:
            raise CrawlProviderError(
                "LOCAL_CONTRACT_UNSUPPORTED",
                "Local crawling supports only the batch provider contract",
                retryable=False,
            )
        task_id = str(payload.get("task_id", ""))
        if not task_id:
            raise CrawlProviderError(
                "LOCAL_TASK_ID_REQUIRED", "Local crawl task_id is required", retryable=False
            )
        if task_id in self._cancelled:
            raise CrawlProviderError(
                "LOCAL_TASK_CANCELLED",
                "Local crawl was cancelled before it started",
                retryable=False,
            )
        source_url = payload.get("source_url")
        selectors = payload.get("selectors")
        pagination = payload.get("pagination", {})
        if not isinstance(source_url, str) or not source_url:
            raise CrawlProviderError(
                "LOCAL_SOURCE_URL_REQUIRED", "Local crawl source_url is required", retryable=False
            )
        if not isinstance(selectors, dict) or not isinstance(pagination, dict):
            raise CrawlProviderError(
                "LOCAL_SELECTORS_REQUIRED",
                "Local crawl selectors and pagination must be JSON objects",
                retryable=False,
            )

        from app.crawler.registry import CrawlerAdapterRegistry

        started = time.perf_counter()
        crawler = CrawlerAdapterRegistry.default(self.fetcher).get(
            str(payload.get("parser_type", "html"))
        )
        max_pages = _positive_int(payload.get("max_pages", 1), "max_pages")
        max_articles = _positive_int(payload.get("max_articles", 5), "max_articles")
        diagnostics: CrawlColumnResult | None = None
        crawl_with_diagnostics = getattr(crawler, "crawl_column_with_diagnostics", None)
        if callable(crawl_with_diagnostics):
            try:
                diagnostics = await crawl_with_diagnostics(
                    column_url=source_url,
                    selectors=selectors,
                    pagination=pagination,
                    max_pages=max_pages,
                    max_articles=max_articles,
                    request_interval_seconds=int(payload.get("request_interval_seconds", 0)),
                )
            except CrawlDiscoveryError as exc:
                raise CrawlProviderError(
                    exc.code,
                    str(exc),
                    retryable=exc.retryable,
                ) from exc
            documents = list(diagnostics.documents)
        else:
            documents = await crawler.crawl_column(
                column_url=source_url,
                selectors=selectors,
                pagination=pagination,
                max_pages=max_pages,
                request_interval_seconds=int(payload.get("request_interval_seconds", 0)),
            )
        failures = list(diagnostics.diagnostics.failures) if diagnostics else []
        warnings = list(diagnostics.diagnostics.warnings) if diagnostics else []
        if not documents and not failures and "NO_ARTICLES" not in warnings:
            warnings.append("NO_ARTICLES")
        articles = [
            {
                "title": document.title,
                "url": document.url,
                "published_at": None,
                "organization": payload.get("source_name"),
                "region": payload.get("region"),
                "column_name": payload.get("column_name"),
                "content": document.text,
                "content_length": len(document.text),
                "attachments": [
                    {
                        "name": attachment.name,
                        "url": attachment.url,
                        "file_type": attachment.file_type,
                        "download_status": "pending",
                    }
                    for attachment in document.attachments
                ],
                "extraction_method": document.extraction_method,
                "needs_ocr": document.needs_ocr,
                "image_urls": list(document.image_urls),
                "image_count": len(document.image_urls),
                "image_alt_texts": list(document.image_alt_texts),
                "decision": "pending_review",
                "accepted": False,
                "quality_score": None,
                "decision_reason": "Local crawler requires downstream review",
                "warnings": list(document.warnings),
            }
            for document in documents[:max_articles]
        ]
        failed_urls = [
            {
                "url": failure.url,
                "stage": failure.stage,
                "error_code": failure.error_code,
                "error_message": failure.error_message,
                "retryable": failure.retryable,
            }
            for failure in failures
        ]
        discovery = diagnostics.diagnostics if diagnostics else None
        normalized = {
            "success": not failures,
            "task_id": task_id,
            "source": {
                "source_url": source_url,
                "source_name": payload.get("source_name"),
                "region": payload.get("region"),
                "column_name": payload.get("column_name"),
            },
            "statistics": {
                "pages_visited": discovery.pages_visited if discovery else 0,
                "articles_discovered": (
                    len(discovery.candidate_links) if discovery else len(documents)
                ),
                "articles_fetched": len(articles),
                "articles_accepted": 0,
                "articles_rejected": 0,
                "articles_pending_review": len(articles),
                "articles_failed": len(failed_urls),
            },
            "articles": articles,
            "failed_urls": failed_urls,
            "warnings": warnings,
            "diagnostics": {
                "candidate_links": list(discovery.candidate_links) if discovery else [],
                "normalized_links": list(discovery.normalized_links) if discovery else [],
                "page_classifications": list(discovery.page_classifications) if discovery else [],
                "pagination_events": list(discovery.pagination_events) if discovery else [],
                "api_discovery": discovery.api_discovery if discovery else None,
            },
        }
        batch, _raw = parse_batch_crawl_response(normalized)
        result = CrawlProviderResult(
            contract="batch_crawl",
            status="completed",
            status_code=200,
            attempts=1,
            duration_ms=round((time.perf_counter() - started) * 1000),
            raw_response=normalized,
            normalized_response=batch.model_dump(mode="json"),
            batch=batch,
        )
        self._results[task_id] = result
        return result

    async def get_task_status(self, provider_task_id: str) -> CrawlProviderResult:
        try:
            return self._results[provider_task_id]
        except KeyError as exc:
            raise CrawlProviderError(
                "LOCAL_TASK_STATUS_NOT_FOUND",
                "No completed local provider result exists for this task",
                retryable=False,
            ) from exc

    async def cancel_task(self, provider_task_id: str) -> bool:
        if provider_task_id in self._results:
            return False
        self._cancelled.add(provider_task_id)
        return True

    def normalize_result(
        self, payload: Any, *, contract: CrawlContract
    ) -> tuple[dict[str, Any], BatchCrawlResponse | None]:
        if contract != "batch_crawl":
            raise ValueError("local provider supports only batch_crawl normalization")
        batch, _raw = parse_batch_crawl_response(payload)
        return batch.model_dump(mode="json"), batch


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise CrawlProviderError(
            "LOCAL_INVALID_ARGUMENT",
            f"{name} must be a positive integer",
            retryable=False,
        )
    if not isinstance(value, (int, float, str)):
        raise CrawlProviderError(
            "LOCAL_INVALID_ARGUMENT",
            f"{name} must be a positive integer",
            retryable=False,
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CrawlProviderError(
            "LOCAL_INVALID_ARGUMENT",
            f"{name} must be a positive integer",
            retryable=False,
        ) from exc
    if parsed < 1:
        raise CrawlProviderError(
            "LOCAL_INVALID_ARGUMENT",
            f"{name} must be a positive integer",
            retryable=False,
        )
    return parsed


def _response_error(response: httpx.Response, *, attempts: int) -> CrawlProviderError | None:
    status = response.status_code
    if 200 <= status < 300:
        return None
    raw = response.text
    if status in {401, 403}:
        return CrawlProviderError(
            "COZE_AUTH_FAILED",
            "Coze rejected the configured credentials",
            retryable=False,
            status_code=status,
            raw_response=raw,
            attempts=attempts,
        )
    if status == 408:
        return CrawlProviderError(
            "COZE_TIMEOUT",
            "Coze deployment timed out",
            retryable=True,
            status_code=status,
            raw_response=raw,
            attempts=attempts,
        )
    if status == 429:
        return CrawlProviderError(
            "COZE_RATE_LIMITED",
            "Coze rate limit was reached",
            retryable=True,
            status_code=status,
            raw_response=raw,
            attempts=attempts,
        )
    if status >= 500:
        return CrawlProviderError(
            "COZE_UPSTREAM_ERROR",
            "Coze deployment returned a server error",
            retryable=True,
            status_code=status,
            raw_response=raw,
            attempts=attempts,
        )
    return CrawlProviderError(
        "COZE_REQUEST_REJECTED",
        "Coze rejected the request",
        retryable=False,
        status_code=status,
        raw_response=raw,
        attempts=attempts,
    )


def _clean_url(value: str | None) -> str | None:
    stripped = value.strip() if value else ""
    return stripped.rstrip("/") if stripped else None


def _raw_response_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(payload)
