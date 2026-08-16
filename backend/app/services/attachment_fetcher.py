from __future__ import annotations

from collections.abc import Callable

import httpx

from app.config import Settings
from app.crawler import DohHostResolver, HttpFetcher, PinnedAsyncHTTPTransport


def build_attachment_fetcher(
    settings: Settings,
    *,
    user_agent: str = "ODIRAG/0.1 attachment-downloader",
) -> HttpFetcher:
    """Build an attachment fetcher whose validation and socket DNS cannot diverge."""

    endpoint = settings.source_discovery_validation_dns_url
    if endpoint is None:
        raise ValueError("attachment downloads require a trusted DNS endpoint")
    resolver = DohHostResolver(
        endpoint,
        timeout_seconds=settings.source_discovery_validation_dns_timeout_seconds,
    )
    return HttpFetcher(
        timeout_seconds=settings.crawler_timeout_seconds,
        max_bytes=settings.max_download_bytes,
        max_redirects=settings.crawler_max_redirects,
        user_agent=user_agent,
        resolver=resolver,
        client_factory=_pinned_client_factory(resolver, settings.crawler_timeout_seconds),
    )


def _pinned_client_factory(
    resolver: DohHostResolver,
    timeout_seconds: float,
) -> Callable[[], httpx.AsyncClient]:
    return lambda: httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=False,
        trust_env=False,
        transport=PinnedAsyncHTTPTransport(resolver),
    )
