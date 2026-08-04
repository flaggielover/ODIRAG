from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievalQueryAnalysis:
    original_query: str
    normalized_query: str
    terms: tuple[str, ...]
    inferred_filters: dict[str, Any] = field(default_factory=dict)
    applied_filters: dict[str, Any] = field(default_factory=dict)


class RetrievalQueryAnalyzer:
    _after_year = re.compile(
        r"(?:(?:after|since|晚于)\s*(20\d{2})|(20\d{2})\s*(?:之后|以来|以后))",
        re.I,
    )
    _before_year = re.compile(
        r"(?:(?:before|截至|早于)\s*(20\d{2})|(20\d{2})\s*(?:之前|以前))",
        re.I,
    )
    _regions = (
        ("四川", "四川"),
        ("北京", "北京"),
        ("上海", "上海"),
        ("广东", "广东"),
        ("浙江", "浙江"),
        ("江苏", "江苏"),
        ("sichuan", "四川"),
        ("beijing", "北京"),
        ("shanghai", "上海"),
    )

    def analyze(
        self, query: str, explicit_filters: dict[str, Any] | None = None
    ) -> RetrievalQueryAnalysis:
        normalized = re.sub(r"\s+", " ", query).strip()
        if not normalized:
            raise ValueError("query must not be empty")
        inferred = self._infer_filters(normalized)
        supplied = explicit_filters or {}
        unknown = set(supplied) - _ALLOWED_FILTERS
        if unknown:
            raise ValueError(f"unsupported metadata filters: {sorted(unknown)}")
        applied = {**inferred, **supplied}
        terms = tuple(dict.fromkeys(_terms(normalized)))
        return RetrievalQueryAnalysis(query, normalized, terms, inferred, applied)

    def _infer_filters(self, query: str) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if match := self._after_year.search(query):
            year = next(group for group in match.groups() if group is not None)
            filters["publish_date_gte"] = date(int(year) + 1, 1, 1).isoformat()
        if match := self._before_year.search(query):
            year = next(group for group in match.groups() if group is not None)
            filters["publish_date_lte"] = date(int(year) - 1, 12, 31).isoformat()
        lowered = query.lower()
        for alias, canonical in self._regions:
            if alias in lowered:
                filters["region"] = canonical
                break
        return filters


def _terms(text: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text)]


_ALLOWED_FILTERS = {
    "document_id",
    "source_id",
    "region",
    "city",
    "document_type",
    "issuing_authority",
    "publish_date_gte",
    "publish_date_lte",
    "document_version",
}
