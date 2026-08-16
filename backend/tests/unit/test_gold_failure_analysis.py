from __future__ import annotations

from app.evaluation.failure_analysis import build_failure_analysis


def _evaluation_case(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "question_id": "q1",
        "question": "根据《通知》，有什么安排？",
        "category": "explicit_fact",
        "should_refuse": False,
        "refused": True,
        "answer": "无法回答",
        "expected_document_ids": ["d1"],
        "expected_chunk_ids": ["c1"],
        "retrieved_chunk_ids": ["c1"],
        "cited_chunk_ids": [],
        "cited_document_ids": [],
        "metrics": {
            "chunk_hit": 1.0,
            "refusal_correct": 0.0,
            "citation_accuracy": 0.0,
            "citation_completeness": 0.0,
            "answer_point_coverage": 0.0,
        },
        "retrieval_trace": {"trace_id": "t1"},
        "chat_metadata": {"refusal_reasons": ["evidence_missing_required_relation"]},
        "error": None,
    }
    case.update(overrides)
    return case


def _analysis(case: dict[str, object], evidence: dict[str, object]) -> dict[str, object]:
    return build_failure_analysis(
        {"questions": [case]},
        {"questions": [{"question_id": "q1", "expected_answer": "安排"}]},
        {
            "t1": {
                "fusion_results": [{"chunk_id": "c1"}],
                "rerank_results": [{"chunk_id": "c1"}],
                "final_context": [{"chunk_id": "c1"}],
                "rerank_metadata": {"applied": True},
                "evidence_decision": evidence,
            }
        },
        {},
    )


def test_supported_evidence_rejection_is_classified_as_false_negative() -> None:
    analysis = _analysis(
        _evaluation_case(),
        {
            "sufficient": False,
            "reason": "evidence_missing_required_relation",
            "supported_chunk_ids": [],
        },
    )

    case = analysis["cases"][0]
    assert case["root_cause_category"] == "EVIDENCE_GATE_FALSE_NEGATIVE"
    assert case["retrieval_hit"] is True
    assert case["expected_evidence_in_context"] is False
    assert analysis["refusal_confusion_matrix"]["supported_answer_recall"] == 0.0


def test_same_document_citation_mismatch_is_not_called_wrong_evidence() -> None:
    analysis = _analysis(
        _evaluation_case(
            refused=False,
            answer="有明确安排",
            cited_chunk_ids=["c2"],
            cited_document_ids=["d1"],
            chat_metadata={"refusal_reasons": []},
            metrics={
                "chunk_hit": 1.0,
                "refusal_correct": 1.0,
                "citation_accuracy": 0.0,
                "citation_completeness": 0.0,
                "answer_point_coverage": 0.0,
            },
        ),
        {
            "sufficient": True,
            "reason": "evidence_covers_all_query_aspects",
            "supported_chunk_ids": ["c2"],
            "answer_support_validated": True,
        },
    )

    case = analysis["cases"][0]
    assert case["root_cause_category"] == "CITATION_EXPECTATION_MISMATCH"
    assert analysis["refusal_confusion_matrix"]["supported_answer_recall"] == 1.0


def test_post_answer_validation_decision_is_exposed_without_inference() -> None:
    analysis = _analysis(
        _evaluation_case(
            chat_metadata={"refusal_reasons": ["answer_contains_unsupported_relation"]}
        ),
        {
            "sufficient": True,
            "reason": "evidence_covers_all_query_aspects",
            "supported_chunk_ids": ["c1"],
            "answer_support_validated": False,
            "answer_validation_decision": {
                "sufficient": False,
                "confidence": 0.0,
                "reason": "answer_contains_unsupported_relation",
                "supported_chunk_ids": [],
                "unsupported_aspects": ["legal_basis"],
            },
        },
    )

    case = analysis["cases"][0]
    assert case["answer_validation_result"]["unsupported_aspects"] == ["legal_basis"]
    assert case["relation_validation_result"] == {
        "stage": "post_answer_validation",
        "status": "rejected",
        "reason": "answer_contains_unsupported_relation",
        "confidence": 0.0,
        "unsupported_aspects": ["legal_basis"],
    }


def test_correct_refusal_is_separated_from_supported_failures() -> None:
    analysis = _analysis(
        _evaluation_case(
            should_refuse=True,
            metrics={
                "chunk_hit": 1.0,
                "refusal_correct": 1.0,
                "citation_accuracy": 0.0,
                "citation_completeness": 0.0,
                "answer_point_coverage": 0.0,
            },
        ),
        {"sufficient": False, "reason": "insufficient_evidence_relevance"},
    )

    case = analysis["cases"][0]
    assert case["root_cause_category"] == "CORRECT_REFUSAL"
    assert analysis["refusal_confusion_matrix"]["refusal_recall"] == 1.0
