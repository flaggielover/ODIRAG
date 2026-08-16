from __future__ import annotations

import ipaddress
import json
import ssl
from collections.abc import Iterable, Sequence
from urllib.parse import urlsplit

import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

from app.crawler.urls import HostResolver, ensure_public_addresses

_MAX_DNS_RESPONSE_BYTES = 64 * 1024


class DnsResolutionError(OSError):
    """Raised when the trusted validation resolver cannot return usable records."""


class DohHostResolver:
    """Resolve public-host validation records through a fixed HTTPS DNS endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("trusted DNS requires an HTTPS endpoint")
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def __call__(self, hostname: str) -> Sequence[str]:
        addresses: list[str] = []
        for record_type in ("A", "AAAA"):
            for address in await self._query(hostname, record_type):
                if address not in addresses:
                    addresses.append(address)
        if not addresses:
            raise DnsResolutionError("trusted DNS returned no address records")
        return tuple(addresses)

    async def _query(self, hostname: str, record_type: str) -> tuple[str, ...]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/dns-json"},
        )
        try:
            async with client.stream(
                "GET",
                self.endpoint,
                params={"name": hostname, "type": record_type},
                headers={"Accept": "application/dns-json"},
                timeout=self.timeout_seconds,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise DnsResolutionError("trusted DNS returned a non-success status")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > _MAX_DNS_RESPONSE_BYTES:
                        raise DnsResolutionError("trusted DNS response exceeded the size limit")
                    content.extend(chunk)
                payload = json.loads(content)
        except DnsResolutionError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DnsResolutionError("trusted DNS request failed") from exc
        finally:
            if owns_client:
                await client.aclose()

        if not isinstance(payload, dict) or payload.get("Status") != 0:
            raise DnsResolutionError("trusted DNS response was unsuccessful")
        answers = payload.get("Answer", [])
        if not isinstance(answers, list):
            raise DnsResolutionError("trusted DNS response has an invalid shape")
        expected_type = 1 if record_type == "A" else 28
        values: list[str] = []
        for item in answers:
            if not isinstance(item, dict) or item.get("type") != expected_type:
                continue
            value = item.get("data")
            if isinstance(value, str) and value not in values:
                values.append(value)
        return tuple(values)


class PinnedNetworkBackend(AsyncNetworkBackend):
    """Connect to a freshly validated address while preserving HTTP Host and TLS SNI."""

    def __init__(
        self,
        resolver: HostResolver,
        *,
        backend: AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._backend = backend or AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore interface
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        try:
            try:
                literal = ipaddress.ip_address(host)
            except ValueError:
                values = await self._resolver(host)
            else:
                values = (str(literal),)
            addresses = ensure_public_addresses(values)
        except (OSError, ValueError) as exc:
            raise httpcore.ConnectError("validated DNS resolution failed") from exc
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("validated DNS returned no usable addresses")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore interface
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        return await self._backend.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport whose socket DNS cannot diverge from SSRF validation DNS."""

    def __init__(
        self,
        resolver: HostResolver,
        *,
        backend: AsyncNetworkBackend | None = None,
    ) -> None:
        super().__init__(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=PinnedNetworkBackend(resolver, backend=backend),
        )
