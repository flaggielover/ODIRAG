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

    _corpus_count_intent = re.compile(
        r"(?:有|共有|共|发布了?|收录|检索到)?\s*(?:多少|几)\s*(?:份|篇|条|个|项)?\s*"
        r"(?:政策|文件|文档|通知|文章|资料|材料|记录|来源|站点)"
        r"|(?:政策|文件|文档|通知|文章|资料|材料|记录|来源|站点)\s*"
        r"(?:共有|有)?\s*(?:多少|几)\s*(?:份|篇|个)?(?=\s*[?？。!！]*$)"
        r"|(?:政策|文件|文档|通知|文章|资料|材料|记录|来源|站点)\s*"
        r"(?:总数|数量|统计)"
        r"|(?:count|how many|total)\s+(?:polic(?:y|ies)|documents?|articles?|records?|sources?)",
        re.I,
    )
    _fact_value_terms = re.compile(
        r"(金额|罚款|比例|百分比|占比|日期|时间|期限|额度|标准|价格|费用|利率|"
        r"补助|资助|奖励|amount|percent(?:age)?|date|time|deadline|price|fee|rate)",
        re.I,
    )
    _semantic_terms = re.compile(
        r"(总结|概括|共同|措施|要求|原因|影响|summari[sz]e|common|explain)", re.I
    )

    def __init__(self, analyzer: RetrievalQueryAnalyzer | None = None) -> None:
        self.analyzer = analyzer or RetrievalQueryAnalyzer()

    def analyze(self, query: str, explicit_filters: dict[str, Any] | None = None) -> QueryAnalysis:
        text = query.strip()
        if not text:
            raise ValueError("query must not be empty")
        aggregate = bool(
            self._corpus_count_intent.search(text) and not self._fact_value_terms.search(text)
        )
        semantic = bool(self._semantic_terms.search(text))
        filters = self.analyzer.analyze(text, explicit_filters).applied_filters
        if aggregate and not semantic:
            return QueryAnalysis(QueryType.SQL, filters, "aggregate query with structured filters")
        if semantic and (filters or aggregate):
            return QueryAnalysis(
                QueryType.COMPOSITE, filters, "semantic answer over a structured subset"
            )
        return QueryAnalysis(QueryType.RAG, filters, "content-oriented question")
