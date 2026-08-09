from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_sync_database_url_maps_supported_async_drivers() -> None:
    postgres = Settings(database_url="postgresql+asyncpg://user:pass@db/odirag")
    sqlite = Settings(database_url="sqlite+aiosqlite:///test.db")

    assert postgres.sync_database_url == "postgresql+psycopg://user:pass@db/odirag"
    assert sqlite.sync_database_url == "sqlite+pysqlite:///test.db"


def test_evidence_sufficiency_thresholds_are_fail_closed() -> None:
    settings = Settings(
        evidence_sufficiency_minimum_confidence=0.45,
        evidence_sufficiency_minimum_hit_contribution=0.08,
    )
    assert settings.evidence_sufficiency_minimum_confidence == 0.45
    assert settings.evidence_sufficiency_minimum_hit_contribution == 0.08
    assert settings.evidence_sufficiency_minimum_answer_overlap == 0.2

    with pytest.raises(ValidationError, match="evidence_sufficiency_minimum_confidence"):
        Settings(evidence_sufficiency_minimum_confidence=0.44)

    with pytest.raises(ValidationError, match="evidence_sufficiency_minimum_hit_contribution"):
        Settings(evidence_sufficiency_minimum_hit_contribution=0.04)

    with pytest.raises(ValidationError, match="evidence_sufficiency_minimum_answer_overlap"):
        Settings(evidence_sufficiency_minimum_answer_overlap=0.19)


def test_rerank_runtime_settings_have_safe_defaults_and_environment_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings(_env_file=None)
    assert defaults.rerank_timeout_seconds == 30.0
    assert defaults.rerank_failure_policy == "open"

    monkeypatch.setenv("ODIRAG_RERANK_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("ODIRAG_RERANK_FAILURE_POLICY", "closed")
    configured = Settings(_env_file=None)
    assert configured.rerank_timeout_seconds == 12.5
    assert configured.rerank_failure_policy == "closed"

    with pytest.raises(ValidationError, match="rerank_failure_policy"):
        Settings(rerank_failure_policy="ignore")


def test_production_remote_rerank_requires_https() -> None:
    with pytest.raises(ValidationError, match="remote rerank requires an HTTPS endpoint"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="a-production-secret-that-is-long-enough",
            bootstrap_admin=False,
            admin_password=None,
            cors_origins=["https://admin.example"],
            rerank_provider="remote",
            rerank_base_url="http://rerank.example/v2",
        )


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


def test_source_discovery_rejects_non_runtime_provider() -> None:
    with pytest.raises(ValidationError, match="source_discovery_provider"):
        Settings(
            source_discovery_provider="deterministic",
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('["health", " education ", "health"]', ["health", "education"]),
        ("Health, education, health", ["Health", "education"]),
        ("   ", []),
    ],
)
def test_automatic_source_discovery_topics_accept_json_csv_and_empty(
    value: str, expected: list[str]
) -> None:
    settings = Settings(source_discovery_auto_topics=value)
    assert settings.source_discovery_auto_topics == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ('["policy", " industry "]', ["policy", "industry"]),
        ("policy, industry", ["policy", "industry"]),
        ("", []),
    ],
)
def test_automatic_source_discovery_topics_environment_formats(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: list[str],
) -> None:
    monkeypatch.setenv("ODIRAG_SOURCE_DISCOVERY_AUTO_TOPICS", raw_value)

    settings = Settings(_env_file=None)

    assert settings.source_discovery_auto_topics == expected


@pytest.mark.parametrize(
    "raw_value",
    [
        '["policy"',
        '["policy", 42]',
        '{"topic":"policy"}',
        '"policy"',
    ],
)
def test_invalid_automatic_source_discovery_topics_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    monkeypatch.setenv("ODIRAG_SOURCE_DISCOVERY_AUTO_TOPICS", raw_value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    message = str(exc_info.value)
    assert "source_discovery_auto_topics" in message
    assert raw_value not in message


def test_automatic_source_discovery_interval_has_a_safe_lower_bound() -> None:
    with pytest.raises(ValidationError, match="source_discovery_auto_interval_seconds"):
        Settings(source_discovery_auto_interval_seconds=299)


def test_automatic_source_discovery_accepts_min_interval_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ODIRAG_SOURCE_DISCOVERY_AUTO_INTERVAL_SECONDS", raising=False)
    monkeypatch.setenv("ODIRAG_SOURCE_DISCOVERY_AUTO_MIN_INTERVAL_SECONDS", "600")

    settings = Settings(_env_file=None)

    assert settings.source_discovery_auto_interval_seconds == 600


def test_automatic_source_discovery_requires_topics_in_production() -> None:
    with pytest.raises(ValidationError, match="source_discovery_auto_topics"):
        Settings(
            environment="production",
            jwt_secret_key="a-production-secret-that-is-long-enough",
            bootstrap_admin=False,
            admin_password="",
            cors_origins=["https://admin.example"],
            source_discovery_auto_enabled=True,
            embedding_provider="remote",
            embedding_cache_provider="redis",
            vector_store_provider="qdrant",
            rerank_provider="none",
        )


def test_automatic_source_discovery_rejects_disabled_provider_in_production() -> None:
    with pytest.raises(ValidationError, match="enabled discovery provider"):
        Settings(
            environment="production",
            jwt_secret_key="a-production-secret-that-is-long-enough",
            bootstrap_admin=False,
            admin_password="",
            cors_origins=["https://admin.example"],
            source_discovery_provider="disabled",
            source_discovery_auto_enabled=True,
            source_discovery_auto_topics=["health"],
            embedding_provider="remote",
            embedding_cache_provider="redis",
            vector_store_provider="qdrant",
            rerank_provider="none",
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


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("172.30.0.10, 2001:db8::/64", ["172.30.0.10", "2001:db8::/64"]),
        ('[" 172.30.0.10 ", "2001:db8::/64"]', ["172.30.0.10", "2001:db8::/64"]),
        ("", []),
        ("   ", []),
        ("[]", []),
    ],
)
def test_trusted_proxy_ips_environment_formats(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: list[str],
) -> None:
    monkeypatch.setenv("ODIRAG_TRUSTED_PROXY_IPS", raw_value)

    settings = Settings(_env_file=None)

    assert settings.trusted_proxy_ips == expected


def test_compose_csv_trusted_proxy_environment_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ODIRAG_TRUSTED_PROXY_IPS", " 172.30.0.10 , 10.0.0.0/8 ")

    settings = Settings(_env_file=None)

    assert settings.trusted_proxy_ips == ["172.30.0.10", "10.0.0.0/8"]


def test_dotenv_csv_trusted_proxy_environment_regression() -> None:
    env_file = Path(".tmp") / f"config-compat-{uuid4().hex}.env"
    try:
        env_file.write_text(
            "ODIRAG_TRUSTED_PROXY_IPS= 172.30.0.10 , 10.0.0.0/8 \n",
            encoding="utf-8",
        )

        settings = Settings(_env_file=env_file)

        assert settings.trusted_proxy_ips == ["172.30.0.10", "10.0.0.0/8"]
    finally:
        env_file.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "raw_value",
    [
        '["172.30.0.10"',
        '["http://proxy-user:proxy-password@example.invalid"]',
        '["172.30.0.10", 42]',
    ],
)
def test_invalid_trusted_proxy_environment_errors_are_safe(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    monkeypatch.setenv("ODIRAG_TRUSTED_PROXY_IPS", raw_value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    message = str(exc_info.value)
    assert "trusted_proxy_ips" in message
    assert "proxy-user" not in message
    assert "proxy-password" not in message
    assert raw_value not in message


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


def test_legacy_coze_environment_names_are_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
