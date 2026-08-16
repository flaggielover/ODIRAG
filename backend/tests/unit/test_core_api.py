from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.rate_limit import RateLimitBackendUnavailable
from app.schemas.system import DependencyHealth, HealthResponse


async def test_login_me_and_refresh(client: httpx.AsyncClient) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] != tokens["refresh_token"]

    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["is_superuser"] is True

    refreshed = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    refreshed_tokens = refreshed.json()
    assert refreshed_tokens["access_token"] != tokens["access_token"]

    replay = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    revoked_access = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert revoked_access.status_code == 401

    active_access = {"Authorization": f"Bearer {refreshed_tokens['access_token']}"}
    assert (await client.get("/api/auth/me", headers=active_access)).status_code == 200

    logout = await client.post("/api/auth/logout", headers=active_access)
    assert logout.status_code == 204
    assert (await client.get("/api/auth/me", headers=active_access)).status_code == 401


async def test_authentication_errors_are_structured(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        headers={"X-Request-ID": "test-request-id"},
        json={"username": "admin", "password": "incorrect"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "code": "AUTHENTICATION_FAILED",
            "message": "Username or password is incorrect",
            "request_id": "test-request-id",
        }
    }


async def test_me_requires_bearer_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_health_reports_real_degraded_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"]["status"] == "healthy"
    assert body["dependencies"]["redis"]["status"] == "unavailable"
    assert body["dependencies"]["qdrant"]["status"] == "disabled"


async def test_liveness_probe_is_dependency_free(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_probes_bypass_rate_limit_backend(
    app: FastAPI,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_limiter(*_args: object, **_kwargs: object) -> object:
        raise RateLimitBackendUnavailable("credential=limiter-secret")

    monkeypatch.setattr(app.state.rate_limiter, "check", unavailable_limiter)

    live = await client.get("/health/live")
    ready = await client.get("/health/ready")
    regular_api = await client.get("/api/system/health")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert "dependencies" in ready.json()
    assert regular_api.status_code == 503
    assert regular_api.json()["error"]["code"] == "RATE_LIMIT_BACKEND_UNAVAILABLE"


async def test_prometheus_metrics_bypass_rate_limit_and_use_route_templates(
    app: FastAPI,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_limiter(*_args: object, **_kwargs: object) -> object:
        raise RateLimitBackendUnavailable("credential=limiter-secret")

    # An unmatched path must not become a high-cardinality Prometheus label.
    await client.get("/missing/request-specific-value")
    monkeypatch.setattr(app.state.rate_limiter, "check", unavailable_limiter)

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "odirag_http_requests_total" in response.text
    assert 'route="<unmatched>"' in response.text
    assert "request-specific-value" not in response.text
    assert "limiter-secret" not in response.text

    second_scrape = await client.get("/metrics")
    assert 'route="/metrics"' in second_scrape.text
    assert 'route="/api/metrics"' not in second_scrape.text


async def test_prometheus_render_failure_is_generic(
    app: FastAPI,
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_render(_registry: object) -> bytes:
        raise RuntimeError("credential=metrics-secret")

    monkeypatch.setattr(type(app.state.metrics), "prometheus_payload", broken_render)

    response = await client.get("/metrics")

    assert response.status_code == 503
    assert "metrics-secret" not in response.text


async def test_readiness_requires_database_redis_and_qdrant(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"]["status"] == "healthy"
    assert body["dependencies"]["redis"]["status"] == "unavailable"
    assert body["dependencies"]["qdrant"]["status"] == "disabled"


async def test_readiness_returns_200_only_when_all_dependencies_are_healthy(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def healthy_check(_service: object) -> HealthResponse:
        return HealthResponse(
            status="healthy",
            service="test",
            environment="test",
            checked_at="2026-01-01T00:00:00Z",
            dependencies={
                name: DependencyHealth(status="healthy") for name in ("database", "redis", "qdrant")
            },
        )

    monkeypatch.setattr("app.api.routes.health.HealthService.check", healthy_check)
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


async def test_readiness_marks_disabled_dependency_as_degraded(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def disabled_qdrant_check(_service: object) -> HealthResponse:
        return HealthResponse(
            status="healthy",
            service="test",
            environment="test",
            checked_at="2026-01-01T00:00:00Z",
            dependencies={
                "database": DependencyHealth(status="healthy"),
                "redis": DependencyHealth(status="healthy"),
                "qdrant": DependencyHealth(status="disabled"),
            },
        )

    monkeypatch.setattr(
        "app.api.routes.health.HealthService.check",
        disabled_qdrant_check,
    )
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["dependencies"]["qdrant"]["status"] == "disabled"


async def test_readiness_does_not_expose_health_service_exceptions(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken_check(_service: object) -> HealthResponse:
        raise RuntimeError("credential=super-secret-value")

    monkeypatch.setattr("app.api.routes.health.HealthService.check", broken_check)
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert "super-secret-value" not in response.text
    database = response.json()["dependencies"]["database"]
    assert database["status"] == "unavailable"
    assert database["detail"] == "check failed"


async def test_metrics_require_admin_and_report_observed_requests(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    unauthorized = await client.get("/api/system/metrics")
    assert unauthorized.status_code == 401

    response = await client.get("/api/system/metrics", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["requests_total"] >= 2
    assert any(route["path"] == "/api/auth/login" for route in body["routes"])


async def test_validation_error_uses_error_contract(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/login", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
