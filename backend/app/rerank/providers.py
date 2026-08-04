from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.providers import ProviderResponseError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float


class RerankProvider(Protocol):
    model_name: str

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]: ...


class NoRerankProvider:
    model_name = "disabled"

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        del query
        return [
            RerankResult(index, float(len(documents) - index))
            for index in range(min(top_k, len(documents)))
        ]


class DeterministicRerankProvider:
    model_name = "deterministic-token-overlap-v1"

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        query_terms = _terms(query)
        scored = []
        for index, document in enumerate(documents):
            document_terms = _terms(document)
            denominator = len(query_terms | document_terms) or 1
            scored.append(RerankResult(index, len(query_terms & document_terms) / denominator))
        return sorted(scored, key=lambda result: (-result.score, result.index))[:top_k]


class RemoteRerankProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_name: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        if not self.api_key:
            raise ProviderUnavailableError("remote_rerank", "API key is not configured")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(
                f"{self.base_url}/rerank",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("remote_rerank", str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            return [
                RerankResult(int(item["index"]), float(item["relevance_score"]))
                for item in payload["results"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderResponseError("remote_rerank", str(exc)) from exc


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text)}
