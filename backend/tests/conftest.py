from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://127.0.0.1:1/0",
        qdrant_url="http://127.0.0.1:1",
        dependency_timeout_seconds=0.1,
        health_check_qdrant=False,
        jwt_secret_key="test-jwt-secret-that-is-longer-than-thirty-two-characters",
        admin_username="admin",
        admin_password="correct horse battery staple",
        auto_create_schema=True,
        log_json=False,
        data_dir=Path(".test-data"),
        embedding_provider="deterministic",
        embedding_cache_provider="memory",
        embedding_dimensions=8,
        embedding_version="test-v1",
        vector_store_provider="memory",
        rerank_provider="deterministic",
        answer_provider="extractive",
        coze_enabled=False,
        coze_legacy_api_url=None,
        coze_batch_api_url=None,
        coze_api_token=None,
        coze_default_contract="batch_crawl",
        bm25_snapshot_path=Path(f".test-data/{uuid.uuid4()}-bm25.json"),
        evaluation_artifact_dir=Path(f".test-data/{uuid.uuid4()}-evaluation-runs"),
        experiment_artifact_dir=Path(f".test-data/{uuid.uuid4()}-experiment-runs"),
    )


@pytest.fixture
async def app(test_settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(test_settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
