from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FilterDecision(StrEnum):
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


class RuleFilterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hard_minimum_chars: int = Field(default=40, ge=0)
    soft_minimum_chars: int = Field(default=180, ge=0)
    accept_score: float = Field(default=0.65, ge=0, le=1)
    reject_score: float = Field(default=0.25, ge=0, le=1)
    title_reject_patterns: list[str] = Field(default_factory=list)
    content_reject_patterns: list[str] = Field(default_factory=list)
    relevance_keywords: list[str] = Field(default_factory=list)
    short_content_penalty: float = Field(default=0.35, ge=0, le=1)
    missing_keyword_penalty: float = Field(default=0.25, ge=0, le=1)
    unofficial_source_penalty: float = Field(default=0.1, ge=0, le=1)


@dataclass(frozen=True, slots=True)
class FilterResult:
    decision: FilterDecision
    score: float
    reasons: tuple[str, ...]


class RuleFilter:
    def __init__(self, config: RuleFilterConfig) -> None:
        self.config = config
        self._title_reject = [re.compile(pattern, re.I) for pattern in config.title_reject_patterns]
        self._content_reject = [
            re.compile(pattern, re.I) for pattern in config.content_reject_patterns
        ]

    def evaluate(self, *, title: str, content: str, official_source: bool) -> FilterResult:
        reasons: list[str] = []
        if len(content.strip()) < self.config.hard_minimum_chars:
            return FilterResult(FilterDecision.REJECT, 0.0, ("content_too_short_hard",))
        if any(pattern.search(title) for pattern in self._title_reject):
            return FilterResult(FilterDecision.REJECT, 0.0, ("title_reject_pattern",))
        if any(pattern.search(content) for pattern in self._content_reject):
            return FilterResult(FilterDecision.REJECT, 0.0, ("content_reject_pattern",))
        score = 1.0
        if len(content.strip()) < self.config.soft_minimum_chars:
            score -= self.config.short_content_penalty
            reasons.append("content_too_short_soft")
        if self.config.relevance_keywords and not any(
            keyword.lower() in f"{title}\n{content}".lower()
            for keyword in self.config.relevance_keywords
        ):
            score -= self.config.missing_keyword_penalty
            reasons.append("relevance_keyword_missing")
        if not official_source:
            score -= self.config.unofficial_source_penalty
            reasons.append("source_not_official")
        score = round(max(0.0, min(1.0, score)), 4)
        if score <= self.config.reject_score:
            decision = FilterDecision.REJECT
        elif score < self.config.accept_score:
            decision = FilterDecision.REVIEW
        else:
            decision = FilterDecision.ACCEPT
        return FilterResult(decision, score, tuple(reasons))
