from __future__ import annotations

import httpx
import pytest

from app.providers import ProviderResponseError, ProviderUnavailableError
from app.source_discovery.providers import BraveCandidateDiscoveryProvider


async def test_brave_candidate_provider_parses_real_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "secret"
        assert request.url.params["q"] == "software policy official"
        return httpx.Response(
            200,
            request=request,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Official agency",
                            "url": "https://agency.gov.cn/?utm_source=search",
                            "description": "Government policy portal",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = BraveCandidateDiscoveryProvider(
            endpoint="https://api.search.brave.com/res/v1/web/search",
            api_key="secret",
            timeout_seconds=1,
            client=client,
        )
        results = await provider.search("software policy official", limit=5)

    assert len(results) == 1
    assert results[0].url == "https://agency.gov.cn/"
    assert results[0].rank == 1


async def test_brave_candidate_provider_reports_missing_credentials() -> None:
    provider = BraveCandidateDiscoveryProvider(
        endpoint="https://api.search.brave.com/res/v1/web/search",
        api_key=None,
        timeout_seconds=1,
    )

    with pytest.raises(ProviderUnavailableError, match="credentials"):
        await provider.search("policy", limit=5)


async def test_brave_candidate_provider_rejects_invalid_response_shape() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, request=request, json={"web": {"results": "not-a-list"}}
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        provider = BraveCandidateDiscoveryProvider(
            endpoint="https://api.search.brave.com/res/v1/web/search",
            api_key="secret",
            timeout_seconds=1,
            client=client,
        )
        with pytest.raises(ProviderResponseError, match="not a list"):
            await provider.search("policy", limit=5)
