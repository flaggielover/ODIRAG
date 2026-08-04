from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.cache import EmbeddingCache
from app.embedding.providers import EmbeddingProvider
from app.providers import ProviderResponseError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    vectors: tuple[tuple[float, ...], ...]
    cache_hits: int
    embedded_count: int
    input_chars: int
    estimated_cost: float


class EmbeddingBatcher:
    def __init__(
        self,
        provider: EmbeddingProvider,
        cache: EmbeddingCache,
        *,
        batch_size: int = 32,
        minimum_interval_seconds: float = 0.0,
        cost_per_1k_chars: float = 0.0,
        version: str = "v1",
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.provider = provider
        self.cache = cache
        self.batch_size = batch_size
        self.minimum_interval_seconds = minimum_interval_seconds
        self.cost_per_1k_chars = cost_per_1k_chars
        self.version = version

    async def embed(self, texts: list[str]) -> EmbeddingBatchResult:
        vectors: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str, str]] = []
        cache_hits = 0
        for index, value in enumerate(texts):
            key = self._key(value)
            cached = await self.cache.get(key)
            if cached is None:
                missing.append((index, key, value))
            else:
                vectors[index] = cached
                cache_hits += 1
        embedded_count = 0
        for offset in range(0, len(missing), self.batch_size):
            batch = missing[offset : offset + self.batch_size]
            if offset and self.minimum_interval_seconds:
                await asyncio.sleep(self.minimum_interval_seconds)
            embedded = await self._embed_with_retry([item[2] for item in batch])
            if len(embedded) != len(batch):
                raise ProviderResponseError("embedding", "provider returned an unexpected count")
            for (index, key, _value), vector in zip(batch, embedded, strict=True):
                vectors[index] = vector
                await self.cache.set(key, vector)
                embedded_count += 1
        if any(vector is None for vector in vectors):
            raise ProviderResponseError("embedding", "one or more vectors are missing")
        normalized = tuple(tuple(vector or []) for vector in vectors)
        input_chars = sum(len(value) for _, _, value in missing)
        return EmbeddingBatchResult(
            normalized,
            cache_hits,
            embedded_count,
            input_chars,
            round((input_chars / 1000) * self.cost_per_1k_chars, 8),
        )

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((ProviderUnavailableError, ProviderResponseError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.1, min=0, max=1),
            reraise=True,
        ):
            with attempt:
                return await self.provider.embed_documents(texts)
        raise RuntimeError("embedding retry loop exited without a result")

    def _key(self, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return (
            f"embedding:{self.provider.provider_name}:{self.provider.model_name}:"
            f"{self.version}:{digest}"
        )
