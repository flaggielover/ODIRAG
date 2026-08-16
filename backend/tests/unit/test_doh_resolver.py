from __future__ import annotations

import ssl
from collections.abc import Iterable

import httpcore
import httpx
import pytest
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream
from httpcore._backends.mock import AsyncMockStream
from pydantic import ValidationError

from app.config import Settings
from app.crawler import (
    DnsResolutionError,
    DohHostResolver,
    HttpFetcher,
    PinnedAsyncHTTPTransport,
    PinnedNetworkBackend,
    UnsafeUrlError,
)
from app.crawler.urls import validate_public_url
from app.services.source_discovery import build_source_discovery_fetcher


def _dns_response(record_type: str, values: tuple[str, ...]) -> httpx.Response:
    type_id = 1 if record_type == "A" else 28
    return httpx.Response(
        200,
        headers={"content-type": "application/dns-json"},
        json={
            "Status": 0,
            "Answer": [
                {"name": "official.example", "type": type_id, "TTL": 60, "data": value}
                for value in values
            ],
        },
    )


def _resolver_client(
    *,
    ipv4: tuple[str, ...] = ("203.0.113.10",),
    ipv6: tuple[str, ...] = (),
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        record_type = request.url.params["type"]
        return _dns_response(record_type, ipv4 if record_type == "A" else ipv6)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_doh_resolver_returns_unique_a_and_aaaa_records() -> None:
    async with _resolver_client(
        ipv4=("93.184.216.34", "93.184.216.34"),
        ipv6=("2606:2800:220:1:248:1893:25c8:1946",),
    ) as client:
        resolver = DohHostResolver("https://1.1.1.1/dns-query", client=client)
        assert await resolver("official.example") == (
            "93.184.216.34",
            "2606:2800:220:1:248:1893:25c8:1946",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ipv4,ipv6",
    [
        (("10.0.0.8",), ()),
        (("198.18.0.24",), ()),
        (("93.184.216.34", "10.0.0.8"), ()),
        (("93.184.216.34",), ("fe80::1",)),
        ((), ("fec0::1",)),
        (("93.184.216.34",), ("fec0::1",)),
    ],
)
async def test_trusted_dns_still_rejects_non_public_and_mixed_results(
    ipv4: tuple[str, ...], ipv6: tuple[str, ...]
) -> None:
    async with _resolver_client(ipv4=ipv4, ipv6=ipv6) as client:
        resolver = DohHostResolver("https://1.1.1.1/dns-query", client=client)
        with pytest.raises(UnsafeUrlError, match="non-public"):
            await validate_public_url("https://official.example/path", resolver=resolver)


@pytest.mark.asyncio
async def test_trusted_dns_allows_genuine_public_resolution() -> None:
    async with _resolver_client(ipv4=("93.184.216.34",)) as client:
        resolver = DohHostResolver("https://1.1.1.1/dns-query", client=client)
        assert (
            await validate_public_url("https://official.example/path", resolver=resolver)
            == "https://official.example/path"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(302, headers={"location": "https://elsewhere.example/dns-query"}),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"Status": 2}),
        httpx.Response(200, json={"Status": 0, "Answer": {}}),
        httpx.Response(200, content=b"x" * (64 * 1024 + 1)),
    ],
)
async def test_doh_resolver_fails_closed_for_invalid_responses(
    response: httpx.Response,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: response)
    ) as client:
        resolver = DohHostResolver("https://1.1.1.1/dns-query", client=client)
        with pytest.raises(DnsResolutionError):
            await resolver("official.example")


@pytest.mark.asyncio
async def test_doh_resolver_fails_closed_for_timeout() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
        resolver = DohHostResolver("https://1.1.1.1/dns-query", client=client)
        with pytest.raises(DnsResolutionError):
            await resolver("official.example")


@pytest.mark.asyncio
async def test_fetcher_revalidates_same_host_and_blocks_rebinding() -> None:
    a_queries = 0

    def dns_handler(request: httpx.Request) -> httpx.Response:
        nonlocal a_queries
        record_type = request.url.params["type"]
        if record_type == "AAAA":
            return _dns_response("AAAA", ())
        a_queries += 1
        value = "93.184.216.34" if a_queries == 1 else "198.18.0.24"
        return _dns_response("A", (value,))

    site_requests = 0

    def site_handler(request: httpx.Request) -> httpx.Response:
        nonlocal site_requests
        site_requests += 1
        return httpx.Response(302, headers={"location": "/second"}, request=request)

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(dns_handler)) as dns_client,
        httpx.AsyncClient(transport=httpx.MockTransport(site_handler)) as site_client,
    ):
        resolver = DohHostResolver("https://1.1.1.1/dns-query", client=dns_client)
        fetcher = HttpFetcher(client=site_client, resolver=resolver)
        with pytest.raises(UnsafeUrlError, match="non-public"):
            await fetcher.fetch("https://official.example/first")

    assert site_requests == 1
    assert a_queries == 2


class _RecordingBackend(AsyncNetworkBackend):
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore test double
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        del port, timeout, local_address, socket_options
        self.hosts.append(host)
        return AsyncMockStream([])

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore test double
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        del path, timeout, socket_options
        raise AssertionError("unexpected Unix socket connection")

    async def sleep(self, seconds: float) -> None:
        del seconds


@pytest.mark.asyncio
async def test_pinned_backend_connects_to_validated_address_not_hostname() -> None:
    async def resolver(_hostname: str) -> tuple[str, ...]:
        return ("93.184.216.34",)

    backend = _RecordingBackend()
    pinned = PinnedNetworkBackend(resolver, backend=backend)
    await pinned.connect_tcp("official.example", 443)

    assert backend.hosts == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_pinned_backend_blocks_rebinding_before_socket_connect() -> None:
    calls = 0

    async def resolver(_hostname: str) -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        return ("93.184.216.34",) if calls == 1 else ("198.18.0.24",)

    backend = _RecordingBackend()
    await validate_public_url("https://official.example/path", resolver=resolver)
    pinned = PinnedNetworkBackend(resolver, backend=backend)

    with pytest.raises(httpcore.ConnectError, match="validated DNS resolution failed"):
        await pinned.connect_tcp("official.example", 443)

    assert backend.hosts == []


class _InspectableStream(AsyncMockStream):
    def __init__(self) -> None:
        super().__init__([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"])
        self.server_hostname: str | None = None
        self.writes: list[bytes] = []

    async def write(
        self,
        buffer: bytes,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore test double
    ) -> None:
        del timeout
        self.writes.append(buffer)

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore test double
    ) -> AsyncNetworkStream:
        del ssl_context, timeout
        self.server_hostname = server_hostname
        return self


class _InspectableBackend(_RecordingBackend):
    def __init__(self) -> None:
        super().__init__()
        self.stream = _InspectableStream()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore test double
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        del port, timeout, local_address, socket_options
        self.hosts.append(host)
        return self.stream


@pytest.mark.asyncio
async def test_pinned_transport_preserves_original_host_and_tls_sni() -> None:
    async def resolver(_hostname: str) -> tuple[str, ...]:
        return ("93.184.216.34",)

    backend = _InspectableBackend()
    transport = PinnedAsyncHTTPTransport(resolver, backend=backend)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://official.example/path")

    request_bytes = b"".join(backend.stream.writes).lower()
    assert response.status_code == 200
    assert backend.hosts == ["93.184.216.34"]
    assert backend.stream.server_hostname == "official.example"
    assert b"host: official.example" in request_bytes


def test_validation_dns_config_requires_https_and_builds_shared_fetcher() -> None:
    with pytest.raises(ValidationError, match="requires an HTTPS endpoint"):
        Settings(source_discovery_validation_dns_url="http://resolver.example/dns-query")

    settings = Settings(
        source_discovery_validation_dns_url="https://1.1.1.1/dns-query/",
        source_discovery_validation_dns_timeout_seconds=3,
    )
    fetcher = build_source_discovery_fetcher(settings, user_agent="test-agent")

    assert settings.source_discovery_validation_dns_url == "https://1.1.1.1/dns-query"
    assert isinstance(fetcher._resolver, DohHostResolver)
    assert fetcher._resolver.timeout_seconds == 3
    assert fetcher.user_agent == "test-agent"
