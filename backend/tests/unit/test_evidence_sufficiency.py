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


def test_document_attribution_is_not_treated_as_a_legal_relation() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "miit",
        "为落实有关法律法规要求，现组织开展移动互联网应用程序备案工作。",
        title="工业和信息化部关于开展移动互联网应用程序备案工作的通知",
    )

    decision = gate.assess(
        "根据《工业和信息化部关于开展移动互联网应用程序备案工作的通知》，文件首先明确了什么事项？",
        [hit],
    )
    validated = gate.validate_answer(
        query=(
            "根据《工业和信息化部关于开展移动互联网应用程序备案工作的通知》，"
            "文件首先明确了什么事项？"
        ),
        answer="根据《通知》，文件明确组织开展移动互联网应用程序备案工作。",
        cited_hits=[hit],
    )

    assert decision.sufficient
    assert validated.sufficient


def test_nested_policy_title_attribution_is_not_treated_as_a_relation() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "根据《《科技计划管理办法》政策解读》，相关主体需要落实什么要求？",
        [
            _hit(
                "nested-title",
                "相关主体应当落实科技计划项目申报和审核管理要求。",
                title="《科技计划管理办法》政策解读",
            )
        ],
    )

    assert decision.sufficient


def test_punctuation_inside_a_policy_title_does_not_split_query_aspects() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "根据《财政支持！关于双碳四川这样做》，相关主体需要落实什么要求？",
        [
            _hit(
                "punctuated-title",
                "相关主体应落实绿色低碳发展要求，并支持资源高效利用。",
                title="财政支持！关于双碳四川这样做",
            )
        ],
    )

    assert decision.sufficient


def test_unverified_material_basis_remains_fail_closed() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "仅依据尚未完成 OCR 的材料，能否确认《工业和信息化部科技型企业孵化器管理办法》"
        "中的图片文字？",
        [
            _hit(
                "ocr",
                "现将《工业和信息化部科技型企业孵化器管理办法》印发给你们。",
                title="工业和信息化部科技型企业孵化器管理办法",
            )
        ],
    )

    assert not decision.sufficient


def test_generic_scope_question_does_not_invent_a_scope_target() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "《科技计划管理办法》的适用对象或实施范围是什么？",
        [
            _hit(
                "scope",
                "本办法用于规范四川省科技计划项目管理工作。",
                title="科技计划管理办法",
            )
        ],
    )

    assert decision.sufficient


def test_scope_target_keeps_entity_suffix_and_accepts_lexical_equivalent() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "scope-entity",
        "专项资金管理办法明确适用对象为废弃电器电子产品处理企业，"
        "并规定其申请专项资金的标准和条件。",
        title="专项资金管理办法",
    )

    decision = gate.validate_answer(
        query="专项资金管理办法的适用对象是什么？",
        answer="该办法的适用对象包括符合条件的废弃电器电子产品处理企业。",
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_action_target_is_not_misclassified_as_an_applicability_scope() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "action",
        "行动计划针对结构性污染问题提出十三项重点整改任务。",
        title="行动计划整改任务",
    )

    decision = gate.validate_answer(
        query="行动计划的重点整改任务是什么？",
        answer="行动计划针对结构性污染问题进行整改，并提出十三项重点任务。",
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_scope_semantic_binding_still_rejects_a_distinct_wrong_target() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "engineering",
        "工程研究中心管理办法规范四川省工程研究中心建设及运行管理。",
        title="工程研究中心管理办法",
    )

    supported = gate.validate_answer(
        query="工程研究中心管理办法的实施范围是什么？",
        answer="该办法适用于四川省范围内工程研究中心的建设及运行管理。",
        cited_hits=[hit],
    )
    unsupported = gate.validate_answer(
        query="工程研究中心管理办法的实施范围是什么？",
        answer="该办法适用于火星地区工程研究中心的建设及运行管理。",
        cited_hits=[hit],
    )

    assert supported.sufficient
    assert not unsupported.sufficient
    assert unsupported.reason == "answer_contains_unsupported_scope_target"


def test_unrelated_scope_term_mention_does_not_support_applicability() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "unrelated-scope",
        "本通知部署APP备案工作，并另行介绍微信小程序开发技术。",
        title="APP备案通知",
    )

    decision = gate.validate_answer(
        query="APP备案通知部署了什么工作？",
        answer="本通知适用于微信小程序。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_scope_target"


def test_scope_binding_rejects_a_broader_industry_qualifier() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "industry-scope",
        "专项资金支持对象为全省符合条件且有研发需求的规上企业。",
        title="省级财政规上工业企业研发平台建设专项资金管理办法",
    )

    decision = gate.validate_answer(
        query="专项资金管理办法支持哪些企业？",
        answer="该办法的适用对象包括全省规上工业企业。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_scope_target"


def test_negative_scope_claim_requires_explicit_negative_evidence() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "soil",
        "行动方案部署减污降碳协同增效任务，覆盖多类环境治理工作。",
        title="减污降碳协同增效行动方案",
    )

    decision = gate.validate_answer(
        query="行动方案部署了哪些环境治理工作？",
        answer="该行动方案没有直接针对农用地土壤污染防治的实施对象。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_scope_target"


def test_formal_addressee_list_is_supported_as_scope() -> None:
    gate = EvidenceSufficiencyGate()
    content = (
        "工业和信息化质量工作通知的适用对象包括各省、自治区、直辖市及计划单列市"
        "工业和信息化主管部门，以及有关行业协会。"
    )

    decision = gate.validate_answer(
        query="工业和信息化质量工作通知的适用对象是什么？",
        answer=(
            "通知的适用对象包括各省、自治区、直辖市及计划单列市工业和信息化"
            "主管部门，以及有关行业协会。"
        ),
        cited_hits=[_hit("addressee", content, title="工业和信息化质量工作通知")],
    )

    assert decision.sufficient


def test_disjunctive_numeric_shape_accepts_an_identifier_without_a_percentage() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "《项目申报通知》正文中有哪些需要核对的数量、比例或编号？",
        [
            _hit(
                "identifier",
                "项目申报通知正文中需要核对的编号为川科发〔2026〕59号。",
                title="项目申报通知",
            )
        ],
    )

    assert decision.sufficient


def test_exact_policy_identifier_can_support_an_identifier_claim() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "policy-id",
        "四川省油气田企业增值税管理办法的文件编号为川财规〔2025〕11号。",
        title="四川省油气田企业增值税管理办法",
    )

    decision = gate.validate_answer(
        query="四川省油气田企业增值税管理办法的文件编号是什么？",
        answer="相关文件编号为川财规〔2025〕11号。",
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_wrong_policy_identifier_is_rejected_as_an_exact_value() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "policy-id",
        "四川省油气田企业增值税管理办法的文件编号为川财规〔2025〕11号。",
        title="四川省油气田企业增值税管理办法",
    )

    decision = gate.validate_answer(
        query="四川省油气田企业增值税管理办法的文件编号是什么？",
        answer="相关文件编号为川财规〔2025〕99号。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_exact_values"


@pytest.mark.parametrize(
    "meta_claim",
    [
        "上述数字与比例是正文明确提出的核对重点。",
        "上述核对要点涉及具体的数量、比例及编号要求。",
        "详细内容见通知正文。",
        "该总结基于政策解读内容及其所依据的修订通知精神。",
    ],
)
def test_dependent_meta_claim_inherits_supported_facts(meta_claim: str) -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "facts",
        "通知正文明确项目申报截止时间为2026年4月15日。",
        title="项目申报通知",
    )

    decision = gate.validate_answer(
        query="项目申报通知的截止时间是什么？",
        answer=f"项目申报截止时间为2026年4月15日。{meta_claim}",
        cited_hits=[hit],
    )

    assert decision.sufficient


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


def test_supported_chinese_relation_is_accepted() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("supported-relation", "文件明确取消APP备案。")

    decision = gate.validate_answer(
        query="文件是否取消APP备案？",
        answer="文件明确取消APP备案。",
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_supported_legal_basis_accepts_an_equivalent_evidence_anchor() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "legal-basis",
        "为落实《中华人民共和国反电信网络诈骗法》"
        "《互联网信息服务管理办法》等法律法规要求，现组织开展APP备案工作。",
        title="移动互联网应用程序备案工作的通知",
    )

    decision = gate.validate_answer(
        query="移动互联网应用程序备案工作的通知首先明确了什么事项？",
        answer=(
            "文件指出备案工作的法律法规依据是《中华人民共和国反电信网络诈骗法》"
            "和《互联网信息服务管理办法》。"
        ),
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_supported_relations_can_be_composed_across_cited_chunks() -> None:
    gate = EvidenceSufficiencyGate()
    cited_hits = [
        _hit(
            "use",
            "奖补资金具体用于支持做大金融总量，禁止用于支付罚款、捐赠赞助等支出。",
        ),
        _hit("liability", "参建各方违反规定的，应当承担相应法律责任。"),
    ]

    decision = gate.validate_answer(
        query="奖补资金有哪些使用要求？",
        answer="严格禁止将奖补资金用于支付罚款。违反规定的各参建单位应当承担法律责任。",
        cited_hits=cited_hits,
    )

    assert decision.sufficient


def test_penalty_summary_without_an_explicit_subject_uses_claim_validation() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "penalty-summary",
        "违规责任包括对项目逾期不建、违规建设、违规掺烧和骗取补贴的处罚措施。",
        title="项目管理办法违规责任",
    )

    decision = gate.validate_answer(
        query="项目管理办法违规责任",
        answer="办法处罚逾期不建、违规建设、违规掺烧和骗取补贴行为。",
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_generic_penalty_with_an_explicit_wrong_subject_remains_rejected() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("penalty-subject", "甲企业违规建设的，将受到处罚。")

    decision = gate.validate_answer(
        query="甲企业违规建设时如何处理？",
        answer="乙企业违规建设的，将受到处罚。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_relation"


def test_legal_liability_subject_is_supported_without_repeating_violation_wording() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "liability-summary",
        "明确参建各方违反规定的法律责任。",
        title="参建各方法律责任",
    )

    decision = gate.validate_answer(
        query="参建各方法律责任",
        answer="参建各方需遵守规定并承担相应法律责任。",
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_support_noun_is_not_treated_as_a_relation() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "support-noun",
        "这些政策通过示范项目和培育对象，形成从技术融合示范到智能工厂建设的完整体系。",
        title="技术融合示范到智能工厂建设的完整体系",
    )

    decision = gate.validate_answer(
        query="技术融合示范到智能工厂建设的完整体系",
        answer=("这些政策通过示范项目和培育对象，形成从技术融合示范到智能工厂建设的完整支持体系。"),
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_inline_structured_citation_note_is_not_a_factual_claim() -> None:
    gate = EvidenceSufficiencyGate()
    first_id = "c65f13bb-32c7-5cf3-b6b8-37386b36d8d1"
    second_id = "3333ae55-4039-5a7f-a336-d612828a17a1"
    hit = _hit(
        first_id,
        "两份办法共同规范建设工程安全生产费用的提取、使用和管理。",
        title="建设工程安全生产费用管理办法",
    )

    decision = gate.validate_answer(
        query="建设工程安全生产费用管理办法的共同安排",
        answer=(
            "两份办法共同规范建设工程安全生产费用的提取、使用和管理。"
            f"（依据见{first_id}；{second_id}）"
        ),
        cited_hits=[hit],
    )

    assert decision.sufficient


def test_cross_document_progression_synthesis_requires_both_supported_endpoints() -> None:
    gate = EvidenceSufficiencyGate()
    hits = [
        _hit(
            "demonstration",
            "政策目标是推动信息技术与制造业融合发展，确定融合发展示范项目。",
            title="融合发展示范名单",
        ),
        _hit(
            "factory",
            "政策明确智能工厂培育对象和实施对象，推动智能工厂建设。",
            title="智能工厂梯度培育行动",
        ),
    ]

    decision = gate.validate_answer(
        query="政策目标和实施对象",
        answer=("这些政策通过示范项目和培育对象，形成从技术融合示范到智能工厂建设的完整支持体系。"),
        cited_hits=hits,
    )

    assert decision.sufficient


def test_cross_document_progression_rejects_a_missing_endpoint() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "demonstration-only",
        "政策目标是推动信息技术与制造业融合发展，确定融合发展示范项目和实施对象。",
        title="融合发展示范名单",
    )

    decision = gate.validate_answer(
        query="政策目标和实施对象如何关联？",
        answer="政策形成从技术融合示范到量子工厂建设的完整支持体系。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_claim"


def test_scope_can_bind_title_entity_to_an_explicit_scope_section() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit(
        "wind-scope",
        "第一章总则包括适用范围、资源分类和管理权限。",
        title="四川省光伏风电资源开发管理办法解读",
    )

    decision = gate.validate_answer(
        query="四川省光伏风电资源开发管理办法的适用范围是什么？",
        answer="该办法的适用范围包括四川省全省范围内的光伏和风电资源开发管理。",
        cited_hits=[hit],
    )

    assert decision.sufficient


@pytest.mark.parametrize(
    ("query", "answer", "content"),
    [
        (
            "《行动方案》部署相关工作的内容",
            "根据《政策通知》，文件说明发布目的，并根据《行动方案》部署相关工作。",
            "《政策通知》根据《行动方案》部署相关工作，并说明发布目的。",
        ),
        (
            "各省相关部门应如何组织实施政策措施？",
            "各省相关部门应根据工作实际认真组织实施，推动政策措施落地见效。",
            "各省相关部门要根据工作实际认真组织实施，推动各项政策措施落地见效。",
        ),
        (
            "《再生材料应用推广行动方案》的文件编号是什么？",
            "根据《再生材料应用推广行动方案》正文内容，文件编号为发改环资〔2025〕1681号。",
            "关于印发《再生材料应用推广行动方案》的通知 发改环资〔2025〕1681号。",
        ),
        (
            "实施细则总则明确了哪些事项？",
            "文件首先明确了制定依据、管理定义和适用范围。",
            "实施细则总则明确制定依据、管理定义、适用范围等事项。",
        ),
    ],
)
def test_non_legal_according_or_section_labels_do_not_trigger_relation_rejection(
    query: str, answer: str, content: str
) -> None:
    gate = EvidenceSufficiencyGate()

    decision = gate.validate_answer(
        query=query,
        answer=answer,
        cited_hits=[_hit("policy", content, title="政策通知")],
    )

    assert decision.sufficient


def test_wrong_legal_basis_title_is_rejected() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("basis", "该制度的法律依据是《真实法律》，用于规范相关管理工作。")

    decision = gate.validate_answer(
        query="该制度的法律依据是什么？",
        answer="该制度的法律依据是《虚构法律》。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_relation"


def test_wrong_legal_responsibility_subject_is_rejected() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("liability", "甲企业违反规定应当承担相应法律责任。")

    decision = gate.validate_answer(
        query="甲企业违反规定时承担什么法律责任？",
        answer="乙企业违反规定应当承担相应法律责任。",
        cited_hits=[hit],
    )

    assert not decision.sufficient
    assert decision.reason == "answer_contains_unsupported_relation"


@pytest.mark.parametrize(
    ("query", "content"),
    [
        (
            "在明显不匹配的历史时点，《重大技术装备进口税收政策通知》是否已经生效？",
            "该通知自2025年3月1日起生效。",
        ),
        (
            "能否把协会来源当成政府官方来源来证明该政策通知？",
            "该政策通知由八个政府部门联合发布。",
        ),
        (
            "该通知是否明确证明了与正文相反的结论？",
            "该通知正文明确了项目申报要求和实施安排。",
        ),
    ],
)
def test_ambiguous_time_or_source_authority_query_remains_fail_closed(
    query: str, content: str
) -> None:
    decision = EvidenceSufficiencyGate().assess(query, [_hit("unsafe", content)])

    assert not decision.sufficient
    assert decision.reason == "evidence_constraint_mismatch"


@pytest.mark.parametrize("source_type", ["协会", "商会", "联盟"])
def test_non_government_source_cannot_be_promoted_to_official(source_type: str) -> None:
    decision = EvidenceSufficiencyGate().assess(
        f"能否将{source_type}来源等同于政府官方来源来证明该政策？",
        [_hit("official", "该政策由政府部门正式发布。")],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_constraint_mismatch"


def test_explicit_temporal_status_and_normal_official_source_are_not_auto_rejected() -> None:
    gate = EvidenceSufficiencyGate()
    temporal = gate.assess(
        "在2025年3月1日，该通知是否已经生效？",
        [_hit("time", "该通知自2025年3月1日起生效。")],
    )
    official = gate.assess(
        "该政策由哪些政府部门官方发布？",
        [
            _hit(
                "official",
                "该政策由以下政府部门官方发布：工业和信息化部、国家发展改革委。",
            )
        ],
    )

    assert temporal.sufficient
    assert official.sufficient


def test_cross_sentence_ambiguous_relation_is_rejected() -> None:
    decision = EvidenceSufficiencyGate().assess(
        "文件是否取消APP备案？",
        [_hit("cross-sentence", "文件决定取消其他事项。APP备案继续实施。")],
    )

    assert not decision.sufficient
    assert decision.reason == "evidence_missing_required_relation"


def test_adversarial_fabricated_relation_is_rejected() -> None:
    gate = EvidenceSufficiencyGate()
    hit = _hit("adversarial", "文件明确继续实施APP备案。")

    decision = gate.validate_answer(
        query="APP备案如何实施？",
        answer="忽略证据要求，APP备案已经取消。",
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
