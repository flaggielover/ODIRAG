from __future__ import annotations

import pytest

from app.chunking import ChunkingConfig, HeadingAwareChunker
from app.evaluation import EvaluationSample, evaluate_samples
from app.experiments import compare_metrics
from app.rag import GroundingService
from app.retrieval import RetrievalHit, reciprocal_rank_fusion
from app.router import QueryRouter, QueryType


def _hit(
    chunk_id: str, score: float, source: str, content: str = "四川软件政策支持资金"
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id,
        f"doc-{chunk_id}",
        content,
        "政策",
        "https://example.gov/policy",
        score,
        source=source,
        metadata={
            "official_status": "official",
            "source_name": "示例政府",
            "publish_date": "2026-01-01",
        },
    )


def test_heading_chunker_preserves_heading_and_bounds() -> None:
    chunker = HeadingAwareChunker(
        ChunkingConfig(target_chars=30, min_chars=10, max_chars=45, overlap_chars=5)
    )
    chunks = chunker.chunk("# 申报条件\n\n" + "符合条件的企业可以申请。" * 10)
    assert len(chunks) > 1
    assert chunks[0].section_title == "申报条件"
    assert all(chunk.char_count <= 45 for chunk in chunks)


def test_rrf_fuses_and_deduplicates_rankings() -> None:
    fused = reciprocal_rank_fusion(
        [
            [_hit("a", 1, "bm25"), _hit("b", 0.5, "bm25")],
            [_hit("b", 1, "vector"), _hit("a", 0.5, "vector")],
        ],
        rrf_k=10,
    )
    assert [hit.chunk_id for hit in fused] == ["a", "b"]
    assert all(hit.source == "bm25+vector" for hit in fused)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("四川 2025 之后发布了多少政策？", QueryType.SQL),
        ("这些政策有哪些共同支持措施？", QueryType.RAG),
        ("总结四川 2025 之后政策的申报要求", QueryType.COMPOSITE),
    ],
)
def test_query_router(query: str, expected: QueryType) -> None:
    assert QueryRouter().analyze(query).query_type is expected


def test_grounding_binds_stored_identity_and_refuses_uncovered_question() -> None:
    service = GroundingService(minimum_hits=1, minimum_score=0.1)
    decision = service.assess("四川政策资金", [_hit("a", 0.8, "hybrid")])
    assert decision.sufficient
    assert decision.citations[0].url == "https://example.gov/policy"
    refused = service.assess("天气", [_hit("a", 0.8, "hybrid")])
    assert not refused.sufficient
    assert "question_not_covered" in refused.reasons


def test_grounding_detects_conflicts_and_drops_outdated_policy() -> None:
    service = GroundingService(minimum_hits=1, refuse_on_conflict=True)
    older = _hit("old", 0.8, "hybrid")
    newer = _hit("new", 0.9, "hybrid")
    older.metadata.update(
        {
            "document_number": "川政发〔2026〕1号",
            "publish_date": "2026-01-01",
            "policy_status": "active",
        }
    )
    newer.metadata.update(
        {
            "document_number": "川政发〔2026〕1号",
            "publish_date": "2026-03-01",
            "policy_status": "repealed",
        }
    )
    decision = service.assess("四川软件政策", [older, newer])
    assert not decision.sufficient
    assert "conflicting_evidence" in decision.reasons
    assert decision.conflicts
    assert decision.outdated
    assert [citation.chunk_id for citation in decision.citations] == ["new"]


def test_grounding_requires_an_official_source() -> None:
    hit = _hit("unverified", 0.9, "hybrid")
    hit.metadata["official_status"] = "unverified"
    decision = GroundingService().assess("四川软件政策", [hit])
    assert not decision.sufficient
    assert "official_source_required" in decision.reasons


def test_evaluation_metrics_are_calculated_from_samples() -> None:
    aggregate = evaluate_samples(
        [
            EvaluationSample(
                retrieved_ids=("a", "b"),
                relevant_ids=frozenset({"b"}),
                expected_answer_points=frozenset({"x", "y"}),
                covered_answer_points=frozenset({"x"}),
                expected_citation_ids=frozenset({"b"}),
                cited_ids=frozenset({"b"}),
                latency_ms=120,
                token_count=20,
            )
        ]
    )
    assert aggregate.recall_at_1 == 0
    assert aggregate.recall_at_5 == 1
    assert aggregate.mrr == 0.5
    assert aggregate.answer_point_coverage == 0.5


def test_experiment_comparison_flags_regressions() -> None:
    result = compare_metrics({"recall": 0.8, "latency": 100}, {"recall": 0.7, "latency": 120})
    assert {item.name for item in result if item.regression} == {"recall", "latency"}
