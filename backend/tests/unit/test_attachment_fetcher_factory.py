from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.crawler import DohHostResolver, PinnedAsyncHTTPTransport
from app.services.attachment_fetcher import build_attachment_fetcher


def test_attachment_fetcher_requires_trusted_dns() -> None:
    settings = Settings(source_discovery_validation_dns_url=None)

    with pytest.raises(ValueError, match="trusted DNS"):
        build_attachment_fetcher(settings)


@pytest.mark.asyncio
async def test_attachment_fetcher_uses_shared_resolver_and_pinned_transport() -> None:
    settings = Settings(
        source_discovery_validation_dns_url="https://1.1.1.1/dns-query",
        source_discovery_validation_dns_timeout_seconds=3,
        crawler_timeout_seconds=7,
        crawler_max_redirects=4,
        max_download_bytes=4096,
    )

    fetcher = build_attachment_fetcher(settings, user_agent="attachment-test")

    assert isinstance(fetcher._resolver, DohHostResolver)
    assert fetcher._resolver.timeout_seconds == 3
    assert fetcher.max_bytes == 4096
    assert fetcher.max_redirects == 4
    assert fetcher.user_agent == "attachment-test"
    assert fetcher._client_factory is not None

    client = fetcher._client_factory()
    try:
        assert isinstance(client, httpx.AsyncClient)
        assert isinstance(client._transport, PinnedAsyncHTTPTransport)
    finally:
        await client.aclose()
