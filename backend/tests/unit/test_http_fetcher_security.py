from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.crawler import HttpFetcher, RedirectLimitError, ResponseTooLargeError, UnsafeUrlError


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks
        self.iterated = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.iterated = True
        for chunk in self._chunks:
            yield chunk


async def public_resolver(_hostname: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://224.0.0.1/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[ff02::1]/",
        "http://[::]/",
        "http://user:password@public.example/",
    ],
)
async def test_fetcher_rejects_local_non_public_and_credential_targets(url: str) -> None:
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsafe target reached the HTTP transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        fetcher = HttpFetcher(client=client, resolver=public_resolver)
        with pytest.raises(UnsafeUrlError):
            await fetcher.fetch(url)


async def test_fetcher_rejects_hostname_resolving_to_private_ip() -> None:
    async def private_resolver(hostname: str) -> tuple[str, ...]:
        assert hostname == "internal.example"
        return ("10.1.2.3",)

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("private DNS result reached the HTTP transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        fetcher = HttpFetcher(client=client, resolver=private_resolver)
        with pytest.raises(UnsafeUrlError, match="non-public"):
            await fetcher.fetch("https://internal.example/document")


async def test_fetcher_rejects_mixed_public_and_private_dns_results() -> None:
    async def mixed_resolver(_hostname: str) -> tuple[str, ...]:
        return ("93.184.216.34", "127.0.0.1")

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("mixed DNS result reached the HTTP transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        fetcher = HttpFetcher(client=client, resolver=mixed_resolver)
        with pytest.raises(UnsafeUrlError, match="non-public"):
            await fetcher.fetch("https://mixed.example/document")


async def test_fetcher_validates_redirect_target_before_second_request() -> None:
    resolved_hosts: list[str] = []
    requested_urls: list[str] = []

    async def resolver(hostname: str) -> tuple[str, ...]:
        resolved_hosts.append(hostname)
        return ("10.0.0.8",) if hostname == "internal.example" else ("93.184.216.34",)

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://internal.example/secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(client=client, resolver=resolver)
        with pytest.raises(UnsafeUrlError, match="non-public"):
            await fetcher.fetch("https://public.example/start")

    assert requested_urls == ["https://public.example/start"]
    assert resolved_hosts == ["public.example", "internal.example"]


async def test_fetcher_rejects_oversized_content_length_before_reading() -> None:
    stream = ChunkedStream((b"body",))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "9"}, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(client=client, resolver=public_resolver, max_bytes=8)
        with pytest.raises(ResponseTooLargeError):
            await fetcher.fetch("https://public.example/large")

    assert not stream.iterated


async def test_fetcher_stops_stream_when_cumulative_body_exceeds_limit() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkedStream((b"abcd", b"efgh")))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(client=client, resolver=public_resolver, max_bytes=6)
        with pytest.raises(ResponseTooLargeError):
            await fetcher.fetch("https://public.example/stream")


async def test_fetcher_returns_valid_public_streamed_response() -> None:
    resolved_hosts: list[str] = []

    async def resolver(hostname: str) -> tuple[str, ...]:
        resolved_hosts.append(hostname)
        return ("93.184.216.34",)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            stream=ChunkedStream((b"policy", b" body")),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await HttpFetcher(
            client=client,
            resolver=resolver,
            max_bytes=64,
        ).fetch("https://public.example/document")

    assert resolved_hosts == ["public.example"]
    assert response.status_code == 200
    assert response.content_type == "text/plain"
    assert response.text == "policy body"


async def test_fetcher_enforces_redirect_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": f"{request.url.path}/next"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(
            client=client,
            resolver=public_resolver,
            max_redirects=1,
        )
        with pytest.raises(RedirectLimitError):
            await fetcher.fetch("https://public.example/start")
