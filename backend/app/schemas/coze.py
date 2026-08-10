from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)


class CozeStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BatchCrawlRequest(CozeStrictModel):
    task_id: str = Field(min_length=1, strict=True)
    source_url: HttpUrl
    source_name: str | None = None
    region: str | None = None
    column_name: str | None = None
    max_articles: int = Field(default=5, ge=1, le=100)
    max_pages: int = Field(default=1, ge=1, le=100)
    minimum_content_length: int = Field(default=3000, ge=0, le=1_000_000)
    start_date: date | None = None
    end_date: date | None = None
    include_html: bool = True
    include_pdf: bool = True
    include_docx: bool = True
    include_xlsx: bool = True
    deduplicate: bool = True
    crawl_rules: dict[str, Any] = Field(default_factory=dict)
    quality_rules: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_date_range(self) -> BatchCrawlRequest:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class BatchSource(CozeStrictModel):
    source_url: HttpUrl = Field(validation_alias=AliasChoices("source_url", "url"))
    source_name: str | None = Field(
        default=None, validation_alias=AliasChoices("source_name", "name")
    )
    organization: str | None = None
    region: str | None = None
    column_name: str | None = None


class BatchStatistics(CozeStrictModel):
    pages_visited: int = Field(ge=0)
    articles_discovered: int = Field(ge=0)
    articles_fetched: int = Field(ge=0)
    articles_accepted: int = Field(ge=0)
    articles_rejected: int = Field(ge=0)
    articles_pending_review: int = Field(ge=0)
    articles_failed: int = Field(ge=0)


class BatchAttachment(CozeStrictModel):
    name: str
    url: HttpUrl
    file_type: str | None = None
    extracted_text: str | None = None
    download_status: Literal[
        "pending",
        "success",
        "completed",
        "failed",
        "too_large",
        "unsupported",
        "skipped",
    ] = "pending"
    error_message: str | None = None


class BatchArticle(CozeStrictModel):
    title: str
    url: HttpUrl
    published_at: datetime | date | None = None
    organization: str | None = None
    organization_inferred: bool = False
    region: str | None = None
    column_name: str | None = None
    content: str
    content_length: int = Field(ge=0)
    attachments: list[BatchAttachment] = Field(default_factory=list)
    extraction_method: Literal[
        "html", "pdf", "doc", "docx", "xls", "xlsx", "image", "image_ocr", "mixed"
    ]
    needs_ocr: bool = False
    image_urls: list[HttpUrl] = Field(default_factory=list)
    image_count: int = Field(default=0, ge=0)
    image_alt_texts: list[str] = Field(default_factory=list)
    decision: Literal["accepted", "rejected", "pending_review", "failed"]
    accepted: bool
    quality_score: float | None = Field(default=None, ge=0, le=100)
    decision_reason: str
    document_type: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_consistency(self) -> BatchArticle:
        if self.content_length != len(self.content):
            raise ValueError("content_length must equal the Unicode character length of content")
        if self.accepted != (self.decision == "accepted"):
            raise ValueError("accepted must be true exactly when decision is accepted")
        if self.extraction_method == "image" and not self.needs_ocr:
            raise ValueError("image extraction must set needs_ocr=true")
        if self.extraction_method == "image_ocr" and self.needs_ocr:
            raise ValueError("completed image OCR must set needs_ocr=false")
        if self.image_count != len(self.image_urls):
            raise ValueError("image_count must equal image_urls length")
        return self


class BatchFailedUrl(CozeStrictModel):
    url: HttpUrl
    stage: str
    error_code: str
    error_message: str
    retryable: bool = False


class BatchCrawlResponse(CozeStrictModel):
    success: bool
    task_id: str = Field(min_length=1, strict=True)
    source: BatchSource
    statistics: BatchStatistics
    articles: list[BatchArticle]
    failed_urls: list[BatchFailedUrl]
    warnings: list[str]
    contract_version: str | None = None
    workflow_version: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    completed_at: datetime | None = None
    diagnostics: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_statistics(self) -> BatchCrawlResponse:
        decisions = {name: 0 for name in ("accepted", "rejected", "pending_review", "failed")}
        for article in self.articles:
            decisions[article.decision] += 1
        expected = {
            "accepted": self.statistics.articles_accepted,
            "rejected": self.statistics.articles_rejected,
            "pending_review": self.statistics.articles_pending_review,
            "failed": self.statistics.articles_failed,
        }
        if decisions["accepted"] != expected["accepted"]:
            raise ValueError("accepted article count does not match statistics")
        if decisions["rejected"] != expected["rejected"]:
            raise ValueError("rejected article count does not match statistics")
        if decisions["pending_review"] != expected["pending_review"]:
            raise ValueError("pending_review article count does not match statistics")
        if decisions["failed"] + len(self.failed_urls) != expected["failed"]:
            raise ValueError("article decision counts do not match statistics")
        if self.statistics.articles_fetched != len(self.articles):
            raise ValueError("articles_fetched must equal articles length")
        return self


def parse_batch_crawl_response(payload: Any) -> tuple[BatchCrawlResponse, Any]:
    """Parse a direct JSON object or a Coze string-wrapped JSON result."""

    raw = payload
    candidate = payload
    for _ in range(3):
        if isinstance(candidate, str):
            candidate = _decode_json_string(candidate)
            continue
        if isinstance(candidate, dict):
            for key in ("data", "output", "result", "batch_result"):
                nested = candidate.get(key)
                if isinstance(nested, (str, dict)):
                    candidate = nested
                    break
            else:
                break
            continue
        break
    # Keep the provider response byte-for-byte available to the audit trail, but
    # canonicalize relative resource URLs in a validation copy.  Coze workflows
    # commonly emit ``/upload/image.png`` while the strict contract intentionally
    # requires absolute HTTP URLs.  This is a transport normalization, not a
    # schema relaxation: malformed URLs still fail Pydantic validation.
    candidate = _canonicalize_batch_urls(candidate)
    return BatchCrawlResponse.model_validate(candidate), raw


_JSON_FENCE = re.compile(r"^```(?:json)?[ \t]*\r?\n(?P<body>.*)\r?\n```$", re.DOTALL)


def _decode_json_string(value: str) -> Any:
    """Decode only a complete JSON string or a complete historical JSON fence.

    Coze deployments have returned fenced JSON in the past.  Accepting a whole
    fenced block is deterministic; stripping arbitrary prefixes/suffixes would
    risk turning an invalid provider response into a false success.
    """

    text = value.strip()
    match = _JSON_FENCE.fullmatch(text)
    if match:
        text = match.group("body").strip()
    return json.loads(text)


def _canonicalize_batch_urls(candidate: Any) -> Any:
    if not isinstance(candidate, dict):
        return candidate
    normalized = deepcopy(candidate)
    articles = normalized.get("articles")
    if not isinstance(articles, list):
        return normalized
    for article in articles:
        if not isinstance(article, dict):
            continue
        article_url = article.get("url")
        if not isinstance(article_url, str) or not article_url.strip():
            continue
        article_url = _try_normalize(article_url)
        if article_url is None:
            continue
        article["url"] = article_url
        image_urls = article.get("image_urls")
        if isinstance(image_urls, list):
            article["image_urls"] = [
                (
                    normalized_url
                    if (normalized_url := _try_normalize(str(value), base_url=article_url))
                    is not None
                    else value
                )
                for value in image_urls
            ]
        attachments = article.get("attachments")
        if isinstance(attachments, list):
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                value = attachment.get("url")
                if isinstance(value, str):
                    normalized_url = _try_normalize(value, base_url=article_url)
                    if normalized_url is not None:
                        attachment["url"] = normalized_url
    return normalized


def _try_normalize(value: str, *, base_url: str | None = None) -> str | None:
    try:
        parsed = urlsplit(urljoin(base_url, value) if base_url else value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = parsed.hostname.lower().rstrip(".")
        port = parsed.port
        default_port = (parsed.scheme.lower() == "http" and port == 80) or (
            parsed.scheme.lower() == "https" and port == 443
        )
        authority = host if port is None or default_port else f"{host}:{port}"
        path = parsed.path or "/"
        while "//" in path:
            path = path.replace("//", "/")
        query = urlencode(
            sorted(
                (key, item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                if not key.lower().startswith("utm_")
                and key.lower() not in {"spm", "from", "source"}
            )
        )
        return urlunsplit((parsed.scheme.lower(), authority, path, query, ""))
    except (TypeError, ValueError):
        return None


# Stable aliases for callers that use the provider-oriented terminology.
CozeBatchCrawlRequest = BatchCrawlRequest
CozeBatchCrawlResponse = BatchCrawlResponse
