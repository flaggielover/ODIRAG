from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class SourceColumnCreate(BaseModel):
    column_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    column_name: str = Field(min_length=1, max_length=255)
    column_url: HttpUrl
    parser_type: str = Field(default="html", min_length=1, max_length=64)
    enabled: bool = True
    max_pages: int = Field(default=100, ge=1, le=10_000)
    request_interval_seconds: int = Field(default=1, ge=0, le=3600)
    selectors_json: dict[str, Any] = Field(default_factory=dict)
    pagination_json: dict[str, Any] = Field(default_factory=dict)


class SourceCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=128)
    city: str | None = Field(default=None, max_length=128)
    organization_level: str | None = Field(default=None, max_length=64)
    organization_type: str | None = Field(default=None, max_length=64)
    official_status: str = Field(default="official", min_length=1, max_length=32)
    homepage_url: HttpUrl
    enabled: bool = True
    priority: int = Field(default=0, ge=0, le=10_000)
    crawl_frequency: str = Field(default="daily", min_length=1, max_length=64)
    crawl_provider: Literal["coze", "local"] = "coze"
    coze_contract_mode: Literal["legacy_single_article", "batch_crawl"] = "batch_crawl"
    columns: list[SourceColumnCreate] = Field(default_factory=list)

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return value.strip().lower().rstrip(".")


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    domain: str | None = Field(default=None, min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=128)
    city: str | None = Field(default=None, max_length=128)
    organization_level: str | None = Field(default=None, max_length=64)
    organization_type: str | None = Field(default=None, max_length=64)
    official_status: str | None = Field(default=None, min_length=1, max_length=32)
    homepage_url: HttpUrl | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    crawl_frequency: str | None = Field(default=None, min_length=1, max_length=64)
    crawl_provider: Literal["coze", "local"] | None = None
    coze_contract_mode: Literal["legacy_single_article", "batch_crawl"] | None = None


class SourceColumnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    column_key: str
    column_name: str
    column_url: str
    parser_type: str
    enabled: bool
    max_pages: int
    request_interval_seconds: int
    selectors_json: dict[str, Any]
    pagination_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_key: str
    name: str
    domain: str
    region: str | None
    city: str | None
    organization_level: str | None
    organization_type: str | None
    official_status: str
    homepage_url: str
    enabled: bool
    priority: int
    crawl_frequency: str
    last_crawl_time: datetime | None
    crawl_provider: str
    last_coze_status: str | None
    last_coze_article_count: int | None
    last_coze_error: str | None
    coze_contract_mode: str
    last_coze_test_at: datetime | None
    last_successful_crawl_at: datetime | None
    created_at: datetime
    updated_at: datetime
    columns: list[SourceColumnResponse] = Field(default_factory=list)


class SourceTestResponse(BaseModel):
    reachable: bool
    status_code: int | None = None
    latency_ms: float
    final_url: str | None = None
    error_type: str | None = None


class CozeConnectionResponse(BaseModel):
    available: bool
    reachable: bool
    contract: Literal["legacy_single_article", "batch_crawl"]
    status_code: int | None = None
    latency_ms: int
    error_code: str | None = None
    final_url: str | None = None
    error_type: str | None = None
    provider: Literal["coze"] = "coze"
    status: str
    message: str | None = None
    checked_at: datetime
