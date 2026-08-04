from __future__ import annotations

import httpx
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app
from app.rate_limit import InMemoryFixedWindowRateLimiter


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
