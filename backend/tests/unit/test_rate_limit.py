from __future__ import annotations

from ipaddress import ip_network

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.config import Settings
from app.main import create_app
from app.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    RateLimitBackendUnavailable,
    RedisFixedWindowRateLimiter,
    _identity,
)


async def test_fixed_window_limiter_is_atomic_and_resets() -> None:
    now = 0.0
    limiter = InMemoryFixedWindowRateLimiter(clock=lambda: now)

    first = await limiter.check("login:client", limit=2, window_seconds=60)
    second = await limiter.check("login:client", limit=2, window_seconds=60)
    rejected = await limiter.check("login:client", limit=2, window_seconds=60)

    assert first.allowed and first.remaining == 1
    assert second.allowed and second.remaining == 0
    assert not rejected.allowed

    now = 61.0
    reset = await limiter.check("login:client", limit=2, window_seconds=60)
    assert reset.allowed and reset.remaining == 1


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.expirations.get(key, -1)

    async def aclose(self) -> None:
        return None

    async def eval(self, _script: str, _numkeys: int, key: str, seconds: str) -> list[int]:
        count = await self.incr(key)
        if count == 1:
            await self.expire(key, int(seconds))
        return [count, await self.ttl(key)]


async def test_redis_fixed_window_limiter_uses_shared_counter() -> None:
    redis = FakeRedis()
    limiter = RedisFixedWindowRateLimiter(
        "redis://unused/0", client=redis, clock=lambda: 1.0  # type: ignore[arg-type]
    )

    first = await limiter.check("auth:ip:test", limit=1, window_seconds=60)
    second = await limiter.check("auth:ip:test", limit=1, window_seconds=60)

    assert first.allowed and first.remaining == 0
    assert not second.allowed
    assert len(redis.values) == 1
    assert next(iter(redis.expirations.values())) == 59
    assert first.reset_after_seconds == 59


def test_application_passes_dependency_timeout_to_redis_limiter(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    captured: dict[str, object] = {}

    class CapturingLimiter:
        def __init__(self, redis_url: str, *, timeout_seconds: float) -> None:
            captured["redis_url"] = redis_url
            captured["timeout_seconds"] = timeout_seconds

        async def check(
            self, _key: str, *, limit: int, window_seconds: int
        ) -> object:  # pragma: no cover - the test only covers construction.
            raise AssertionError("not used")

        async def close(self) -> None:
            return None

    monkeypatch.setattr("app.main.RedisFixedWindowRateLimiter", CapturingLimiter)
    settings = test_settings.model_copy(
        update={
            "environment": "development",
            "rate_limit_backend": "redis",
            "dependency_timeout_seconds": 0.25,
        }
    )

    application = create_app(settings)

    assert application.state.rate_limiter is not None
    assert captured == {"redis_url": settings.redis_url, "timeout_seconds": 0.25}


def test_redis_limiter_uses_dependency_timeout_when_creating_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class CreatedRedis(FakeRedis):
        pass

    def create_client(url: str, **kwargs: object) -> CreatedRedis:
        captured["url"] = url
        captured.update(kwargs)
        return CreatedRedis()

    monkeypatch.setattr("app.rate_limit.Redis.from_url", create_client)
    limiter = RedisFixedWindowRateLimiter("redis://redis/0", timeout_seconds=0.25)

    assert isinstance(limiter._client, CreatedRedis)
    assert captured == {
        "url": "redis://redis/0",
        "decode_responses": True,
        "socket_connect_timeout": 0.25,
        "socket_timeout": 0.25,
    }


class BrokenRedis(FakeRedis):
    async def eval(self, _script: str, _numkeys: int, _key: str, _seconds: str) -> list[int]:
        raise ConnectionError("redis down")


async def test_redis_limiter_fails_closed_when_backend_is_unavailable() -> None:
    limiter = RedisFixedWindowRateLimiter(
        "redis://unused/0", client=BrokenRedis(), clock=lambda: 1.0  # type: ignore[arg-type]
    )

    with pytest.raises(RateLimitBackendUnavailable):
        await limiter.check("default:ip:test", limit=10, window_seconds=60)


async def test_login_rate_limit_uses_structured_error_contract(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"rate_limit_auth_requests": 2})
    application: FastAPI = create_app(settings)
    transport = httpx.ASGITransport(app=application)

    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        for _ in range(2):
            response = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "incorrect"},
            )
            assert response.status_code == 401

        limited = await client.post(
            "/api/auth/login",
            headers={"X-Request-ID": "rate-limit-test"},
            json={"username": "admin", "password": "incorrect"},
        )

    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert limited.headers["x-ratelimit-remaining"] == "0"
    assert limited.json() == {
        "error": {
            "code": "RATE_LIMITED",
            "message": "Too many requests",
            "details": {"profile": "auth"},
            "request_id": "rate-limit-test",
        }
    }


async def test_unverified_bearer_tokens_cannot_split_an_ip_rate_limit_bucket(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"rate_limit_default_requests": 2})
    application: FastAPI = create_app(settings)
    transport = httpx.ASGITransport(app=application)

    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        for token in ("forged-one", "forged-two"):
            response = await client.get(
                "/api/system/health", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
        limited = await client.get(
            "/api/system/health",
            headers={"Authorization": "Bearer forged-three"},
        )

    assert limited.status_code == 429
    assert limited.json()["error"]["details"] == {"profile": "default"}


@pytest.mark.parametrize(
    ("peer", "forwarded_for", "trusted_proxies", "expected"),
    [
        ("198.51.100.10", "203.0.113.20", (), "ip:198.51.100.10"),
        ("172.30.0.10", "203.0.113.20", ("172.30.0.10",), "ip:203.0.113.20"),
        ("172.30.0.10", "203.0.113.20, 198.51.100.1", ("172.30.0.10",), "ip:172.30.0.10"),
        ("172.30.0.10", "not-an-ip", ("172.30.0.10",), "ip:172.30.0.10"),
    ],
)
def test_rate_limit_identity_trusts_only_configured_single_hop_proxy(
    peer: str,
    forwarded_for: str,
    trusted_proxies: tuple[str, ...],
    expected: str,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/api/system/health",
            "raw_path": b"/api/system/health",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", forwarded_for.encode())],
            "client": (peer, 12345),
            "server": ("test", 80),
        }
    )
    networks = tuple(ip_network(value) for value in trusted_proxies)

    assert _identity(request, networks) == expected
