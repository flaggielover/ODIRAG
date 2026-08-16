from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.crawler.urls import HostResolver, validate_public_url

_DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True, slots=True)
class FetchResponse:
    url: str
    status_code: int
    content: bytes
    content_type: str
    encoding: str
    content_disposition: str | None = None

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding, errors="replace")


class Fetcher(Protocol):
    async def fetch(self, url: str) -> FetchResponse: ...


class ResponseTooLargeError(ValueError):
    """Raised before a response can exceed the configured in-memory limit."""


class RedirectLimitError(ValueError):
    """Raised when a response exceeds the configured redirect hop limit."""


class HttpFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        max_redirects: int = 5,
        user_agent: str = "ODIRAG/0.1 (+official-document-crawler)",
        client: httpx.AsyncClient | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        resolver: HostResolver | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must not be negative")
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self._client = client
        self._client_factory = client_factory
        self._resolver = resolver

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
        reraise=True,
    )
    async def fetch(self, url: str) -> FetchResponse:
        owns_client = self._client is None
        client = self._client or (
            self._client_factory()
            if self._client_factory is not None
            else httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": self.user_agent, "Accept": "*/*"},
            )
        )
        try:
            current_url = url
            for redirect_count in range(self.max_redirects + 1):
                current_url = await asyncio.wait_for(
                    validate_public_url(current_url, resolver=self._resolver),
                    timeout=self.timeout_seconds,
                )
                async with client.stream(
                    "GET",
                    current_url,
                    headers={"User-Agent": self.user_agent, "Accept": "*/*"},
                    follow_redirects=False,
                ) as response:
                    if response.status_code in _REDIRECT_STATUS_CODES:
                        location = response.headers.get("location")
                        if location is None:
                            response.raise_for_status()
                        if redirect_count >= self.max_redirects:
                            raise RedirectLimitError("response exceeded the redirect limit")
                        current_url = urljoin(str(response.url), location)
                        continue

                    response.raise_for_status()
                    content = await self._read_limited(response)
                    content_type = response.headers.get("content-type", "application/octet-stream")
                    encoding = (
                        response.encoding or _encoding_from_content_type(content_type) or "utf-8"
                    )
                    return FetchResponse(
                        url=str(response.url),
                        status_code=response.status_code,
                        content=content,
                        content_type=content_type.split(";", 1)[0].strip().lower(),
                        encoding=encoding,
                        content_disposition=response.headers.get("content-disposition"),
                    )
            raise RedirectLimitError("response exceeded the redirect limit")
        finally:
            if owns_client:
                await client.aclose()

    async def _read_limited(self, response: httpx.Response) -> bytes:
        declared_length = _content_length(response)
        if declared_length is not None and declared_length > self.max_bytes:
            raise ResponseTooLargeError("response exceeds configured size limit")

        content = bytearray()
        chunk_size = min(64 * 1024, self.max_bytes + 1)
        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
            if len(content) + len(chunk) > self.max_bytes:
                raise ResponseTooLargeError("response exceeds configured size limit")
            content.extend(chunk)
        return bytes(content)


def _encoding_from_content_type(value: str) -> str | None:
    for item in value.split(";")[1:]:
        key, separator, content = item.strip().partition("=")
        if separator and key.lower() == "charset":
            return content.strip("\"' ")
    return None


def _content_length(response: httpx.Response) -> int | None:
    value = response.headers.get("content-length")
    if value is None:
        return None
    try:
        length = int(value)
    except ValueError as exc:
        raise ValueError("response Content-Length is invalid") from exc
    if length < 0:
        raise ValueError("response Content-Length is invalid")
    return length
