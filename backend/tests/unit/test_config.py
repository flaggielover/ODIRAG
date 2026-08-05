import pytest
from pydantic import ValidationError

from app.config import Settings


def test_sync_database_url_maps_supported_async_drivers() -> None:
    postgres = Settings(database_url="postgresql+asyncpg://user:pass@db/odirag")
    sqlite = Settings(database_url="sqlite+aiosqlite:///test.db")

    assert postgres.sync_database_url == "postgresql+psycopg://user:pass@db/odirag"
    assert sqlite.sync_database_url == "sqlite+pysqlite:///test.db"


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="jwt_secret_key"):
        Settings(environment="production", bootstrap_admin=False)


def test_production_bootstrap_requires_admin_hash() -> None:
    with pytest.raises(ValidationError, match="admin_password_hash"):
        Settings(
            environment="production",
            jwt_secret_key="a-production-secret-that-is-long-enough",
            bootstrap_admin=True,
        )


def test_production_accepts_empty_optional_secret_as_unset() -> None:
    settings = Settings(
        environment="production",
        jwt_secret_key="a-production-secret-that-is-long-enough",
        bootstrap_admin=True,
        admin_password="",
        admin_password_hash="$2b$12$production-password-hash",
        cors_origins=["https://admin.example"],
        embedding_provider="remote",
        embedding_cache_provider="redis",
        vector_store_provider="qdrant",
        rerank_provider="none",
    )

    assert settings.admin_password is None
    assert settings.admin_password_hash is not None


def test_production_rejects_deterministic_source_discovery() -> None:
    with pytest.raises(ValidationError, match="deterministic source discovery"):
        Settings(
            environment="production",
            jwt_secret_key="a-production-secret-that-is-long-enough",
            bootstrap_admin=False,
            admin_password="",
            source_discovery_provider="deterministic",
            cors_origins=["https://admin.example"],
        )


def test_production_rejects_untrusted_source_discovery_endpoint() -> None:
    with pytest.raises(ValidationError, match="official HTTPS endpoint"):
        Settings(
            environment="production",
            jwt_secret_key="a-production-secret-that-is-long-enough",
            bootstrap_admin=False,
            admin_password="",
            source_discovery_search_url="https://proxy.example/search",
            cors_origins=["https://admin.example"],
        )


@pytest.mark.parametrize(
    "update",
    [
        {"embedding_provider": "deterministic"},
        {"embedding_cache_provider": "memory"},
        {"vector_store_provider": "memory"},
        {"rerank_provider": "deterministic"},
    ],
)
def test_production_rejects_demo_only_providers(update: dict[str, object]) -> None:
    values: dict[str, object] = {
        "environment": "production",
        "jwt_secret_key": "a-production-secret-that-is-long-enough",
        "bootstrap_admin": False,
        "admin_password": "",
        "cors_origins": ["https://admin.example"],
    }
    values.update(update)

    with pytest.raises(ValidationError, match="demo-only providers"):
        Settings(**values)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"debug": True}, "debug"),
        ({"admin_password": "plaintext"}, "plaintext"),
        ({"rate_limit_enabled": False}, "rate limiting"),
        ({"cors_origins": ["*"]}, "cors_origins"),
        ({"cors_origins": ["http://admin.example"]}, "cors_origins"),
    ],
)
def test_production_rejects_insecure_runtime_options(
    updates: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "environment": "production",
        "jwt_secret_key": "a-production-secret-that-is-long-enough",
        "bootstrap_admin": False,
        "admin_password": None,
        "cors_origins": ["https://admin.example"],
        "embedding_provider": "remote",
        "embedding_cache_provider": "redis",
        "vector_store_provider": "qdrant",
        "rerank_provider": "none",
    }
    values.update(updates)
    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_comma_separated_cors_origins_are_normalized() -> None:
    settings = Settings(cors_origins="https://one.example, https://two.example")
    assert settings.cors_origins == ["https://one.example", "https://two.example"]


def test_trusted_proxy_ips_are_normalized_and_validated() -> None:
    settings = Settings(trusted_proxy_ips="172.30.0.10, 2001:db8::/64")
    assert settings.trusted_proxy_ips == ["172.30.0.10", "2001:db8::/64"]

    with pytest.raises(ValidationError, match="trusted_proxy_ips"):
        Settings(trusted_proxy_ips=["not-an-ip"])


def test_celery_urls_derive_separate_redis_databases() -> None:
    settings = Settings(redis_url="redis://cache.internal:6379/0")
    assert settings.effective_celery_broker_url == "redis://cache.internal:6379/1"
    assert settings.effective_celery_result_backend == "redis://cache.internal:6379/2"


def test_explicit_celery_urls_take_precedence() -> None:
    settings = Settings(
        celery_broker_url="redis://broker:6379/4",
        celery_result_backend="redis://results:6379/5",
    )
    assert settings.effective_celery_broker_url == "redis://broker:6379/4"
    assert settings.effective_celery_result_backend == "redis://results:6379/5"


def test_legacy_coze_environment_names_are_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COZE_ACCESS_TOKEN", "legacy-secret")
    monkeypatch.setenv("COZE_API_URL", "https://legacy.example/run")

    settings = Settings(_env_file=None)

    assert settings.coze_api_token is not None
    assert settings.coze_api_token.get_secret_value() == "legacy-secret"
    assert settings.coze_legacy_api_url == "https://legacy.example/run"
    assert "legacy-secret" not in repr(settings)


def test_canonical_coze_environment_overrides_empty_prefixed_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODIRAG_COZE_API_TOKEN", "")
    monkeypatch.setenv("COZE_API_TOKEN", "canonical-secret")
    monkeypatch.setenv("ODIRAG_COZE_BATCH_API_URL", "")
    monkeypatch.setenv("COZE_BATCH_API_URL", "https://batch.example/run")

    settings = Settings(_env_file=None)

    assert settings.coze_api_token is not None
    assert settings.coze_api_token.get_secret_value() == "canonical-secret"
    assert settings.coze_batch_api_url == "https://batch.example/run"
