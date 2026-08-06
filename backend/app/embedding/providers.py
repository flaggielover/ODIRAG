from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from app.providers import ProviderResponseError, ProviderUnavailableError


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class DeterministicEmbeddingProvider:
    """Stable local vectors for tests and explicitly enabled demo mode."""

    provider_name = "deterministic"
    model_name = "deterministic-sha256-v1"

    def __init__(self, dimensions: int = 32) -> None:
        if dimensions < 4:
            raise ValueError("dimensions must be at least 4")
        self.dimensions = dimensions

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values = [
            ((seed[index % len(seed)] / 255.0) * 2.0) - 1.0 for index in range(self.dimensions)
        ]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


class RemoteEmbeddingProvider:
    provider_name = "remote"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_name: str,
        dimensions: int | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # Environment values commonly contain accidental surrounding whitespace.
        # Treat a whitespace-only value as an unconfigured credential so it cannot
        # be sent as an Authorization header or masquerade as a live provider.
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.model_name = model_name
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise ProviderUnavailableError("remote_embedding", "API key is not configured")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            request_payload: dict[str, object] = {
                "model": self.model_name,
                "input": texts,
            }
            if self.dimensions is not None:
                request_payload["dimensions"] = self.dimensions
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request_payload,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("remote_embedding", str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            ordered = sorted(payload["data"], key=lambda item: item["index"])
            embeddings = [[float(value) for value in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderResponseError("remote_embedding", str(exc)) from exc
        if len(embeddings) != len(texts):
            raise ProviderResponseError("remote_embedding", "embedding count does not match input")
        return embeddings

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]
