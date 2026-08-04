from __future__ import annotations

import json
from typing import Protocol

from redis.asyncio import Redis

from app.providers import ProviderUnavailableError


class EmbeddingCache(Protocol):
    async def get(self, key: str) -> list[float] | None: ...

    async def set(self, key: str, vector: list[float]) -> None: ...


class InMemoryEmbeddingCache:
    def __init__(self) -> None:
        self.values: dict[str, list[float]] = {}

    async def get(self, key: str) -> list[float] | None:
        value = self.values.get(key)
        return list(value) if value is not None else None

    async def set(self, key: str, vector: list[float]) -> None:
        self.values[key] = list(vector)


class RedisEmbeddingCache:
    def __init__(self, redis_url: str, *, ttl_seconds: int = 30 * 24 * 3600) -> None:
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds

    async def get(self, key: str) -> list[float] | None:
        client = Redis.from_url(self.redis_url, decode_responses=True)
        try:
            value = await client.get(key)
        except Exception as exc:
            raise ProviderUnavailableError("redis_embedding_cache", str(exc)) from exc
        finally:
            await client.aclose()
        if value is None:
            return None
        payload = json.loads(value)
        if not isinstance(payload, list):
            return None
        return [float(item) for item in payload]

    async def set(self, key: str, vector: list[float]) -> None:
        client = Redis.from_url(self.redis_url, decode_responses=True)
        try:
            await client.set(key, json.dumps(vector), ex=self.ttl_seconds)
        except Exception as exc:
            raise ProviderUnavailableError("redis_embedding_cache", str(exc)) from exc
        finally:
            await client.aclose()
