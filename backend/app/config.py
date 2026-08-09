from __future__ import annotations

import json
from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ODIRAG_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    app_name: str = "ODIRAG API"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_json: bool | None = None

    database_url: str = "postgresql+asyncpg://odirag:odirag@localhost:5432/odirag"
    database_echo: bool = False
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    auto_create_schema: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    data_dir: Path = Path("../data")
    crawler_timeout_seconds: float = Field(default=20.0, gt=0, le=300)
    crawler_max_redirects: int = Field(default=5, ge=0, le=20)
    source_discovery_provider: Literal["brave", "disabled"] = "brave"
    source_discovery_search_url: str = "https://api.search.brave.com/res/v1/web/search"
    source_discovery_api_key: SecretStr | None = None
    source_discovery_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    source_discovery_max_candidates: int = Field(default=10, ge=1, le=100)
    source_discovery_max_columns: int = Field(default=12, ge=1, le=100)
    source_discovery_trial_max_documents: int = Field(default=5, ge=1, le=50)
    source_discovery_trial_min_chars: int = Field(default=160, ge=20, le=100_000)
    source_discovery_quality_threshold: float = Field(default=0.65, ge=0, le=1)
    # Periodic source-pool expansion is opt-in.  An empty topic list always makes
    # the scheduler a no-op, even when the task itself is enabled.
    source_discovery_auto_enabled: bool = False
    source_discovery_auto_topics: Annotated[list[str], NoDecode] = Field(
        default_factory=list, max_length=100
    )
    source_discovery_auto_interval_seconds: int = Field(
        default=3600,
        ge=300,
        le=7 * 24 * 3600,
        validation_alias=AliasChoices(
            "ODIRAG_SOURCE_DISCOVERY_AUTO_INTERVAL_SECONDS",
            "ODIRAG_SOURCE_DISCOVERY_AUTO_MIN_INTERVAL_SECONDS",
        ),
    )
    source_discovery_auto_region: str | None = Field(default=None, max_length=128)
    source_discovery_auto_organization_level: str | None = Field(default=None, max_length=64)
    source_discovery_auto_required_source_count: int = Field(default=1, ge=1, le=100)
    source_discovery_auto_required_document_count: int = Field(default=3, ge=0, le=10_000)
    source_discovery_official_suffixes: list[str] = Field(
        default_factory=lambda: [".gov.cn", ".gov", ".edu.cn"]
    )
    crawl_stale_after_seconds: int = Field(default=30 * 60, ge=60, le=24 * 3600)
    crawl_max_recovery_attempts: int = Field(default=3, ge=1, le=20)
    crawl_recovery_batch_size: int = Field(default=200, ge=1, le=10_000)
    celery_visibility_timeout_seconds: int = Field(default=60 * 60, ge=60, le=7 * 24 * 3600)
    celery_task_soft_time_limit_seconds: int = Field(default=25 * 60, ge=30, le=24 * 3600)
    celery_task_time_limit_seconds: int = Field(default=30 * 60, ge=60, le=24 * 3600)
    max_download_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    allowed_attachment_extensions: set[str] = Field(
        default_factory=lambda: {".pdf", ".docx", ".xlsx", ".txt", ".zip"}
    )

    llm_provider: Literal["direct", "coze"] = "direct"
    direct_llm_base_url: str = "https://api.openai.com/v1"
    direct_llm_api_key: SecretStr | None = None
    direct_llm_model: str = "gpt-4.1-mini"
    coze_base_url: str = Field(
        default="https://api.coze.com",
        validation_alias=AliasChoices("ODIRAG_COZE_BASE_URL", "COZE_BASE_URL"),
    )
    coze_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "COZE_API_TOKEN",
            "COZE_ACCESS_TOKEN",
            "ODIRAG_COZE_API_TOKEN",
            "ODIRAG_COZE_ACCESS_TOKEN",
        ),
    )
    coze_bot_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ODIRAG_COZE_BOT_ID", "COZE_BOT_ID"),
    )
    # Crawl workflow settings.  AliasChoices keeps the existing ODIRAG_ prefix while
    # accepting the deployment-oriented names used by the reference Coze project.
    coze_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("COZE_ENABLED", "ODIRAG_COZE_ENABLED"),
    )
    coze_legacy_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "COZE_LEGACY_API_URL",
            "COZE_API_URL",
            "ODIRAG_COZE_LEGACY_API_URL",
            "ODIRAG_COZE_API_URL",
        ),
    )
    coze_batch_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("COZE_BATCH_API_URL", "ODIRAG_COZE_BATCH_API_URL"),
    )
    coze_default_contract: Literal["legacy_single_article", "batch_crawl"] = Field(
        default="batch_crawl",
        validation_alias=AliasChoices("COZE_DEFAULT_CONTRACT", "ODIRAG_COZE_DEFAULT_CONTRACT"),
    )
    coze_timeout_seconds: float = Field(
        default=90.0,
        gt=0,
        le=600,
        validation_alias=AliasChoices("COZE_TIMEOUT_SECONDS", "ODIRAG_COZE_TIMEOUT_SECONDS"),
    )
    coze_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        validation_alias=AliasChoices("COZE_MAX_RETRIES", "ODIRAG_COZE_MAX_RETRIES"),
    )
    review_filter_config_path: Path = Path("../config/filters.yaml")
    review_prompt_path: Path = Path("../config/prompts/document_review_v1.txt")
    review_prompt_name: str = "document_review"
    review_prompt_version: str = "v1"
    answer_provider: Literal["extractive", "llm"] = "extractive"
    grounded_answer_prompt_path: Path = Path("../config/prompts/grounded_answer_v1.txt")
    grounded_answer_prompt_version: str = "v1"
    grounding_minimum_hits: int = Field(default=1, ge=1, le=20)
    grounding_minimum_score: float = Field(default=0.0, ge=0)
    grounding_require_official_source: bool = True
    grounding_refuse_on_conflict: bool = True
    evidence_sufficiency_minimum_confidence: float = Field(default=0.45, ge=0.45, le=1)
    evidence_sufficiency_minimum_hit_contribution: float = Field(default=0.08, ge=0.05, le=1)
    evidence_sufficiency_minimum_answer_overlap: float = Field(default=0.2, ge=0.2, le=1)

    chunking_config_path: Path = Path("../config/chunking.yaml")
    embedding_provider: Literal["remote", "deterministic"] = "remote"
    embedding_cache_provider: Literal["redis", "memory"] = "redis"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=4, le=65_536)
    embedding_batch_size: int = Field(default=32, ge=1, le=512)
    embedding_version: str = "v1"
    embedding_minimum_interval_seconds: float = Field(default=0.0, ge=0, le=60)
    embedding_cache_ttl_seconds: int = Field(default=30 * 24 * 3600, ge=60)
    embedding_cost_per_1k_chars: float = Field(default=0.0, ge=0)
    qdrant_collection: str = "odirag_chunks"
    vector_store_provider: Literal["qdrant", "memory"] = "qdrant"
    bm25_snapshot_path: Path = Path("../data/indexes/bm25.json")
    evaluation_artifact_dir: Path = Path("../data/evaluation/runs")
    experiment_artifact_dir: Path = Path("../data/experiments/runs")
    rerank_provider: Literal["remote", "none", "deterministic"] = "none"
    rerank_base_url: str = "https://api.cohere.com/v2"
    rerank_api_key: SecretStr | None = None
    rerank_model: str = "rerank-v3.5"
    retrieval_bm25_top_k: int = Field(default=20, ge=1, le=200)
    retrieval_vector_top_k: int = Field(default=20, ge=1, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    retrieval_rerank_top_k: int = Field(default=8, ge=1, le=100)
    retrieval_final_top_k: int = Field(default=5, ge=1, le=50)
    retrieval_score_threshold: float = Field(default=0.0, ge=0)

    alert_window_hours: int = Field(default=24, ge=1, le=24 * 30)
    alert_minimum_sample_size: int = Field(default=5, ge=1, le=10_000)
    alert_crawl_failure_rate: float = Field(default=0.2, ge=0, le=1)
    alert_index_failure_count: int = Field(default=1, ge=1)
    alert_chat_p95_ms: float = Field(default=5000, gt=0)
    alert_evaluation_regression_count: int = Field(default=1, ge=1)
    alert_average_cost: float = Field(default=1.0, ge=0)

    jwt_secret_key: SecretStr = SecretStr("change-me-in-production-with-at-least-32-characters")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90)
    admin_username: str = "admin"
    admin_password_hash: SecretStr | None = None
    admin_password: SecretStr | None = None
    bootstrap_admin: bool = True

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    health_check_qdrant: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "redis"
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_auth_requests: int = Field(default=20, ge=1, le=10_000)
    rate_limit_expensive_requests: int = Field(default=120, ge=1, le=100_000)
    rate_limit_default_requests: int = Field(default=600, ge=1, le=1_000_000)
    # Only these direct peers may supply a single X-Forwarded-For client address.
    # Leave empty when the ASGI server is exposed directly.
    trusted_proxy_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator(
        "qdrant_api_key",
        "source_discovery_api_key",
        "direct_llm_api_key",
        "coze_api_token",
        "embedding_api_key",
        "rerank_api_key",
        "admin_password_hash",
        "admin_password",
        mode="before",
    )
    @classmethod
    def normalize_optional_secret(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def parse_trusted_proxy_ips(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        raw_value = value.strip()
        if not raw_value:
            return []

        if raw_value.startswith("["):
            try:
                decoded = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "trusted_proxy_ips must be a valid JSON string array or a comma-separated list"
                ) from exc
            if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
                raise ValueError(
                    "trusted_proxy_ips must be a JSON string array or a comma-separated list"
                )
            return [item.strip() for item in decoded if item.strip()]

        return [item.strip() for item in raw_value.split(",") if item.strip()]

    @field_validator("source_discovery_auto_topics", mode="before")
    @classmethod
    def parse_source_discovery_auto_topics(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            if any(not isinstance(item, str) for item in value):
                raise ValueError("source_discovery_auto_topics must contain only strings")
            return list(value)
        if not isinstance(value, str):
            raise ValueError(
                "source_discovery_auto_topics must be a JSON string array or a comma-separated list"
            )

        raw_value = value.strip()
        if not raw_value:
            return []
        if raw_value.startswith("["):
            try:
                decoded = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "source_discovery_auto_topics must be a valid JSON string array "
                    "or a comma-separated list"
                ) from exc
            if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
                raise ValueError(
                    "source_discovery_auto_topics must be a JSON string array "
                    "or a comma-separated list"
                )
            return decoded
        if raw_value.startswith(("{", '"')):
            raise ValueError(
                "source_discovery_auto_topics must be a JSON string array or a comma-separated list"
            )
        return raw_value.split(",")

    @field_validator("source_discovery_auto_topics")
    @classmethod
    def normalize_source_discovery_auto_topics(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            topic = item.strip()
            if not topic:
                continue
            if len(topic) > 255:
                raise ValueError(
                    "source_discovery_auto_topics entries must be at most 255 characters"
                )
            dedupe_key = topic.casefold()
            if dedupe_key not in seen:
                normalized.append(topic)
                seen.add(dedupe_key)
        return normalized

    @field_validator("trusted_proxy_ips")
    @classmethod
    def validate_trusted_proxy_ips(cls, value: list[str]) -> list[str]:
        for item in value:
            try:
                ip_network(item, strict=False)
            except ValueError as exc:
                message = "trusted_proxy_ips contains an invalid IP address or CIDR"
                raise ValueError(message) from exc
        return value

    @model_validator(mode="after")
    def validate_security(self) -> Settings:
        if self.celery_task_soft_time_limit_seconds >= self.celery_task_time_limit_seconds:
            raise ValueError("celery soft time limit must be lower than the hard time limit")
        if self.environment in {"staging", "production"}:
            if len(self.jwt_secret_key.get_secret_value()) < 32:
                raise ValueError("jwt_secret_key must contain at least 32 characters")
            if self.jwt_secret_key.get_secret_value().startswith("change-me"):
                raise ValueError("jwt_secret_key must be changed outside development/test")
            if self.bootstrap_admin and self.admin_password_hash is None:
                raise ValueError("admin_password_hash is required when bootstrapping an admin")
            if self.debug:
                raise ValueError("debug must be disabled outside development/test")
            if self.admin_password is not None:
                raise ValueError("admin_password must not contain a plaintext production secret")
            if not self.rate_limit_enabled:
                raise ValueError("rate limiting must be enabled outside development/test")
            if self.rate_limit_backend != "redis":
                raise ValueError("rate_limit_backend must be redis outside development/test")
            if self.source_discovery_provider == "brave":
                search_endpoint = urlsplit(self.source_discovery_search_url)
                if (
                    search_endpoint.scheme != "https"
                    or search_endpoint.hostname != "api.search.brave.com"
                ):
                    raise ValueError(
                        "production Brave source discovery requires the official HTTPS endpoint"
                    )
            if self.source_discovery_auto_enabled and not self.source_discovery_auto_topics:
                raise ValueError(
                    "source_discovery_auto_topics is required when automatic discovery is enabled"
                )
            if self.source_discovery_auto_enabled and self.source_discovery_provider == "disabled":
                raise ValueError(
                    "automatic source discovery requires an enabled discovery provider"
                )
            demo_only_providers = {
                "embedding_provider": self.embedding_provider == "deterministic",
                "embedding_cache_provider": self.embedding_cache_provider == "memory",
                "vector_store_provider": self.vector_store_provider == "memory",
                "rerank_provider": self.rerank_provider == "deterministic",
            }
            enabled_demo_providers = [
                name for name, enabled in demo_only_providers.items() if enabled
            ]
            if enabled_demo_providers:
                raise ValueError(
                    "demo-only providers are restricted to development/test: "
                    + ", ".join(enabled_demo_providers)
                )
            insecure_origins = [
                origin
                for origin in self.cors_origins
                if origin == "*" or not origin.lower().startswith("https://")
            ]
            if insecure_origins:
                raise ValueError("cors_origins must contain explicit HTTPS origins")
        return self

    @property
    def json_logs_enabled(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.environment != "development"

    @property
    def sync_database_url(self) -> str:
        replacements = {
            "postgresql+asyncpg://": "postgresql+psycopg://",
            "sqlite+aiosqlite://": "sqlite+pysqlite://",
        }
        for async_driver, sync_driver in replacements.items():
            if self.database_url.startswith(async_driver):
                return self.database_url.replace(async_driver, sync_driver, 1)
        return self.database_url

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self._redis_url_with_database(1)

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self._redis_url_with_database(2)

    def _redis_url_with_database(self, database: int) -> str:
        base, separator, _current_database = self.redis_url.rpartition("/")
        if separator and base.startswith(("redis://", "rediss://")):
            return f"{base}/{database}"
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
