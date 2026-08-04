from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.crawler.urls import normalize_url
from app.providers import ProviderResponseError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class CandidateHit:
    url: str
    title: str
    snippet: str | None
    rank: int


class CandidateDiscoveryProvider(Protocol):
    name: str

    async def search(self, query: str, *, limit: int) -> list[CandidateHit]: ...


class BraveCandidateDiscoveryProvider:
    """Brave Search API adapter; no credentials means explicit unavailability."""

    name = "brave"

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str | None,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def search(self, query: str, *, limit: int) -> list[CandidateHit]:
        if not self.api_key:
            raise ProviderUnavailableError(
                "brave-source-discovery", "API credentials are not configured"
            )
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            try:
                response = await client.get(
                    self.endpoint,
                    params={"q": query, "count": limit},
                    headers={
                        "X-Subscription-Token": self.api_key,
                        "Accept": "application/json",
                    },
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(
                    "brave-source-discovery", exc.__class__.__name__
                ) from exc
            if response.status_code >= 500:
                raise ProviderUnavailableError(
                    "brave-source-discovery", f"HTTP {response.status_code}"
                )
            if response.status_code >= 400:
                raise ProviderResponseError(
                    "brave-source-discovery", f"HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderResponseError(
                    "brave-source-discovery", "response is not JSON"
                ) from exc
            raw_items = payload.get("web", {}).get("results") if isinstance(payload, dict) else None
            if raw_items is None:
                return []
            if not isinstance(raw_items, list):
                raise ProviderResponseError("brave-source-discovery", "web.results is not a list")
            hits: list[CandidateHit] = []
            for rank, raw in enumerate(raw_items[:limit], start=1):
                if not isinstance(raw, dict) or not isinstance(raw.get("url"), str):
                    continue
                try:
                    normalized = normalize_url(raw["url"])
                except ValueError:
                    continue
                parsed = urlsplit(normalized)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    continue
                title = raw.get("title")
                if not isinstance(title, str) or not title.strip():
                    title = parsed.hostname
                snippet = raw.get("description")
                hits.append(
                    CandidateHit(
                        url=normalized,
                        title=title.strip(),
                        snippet=snippet.strip() if isinstance(snippet, str) else None,
                        rank=rank,
                    )
                )
            return hits
        finally:
            if owns_client:
                await client.aclose()


class DisabledCandidateDiscoveryProvider:
    name = "disabled"

    async def search(self, _query: str, *, limit: int) -> list[CandidateHit]:
        del limit
        raise ProviderUnavailableError("source-discovery", "candidate discovery is disabled")


def build_candidate_provider(settings: Settings) -> CandidateDiscoveryProvider:
    if settings.source_discovery_provider == "disabled":
        return DisabledCandidateDiscoveryProvider()
    if settings.source_discovery_provider == "deterministic":
        if settings.environment not in {"development", "test"}:
            raise ProviderUnavailableError(
                "source-discovery", "deterministic provider is restricted to development/test"
            )
        raise ProviderUnavailableError(
            "source-discovery", "deterministic provider must be injected by a test or demo"
        )
    return BraveCandidateDiscoveryProvider(
        endpoint=settings.source_discovery_search_url,
        api_key=(
            settings.source_discovery_api_key.get_secret_value()
            if settings.source_discovery_api_key
            else None
        ),
        timeout_seconds=settings.source_discovery_timeout_seconds,
    )
