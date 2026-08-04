from __future__ import annotations

import httpx


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
