from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.retrieval import RetrievalQueryAnalyzer


class QueryType(StrEnum):
    SQL = "sql"
    RAG = "rag"
    COMPOSITE = "sql+rag"


@dataclass(frozen=True, slots=True)
class QueryAnalysis:
    query_type: QueryType
    filters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class QueryRouter:
    """Deterministic baseline router; no generated SQL is accepted or executed."""

    _aggregate_terms = re.compile(r"(多少|几份|数量|统计|count|how many|total)", re.I)
    _semantic_terms = re.compile(
        r"(总结|概括|共同|措施|要求|原因|影响|summari[sz]e|common|explain)", re.I
    )

    def __init__(self, analyzer: RetrievalQueryAnalyzer | None = None) -> None:
        self.analyzer = analyzer or RetrievalQueryAnalyzer()

    def analyze(self, query: str, explicit_filters: dict[str, Any] | None = None) -> QueryAnalysis:
        text = query.strip()
        if not text:
            raise ValueError("query must not be empty")
        aggregate = bool(self._aggregate_terms.search(text))
        semantic = bool(self._semantic_terms.search(text))
        filters = self.analyzer.analyze(text, explicit_filters).applied_filters
        if aggregate and not semantic:
            return QueryAnalysis(QueryType.SQL, filters, "aggregate query with structured filters")
        if semantic and (filters or aggregate):
            return QueryAnalysis(
                QueryType.COMPOSITE, filters, "semantic answer over a structured subset"
            )
        return QueryAnalysis(QueryType.RAG, filters, "content-oriented question")
