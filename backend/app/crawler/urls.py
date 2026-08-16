from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import SplitResult, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

_TRACKING_PARAMETERS = {"spm", "from", "source"}

HostResolver = Callable[[str], Awaitable[Sequence[str]]]


class UnsafeUrlError(ValueError):
    """Raised when a crawl URL can reach a non-public network target."""


async def resolve_hostname(hostname: str) -> tuple[str, ...]:
    """Resolve all TCP addresses for a hostname without blocking the event loop."""

    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(hostname, 0, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for record in records:
        sockaddr = record[4]
        address = sockaddr[0]
        if isinstance(address, str) and address not in addresses:
            addresses.append(address)
    return tuple(addresses)


async def validate_public_url(
    url: str,
    *,
    resolver: HostResolver | None = None,
) -> str:
    """Validate an HTTP URL and reject targets outside the public internet."""

    candidate = url.strip()
    parsed = _split_http_url(candidate)
    host = _host(parsed)
    if "%" in host:
        raise UnsafeUrlError("scoped IP addresses are not allowed")

    try:
        address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is None:
        try:
            hostname = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UnsafeUrlError("URL host is invalid") from exc
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise UnsafeUrlError("localhost targets are not allowed")
        try:
            addresses = await (resolver or resolve_hostname)(hostname)
        except OSError as exc:
            raise UnsafeUrlError("URL host could not be resolved") from exc
        if not addresses:
            raise UnsafeUrlError("URL host did not resolve to an IP address")
        for resolved in addresses:
            _ensure_public_address(resolved)
    else:
        _ensure_public_address(address)
    return candidate


def normalize_url(url: str, *, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, url) if base_url else url
    parsed = _split_http_url(absolute.strip())
    host = _host(parsed)
    port = parsed.port
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    formatted_host = f"[{host}]" if ":" in host else host
    authority = formatted_host if port is None or default_port else f"{formatted_host}:{port}"
    path = parsed.path or "/"
    while "//" in path:
        path = path.replace("//", "/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
        )
    )
    return urlunsplit((parsed.scheme.lower(), authority, path, query, ""))


def _split_http_url(url: str) -> SplitResult:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL is malformed") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("only HTTP and HTTPS URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL credentials are not allowed")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeUrlError("URL port is invalid")
    if parsed.hostname is None:
        raise UnsafeUrlError("URL host is required")
    return parsed


def _host(parsed: SplitResult) -> str:
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeUrlError("URL host is required")
    return host


def _ensure_public_address(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        address = value
    else:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise UnsafeUrlError("DNS resolver returned an invalid IP address") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if (
        not address.is_global
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or (isinstance(address, ipaddress.IPv6Address) and address.is_site_local)
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UnsafeUrlError("URL target resolves to a non-public IP address")


def ensure_public_addresses(values: Sequence[str]) -> tuple[str, ...]:
    """Validate resolved addresses and return a stable, deduplicated tuple."""

    addresses = tuple(dict.fromkeys(values))
    if not addresses:
        raise UnsafeUrlError("URL host did not resolve to an IP address")
    for address in addresses:
        _ensure_public_address(address)
    return addresses
