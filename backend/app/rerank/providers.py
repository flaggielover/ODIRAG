from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import isfinite
from typing import Literal, Protocol, TypeAlias

import httpx

from app.providers import ProviderResponseError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float


CostMeasurement: TypeAlias = Literal["reported", "not_available", "not_applicable"]


@dataclass(frozen=True, slots=True)
class RerankResponse:
    """Provider response plus billing metadata that is safe to persist."""

    results: tuple[RerankResult, ...]
    usage: dict[str, int | float] = field(default_factory=dict)
    cost: float | None = None
    cost_measurement: CostMeasurement = "not_available"


RerankProviderOutput: TypeAlias = list[RerankResult] | RerankResponse


class RerankProvider(Protocol):
    provider_name: str
    model_name: str

    async def rerank(
        self, query: str, documents: list[str], top_k: int
    ) -> RerankProviderOutput: ...


class NoRerankProvider:
    provider_name = "none"
    model_name = "disabled"

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        del query
        return [
            RerankResult(index, float(len(documents) - index))
            for index in range(min(top_k, len(documents)))
        ]


class DeterministicRerankProvider:
    provider_name = "deterministic"
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
    provider_name = "remote"

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
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def rerank(self, query: str, documents: list[str], top_k: int) -> RerankResponse:
        if not documents:
            return RerankResponse((), cost_measurement="not_applicable")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
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
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError("remote_rerank", "request_timeout") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise ProviderUnavailableError("remote_rerank", f"http_status_{status}") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError("remote_rerank", "transport_error") from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("remote_rerank", "invalid_json") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ProviderResponseError("remote_rerank", "invalid_response_shape")

        results = _validate_results(payload["results"], len(documents), top_k)
        return RerankResponse(
            tuple(results),
            usage=_safe_usage(payload),
            cost=None,
            cost_measurement="not_available",
        )


def _validate_results(
    raw_results: list[object], document_count: int, top_k: int
) -> list[RerankResult]:
    if not raw_results:
        raise ProviderResponseError("remote_rerank", "empty_results")
    if len(raw_results) > min(document_count, top_k):
        raise ProviderResponseError("remote_rerank", "too_many_results")
    results: list[RerankResult] = []
    seen: set[int] = set()
    for item in raw_results:
        if not isinstance(item, dict):
            raise ProviderResponseError("remote_rerank", "invalid_result_shape")
        index = item.get("index")
        score = item.get("relevance_score")
        if not isinstance(index, int) or isinstance(index, bool):
            raise ProviderResponseError("remote_rerank", "invalid_result_index")
        if index in seen or not 0 <= index < document_count:
            raise ProviderResponseError("remote_rerank", "invalid_result_index")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ProviderResponseError("remote_rerank", "invalid_result_score")
        normalized_score = float(score)
        if not isfinite(normalized_score) or not 0 <= normalized_score <= 1:
            raise ProviderResponseError("remote_rerank", "invalid_result_score")
        seen.add(index)
        results.append(RerankResult(index, normalized_score))
    return results


def _safe_usage(payload: dict[str, object]) -> dict[str, int | float]:
    """Keep numeric billing counters only; provider text is never persisted."""

    usage: dict[str, int | float] = {}
    meta = payload.get("meta")
    if isinstance(meta, dict):
        billed_units = meta.get("billed_units")
        if isinstance(billed_units, dict):
            for key, value in billed_units.items():
                if (
                    isinstance(key, str)
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and isfinite(float(value))
                ):
                    usage[key] = value
    raw_usage = payload.get("usage")
    if isinstance(raw_usage, dict):
        for key, value in raw_usage.items():
            if (
                isinstance(key, str)
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and isfinite(float(value))
            ):
                usage.setdefault(key, value)
    return usage


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text)}
