from __future__ import annotations

import pytest

from app.rag import EvidenceSufficiencyGate
from app.retrieval import RetrievalHit


def _hit(chunk_id: str, content: str, *, title: str = "政策通知") -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        content=content,
        title=title,
        source_url=f"https://example.gov.cn/{chunk_id}",
        score=0.01,
        rank=1,
        source="bm25+vector",
        metadata={
            "official_status": "official",
            "source_name": "示例政府部门",
            "publish_date": "2026-01-01",
            "region": "四川省",
        },
    )


def test_a_unrelated_question_is_insufficient() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "火星地表是否已经发现活体恐龙？",
        [_hit("policy", "软件企业可以申请研发资金补助。")],
    )

    assert not decision.sufficient
    assert decision.reason == "insufficient_evidence_relevance"
    assert decision.supported_chunk_ids == ()


def test_b_same_topic_without_requested_fact_is_insufficient() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "软件企业申请研发补助的联系人电话是多少？",
        [_hit("policy", "软件企业研发投入可以申请资金补助。")],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_missing_required_answer_shape"


def test_c_partial_support_for_multi_part_question_is_insufficient() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "软件企业研发补助比例是多少？申报截止日期是什么时间？",
        [_hit("ratio", "软件企业研发补助比例为30%。")],
    )

    assert not decision.sufficient
    assert decision.unsupported_aspects == ("申报截止日期是什么时间",)
    assert decision.supported_chunk_ids == ()


def test_d_same_name_different_entity_is_insufficient() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "苹果公司在四川发布了哪些人工智能政策？",
        [_hit("fruit", "四川苹果种植技术政策支持果园病虫害防治。")],
    )

    assert not decision.sufficient


def test_e_explicit_time_range_mismatch_is_insufficient() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "2025年软件企业补助申报时间是什么？",
        [
            _hit(
                "old",
                "2024年软件企业补助申报时间为3月1日至3月31日。",
            )
        ],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_constraint_mismatch"


def test_filter_boundary_year_does_not_need_to_appear_in_document_text() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "四川2025年之后的软件企业有哪些支持措施？",
        [
            _hit(
                "newer",
                "软件企业研发投入可以申请资金补助。",
            )
        ],
    )

    assert decision.sufficient


def test_f_exact_numeric_evidence_is_required() -> None:
    gate = EvidenceSufficiencyGate()
    supported = gate.assess(
        "软件企业研发补助比例是多少？",
        [_hit("ratio", "软件企业研发补助比例为30%，最高不超过100万元。")],
    )
    unsupported = gate.assess(
        "软件企业研发补助比例是多少？",
        [_hit("generic", "软件企业可以申请研发补助，具体标准另行通知。")],
    )

    assert supported.sufficient
    assert supported.supported_chunk_ids == ("ratio",)
    assert not unsupported.sufficient
    assert unsupported.reason == "evidence_missing_required_answer_shape"


def test_g_one_document_can_cover_the_complete_question() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "软件企业有哪些研发支持措施？",
        [_hit("support", "软件企业研发投入可以申请资金补助。")],
    )

    assert decision.sufficient
    assert decision.unsupported_aspects == ()
    assert decision.supported_chunk_ids == ("support",)


def test_h_multiple_chunks_can_jointly_cover_all_aspects() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "软件企业补助申报时间是什么？申请条件是什么？",
        [
            _hit("time", "软件企业补助申报时间为2026年5月1日至5月31日。"),
            _hit("condition", "申请条件为在四川省依法登记且持续经营的软件企业。"),
        ],
    )

    assert decision.sufficient
    assert decision.supported_chunk_ids == ("time", "condition")


@pytest.mark.parametrize(
    "query",
    [
        "为什么取消APP备案？",
        "请说明APP备案罚款金额的具体规定。",
        "APP备案是否适用于微信小程序？",
    ],
)
def test_semantically_related_but_uncovered_relation_or_scope_is_insufficient(
    query: str,
) -> None:
    decision = EvidenceSufficiencyGate().assess(
        query,
        [
            _hit(
                "miit",
                "现发布开展移动互联网应用程序备案工作的通知，存量APP备案阶段为2023年9月至2024年3月。",
            )
        ],
    )

    assert not decision.sufficient
    assert decision.supported_chunk_ids == ()


def test_relation_anchor_must_be_bound_to_the_requested_entity() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "为什么取消APP备案？",
        [
            _hit(
                "unrelated-action",
                "APP主办者应当立即停止传输违法信息，采取消除等处置措施。",
            )
        ],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_missing_required_relation"


@pytest.mark.parametrize(
    "content",
    [
        "APP备案主办者发现违法信息后，应立即停止传输。",
        "工业和信息化部取消其他事项，同时继续开展移动互联网应用程序备案。",
    ],
)
def test_cancellation_relation_cannot_cross_action_or_clause(content: str) -> None:
    decision = EvidenceSufficiencyGate().assess(
        "工业和信息化部为什么取消APP备案？",
        [_hit("unrelated-cancellation", content)],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_missing_required_relation"


def test_long_entity_remains_bound_to_cancellation_relation() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "为什么取消移动互联网应用程序备案？",
        [
            _hit(
                "long-entity",
                "本通知取消其他申报事项，同时继续开展移动互联网应用程序备案。",
            )
        ],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_missing_required_relation"


def test_negative_scope_statement_is_answerable_but_polarity_is_enforced() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("scope", "微信小程序不在本通知适用范围内。")
    query = "APP备案是否适用于微信小程序？"

    assert gate.assess(query, [hit]).sufficient
    supported = gate.validate_answer(
        query=query,
        answer="本通知不适用于微信小程序。",
        cited_hits=[hit],
    )
    contradicted = gate.validate_answer(
        query=query,
        answer="本通知适用于微信小程序。",
        cited_hits=[hit],
    )

    assert supported.sufficient
    assert not contradicted.sufficient
    assert contradicted.reason == "answer_contains_unsupported_scope_polarity"


def test_answer_validation_rejects_unsupported_status_relation() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "miit",
        "现发布开展移动互联网应用程序备案工作的通知，存量APP备案阶段为2023年9月至2024年3月。",
    )

    decision = gate.validate_answer(
        query="存量APP备案阶段是什么时间？",
        answer="APP备案已永久取消。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_relation"


def test_answer_validation_rejects_contradictory_cancellation_claim() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "miit",
        "工业和信息化部要求开展移动互联网应用程序备案，存量APP备案阶段为2023年9月至2024年3月。",
    )

    decision = gate.validate_answer(
        query="工业和信息化部为什么取消APP备案？",
        answer="工业和信息化部已经取消APP备案，因为制度违反法律。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "citations_do_not_cover_query"


@pytest.mark.parametrize(
    "unsupported_suffix",
    [
        "该制度已被废除。",
        "该通知涵盖所有微信小程序。",
        "所有小程序必须备案。",
        "月球上发现了恐龙。",
        "该制度现已退出历史舞台。",
        "微信小程序也在其内。",
        "现已作废。",
    ],
)
def test_answer_validation_rejects_supported_fact_plus_unsupported_claim(
    unsupported_suffix: str,
) -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("miit", "存量APP备案阶段为2023年9月至2024年3月。")

    decision = gate.validate_answer(
        query="存量APP备案阶段是什么时间？",
        answer=f"存量APP备案阶段为2023年9月至2024年3月。{unsupported_suffix}",
        cited_hits=[hit],
    )

    assert not decision.sufficient


def test_answer_validation_rejects_values_absent_from_citations() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("ratio", "软件企业研发补助比例为30%。")

    valid = gate.validate_answer(
        query="软件企业研发补助比例是多少？",
        answer="软件企业研发补助比例为30%。",
        cited_hits=[hit],
    )
    invalid = gate.validate_answer(
        query="软件企业研发补助比例是多少？",
        answer="软件企业研发补助比例为80%。",
        cited_hits=[hit],
    )

    assert valid.sufficient
    assert not invalid.sufficient
    assert invalid.reason == "answer_contains_unsupported_exact_values"


@pytest.mark.parametrize("threshold", [0, -0.1, 1.1])
def test_gate_rejects_invalid_confidence_configuration(threshold: float) -> None:
    with pytest.raises(ValueError, match="minimum_confidence"):
        EvidenceSufficiencyGate(minimum_confidence=threshold)


def test_gate_rejects_unsafe_answer_overlap_threshold() -> None:
    with pytest.raises(ValueError, match="minimum_answer_overlap"):
        EvidenceSufficiencyGate(minimum_answer_overlap=0.19)
