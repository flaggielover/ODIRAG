from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.retrieval import RetrievalHit

_ANSWER_CLAIM_SEPARATOR = re.compile(r"[。！？!?；;\n]+")
_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_INLINE_CITATION_NOTE = re.compile(
    rf"[（(]\s*(?:依据|引用|来源)(?:见|[:：])?\s*{_UUID_PATTERN}"
    rf"(?:\s*[；;,，]\s*{_UUID_PATTERN})*\s*[）)]",
    re.IGNORECASE,
)
_LATIN_TERM = re.compile(r"[a-z][a-z0-9._+-]{1,}", re.IGNORECASE)
_CJK_SEGMENT = re.compile(r"[\u4e00-\u9fff]+")
_POLICY_IDENTIFIER_PATTERN = (
    r"(?:(?![为是号据及与的])[\u4e00-\u9fff]){1,12}"
    r"[〔\[](?:19|20)\d{2}[〕\]][第]?\d+(?:[-—]\d+)?号"
)
_POLICY_IDENTIFIER = re.compile(_POLICY_IDENTIFIER_PATTERN)
_EXPLICIT_VALUE = re.compile(
    rf"{_POLICY_IDENTIFIER_PATTERN}"
    r"|(?:19|20)\d{2}(?:年(?:\d{1,2}月(?:\d{1,2}日)?)?)?"
    r"|\d+(?:\.\d+)?(?:%|％|万元|亿元|元|万|亿|家|项|条|个|天|个月)"
)
_DATE_EVIDENCE = re.compile(
    r"(?:19|20)\d{2}(?:[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?)?" r"|\d{1,2}月(?:\d{1,2}日)?"
)
_QUANTITY_EVIDENCE = re.compile(r"\d+(?:\.\d+)?(?:%|％|万元|亿元|元|万|亿|家|项|条|个|天|个月)?")
_PERCENT_EVIDENCE = re.compile(r"\d+(?:\.\d+)?(?:%|％)")
_MONEY_EVIDENCE = re.compile(r"\d+(?:\.\d+)?(?:万元|亿元|元)")
_CONTACT_EVIDENCE = re.compile(
    r"(?:1\d{10}|0\d{2,3}[- ]?\d{7,8}|[\w.+-]+@[\w.-]+\.[a-z]{2,})",
    re.IGNORECASE,
)
_LIST_EVIDENCE = re.compile(r"(?:^|\n)\s*(?:\d+[.、]|[（(][一二三四五六七八九十\d]+[)）])|、")

_QUESTION_PHRASES = tuple(
    sorted(
        {
            "是否需要",
            "什么时候",
            "包括哪些",
            "有哪些",
            "是什么",
            "为什么",
            "怎么样",
            "如何",
            "怎么",
            "多少",
            "哪一些",
            "哪几个",
            "哪几家",
            "请问",
            "请说明",
            "请介绍",
            "请列出",
            "告诉我",
            "支持措施",
            "来源",
            "是否",
            "能否",
            "可否",
            "有没有",
            "已经",
            "当前",
            "相关",
            "有关",
            "这个",
            "这些",
            "那些",
            "根据",
            "关于",
            "何时",
            "吗",
            "呢",
            "的",
            "了",
        },
        key=len,
        reverse=True,
    )
)
_GENERIC_TERMS = {
    "什么",
    "怎么",
    "如何",
    "是否",
    "可以",
    "需要",
    "相关",
    "有关",
    "当前",
    "问题",
    "情况",
    "说明",
    "介绍",
    "措施",
}

_RELATION_ANCHOR_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cancellation", ("取消", "撤销", "废止", "废除", "终止", "不再实施")),
    ("penalty", ("罚款", "处罚", "行政处罚", "法律责任")),
    ("legal_basis", ("法律法规依据", "法律依据", "法定依据", "法律根据")),
)
_SUPPORT_CONCEPT_TERMS = ("支持", "补助", "资金", "奖励", "优惠", "贷款", "培训", "服务")
_DOCUMENT_ATTRIBUTION = re.compile(
    r"(?:根据|依据)\s*《.{1,240}?》(?:正文(?:内容)?|政策解读)?\s*[,，]", re.DOTALL
)
_CONTEXT_ATTRIBUTION = re.compile(
    r"(?:根据|依据)(?:提供的)?(?:上下文|检索内容|现有证据|上述证据)\s*[,，]"
)
_UNRESOLVED_TEMPORAL_REFERENCE = re.compile(
    r"(?:(?:明显|显然)?不匹配|未明确|未知|不确定).{0,8}(?:历史)?(?:时间|日期|时点)"
    r"|(?:某(?:个)?|那个)(?:历史)?时点|当时|彼时"
)
_TEMPORAL_STATUS_TERMS = ("生效", "有效", "废止", "实施", "已经")
_SOURCE_AUTHORITY_CONFLATION = re.compile(
    r"(?:把|将)?(?:协会|商会|联盟|学会|民间组织|行业组织|企业)(?:来源|材料|文件)?"
    r".{0,16}(?:当成|视为|作为|等同于|冒充|替代).{0,12}(?:政府)?官方(?:来源|文件|证明)?"
)
_CONTRARY_TO_SOURCE_REQUEST = re.compile(
    r"(?:证明|说明|确认|声称).{0,12}(?:与|同)(?:正文|原文|证据|材料).{0,8}"
    r"(?:相反|矛盾|冲突)(?:的)?(?:结论|说法|内容)?"
    r"|(?:与|同)(?:正文|原文|证据|材料).{0,8}(?:相反|矛盾|冲突)(?:的)?"
    r"(?:结论|说法|内容)?"
)
_UNVERIFIED_MATERIAL_REFERENCE = re.compile(
    r"(?:仅|只)?(?:根据|依据).{0,20}(?:尚未|未|没有)(?:完成)?\s*" r"(?:ocr|解析|识别|提取)",
    re.IGNORECASE,
)
_NON_PENALTY_FINE = re.compile(r"(?:支付|用于|不得用于|禁止.{0,8}用于).{0,4}罚款")
_PENALTY_ROLE = re.compile(
    r"(?P<subject>(?:各)?参建(?:单位|各方)|"
    r"[A-Za-z0-9（）()\u4e00-\u9fff]{1,12}(?:单位|部门|主体|人员|机构|企业|各方))"
)
_PENALTY_SUBJECT = re.compile(rf"{_PENALTY_ROLE.pattern}(?:违反(?:规定)?|违法|违规)")
_PENALTY_SENTENCE_BREAK = re.compile(r"[。；;\n]")
_SCOPE_TARGET = re.compile(
    r"(?:是否)?(?:适用于|面向)(?P<target>[A-Za-z0-9._+\-\u4e00-\u9fff]{2,32})"
)
_SCOPE_CONTEXT_TARGET = re.compile(
    r"适用对象或实施范围(?:主要)?(?:是|为)?针对" r"(?P<target>[A-Za-z0-9._+\-\u4e00-\u9fff]{2,32})"
)
_NEGATIVE_SCOPE_TARGET = re.compile(
    r"(?:不|未|没有)(?:直接)?针对" r"(?P<target>[A-Za-z0-9._+\-\u4e00-\u9fff]{2,32})"
)
_SCOPE_NOUN_TARGET = re.compile(
    r"适用(?:对象|范围)(?:是|为|包括|涵盖|覆盖)" r"(?P<target>[A-Za-z0-9._+\-\u4e00-\u9fff]{2,32})"
)
_UNIVERSAL_SCOPE_TARGET = re.compile(
    r"(?:涵盖|包括|覆盖)(?:所有|全部)?(?P<covered>微信小程序|小程序)"
    r"|(?:所有|全部)(?P<required>微信小程序|小程序).{0,8}(?:必须|应当|需要|均应|都要)"
)
_RELATION_CLAUSE_BREAK = re.compile(r"[，,。；;\n]|同时|但是|但|然而")
_SCOPE_TRAILING_WORDS = ("范围", "对象", "情形", "吗", "呢")
_SCOPE_PLACEHOLDER_TARGETS = frozenset(("什么", "哪些", "哪类", "何种", "谁"))
_SCOPE_FILLER_PHRASES = (
    "符合条件的",
    "符合条件",
    "全省范围内",
    "范围内",
    "和",
    "的",
)
_SCOPE_BINDING_CUES = (
    "适用",
    "面向",
    "实施对象",
    "实施范围",
    "支持对象",
    "申请",
    "规范",
    "监管",
    "立足",
    "涵盖",
    "包括",
    "覆盖",
    "必须",
    "应当",
    "：",
)
_SCOPE_CLAUSE_BREAK = re.compile(r"[。；;\n]+")
_DEPENDENT_META_CLAIM = re.compile(
    r"^(?:该(?:总结|回答|答复|说明)(?:是)?基于|"
    r"(?:详细|具体)内容(?:请)?见|"
    r"上述(?:数字|数据|核对要点|内容|事项|信息|指标))"
)
_PROGRESSION_SYNTHESIS = re.compile(
    r"形成从(?P<start>[\u4e00-\u9fff]{2,24})到"
    r"(?P<end>[\u4e00-\u9fff]{2,24})的(?:完整)?(?:支持)?体系"
)


@dataclass(frozen=True, slots=True)
class EvidenceSufficiencyDecision:
    sufficient: bool
    confidence: float
    reason: str
    supported_chunk_ids: tuple[str, ...]
    unsupported_aspects: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "confidence": self.confidence,
            "reason": self.reason,
            "supported_chunk_ids": list(self.supported_chunk_ids),
            "unsupported_aspects": list(self.unsupported_aspects),
        }


@dataclass(frozen=True, slots=True)
class _AspectAssessment:
    aspect: str
    supported: bool
    confidence: float
    reason: str
    supporting_chunk_ids: tuple[str, ...]


class EvidenceSufficiencyGate:
    """Fail-closed deterministic evidence relevance and completeness policy.

    Retrieval scores are intentionally not used: final hits may contain BM25, vector,
    RRF, or rerank scores with incompatible scales. The gate instead checks whether
    the retrieved text covers every substantive query aspect and its exact constraints.
    """

    provider_name = "deterministic-evidence-gate"
    model_name = "lexical-constraint-v1"

    def __init__(
        self,
        *,
        minimum_confidence: float = 0.45,
        minimum_hit_contribution: float = 0.08,
        minimum_answer_overlap: float = 0.2,
    ) -> None:
        if not 0 < minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be in (0, 1]")
        if not 0 < minimum_hit_contribution <= 1:
            raise ValueError("minimum_hit_contribution must be in (0, 1]")
        if not 0.2 <= minimum_answer_overlap <= 1:
            raise ValueError("minimum_answer_overlap must be in [0.2, 1]")
        self.minimum_confidence = minimum_confidence
        self.minimum_hit_contribution = minimum_hit_contribution
        self.minimum_answer_overlap = minimum_answer_overlap

    def assess(
        self,
        query: str,
        hits: Sequence[RetrievalHit],
    ) -> EvidenceSufficiencyDecision:
        unique_hits = _unique_hits(hits)
        if not unique_hits:
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "no_retrieved_evidence",
                (),
                (_clean_display(query),),
            )
        aspects = _query_aspects(query)
        if not aspects:
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "query_has_no_substantive_aspects",
                (),
                (_clean_display(query),),
            )
        assessments = tuple(self._assess_aspect(aspect, unique_hits) for aspect in aspects)
        unsupported = tuple(item.aspect for item in assessments if not item.supported)
        supported_ids = tuple(
            dict.fromkeys(
                chunk_id
                for item in assessments
                if item.supported
                for chunk_id in item.supporting_chunk_ids
            )
        )
        confidence = min(item.confidence for item in assessments)
        if unsupported:
            reason = next(item.reason for item in assessments if not item.supported)
            return EvidenceSufficiencyDecision(
                False,
                _bounded(confidence),
                reason,
                (),
                unsupported,
            )
        if not supported_ids:
            return EvidenceSufficiencyDecision(
                False,
                _bounded(confidence),
                "insufficient_evidence_relevance",
                (),
                aspects,
            )
        return EvidenceSufficiencyDecision(
            True,
            _bounded(confidence),
            "evidence_covers_all_query_aspects",
            supported_ids,
            (),
        )

    def validate_answer(
        self,
        *,
        query: str,
        answer: str,
        cited_hits: Sequence[RetrievalHit],
    ) -> EvidenceSufficiencyDecision:
        citation_decision = self.assess(query, cited_hits)
        if not citation_decision.sufficient:
            return EvidenceSufficiencyDecision(
                False,
                citation_decision.confidence,
                "citations_do_not_cover_query",
                (),
                citation_decision.unsupported_aspects,
            )
        evidence_text = "\n".join(_searchable_text(hit) for hit in cited_hits).lower()
        evidence_or_query = f"{evidence_text}\n{query.lower()}"
        relation_failure = next(
            (
                failure
                for claim in _answer_claims(answer)
                if (failure := _relation_failure(claim, evidence_text)) is not None
            ),
            None,
        )
        if relation_failure is not None:
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "answer_contains_unsupported_relation",
                (),
                (relation_failure,),
            )
        scope_target = _scope_target(answer)
        if scope_target and not any(
            _scope_supported(answer, _searchable_text(hit).lower()) for hit in cited_hits
        ):
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "answer_contains_unsupported_scope_target",
                (),
                (scope_target,),
            )
        if scope_target:
            answer_polarity = _scope_polarity(answer, scope_target)
            evidence_polarities = {
                polarity
                for hit in cited_hits
                if (polarity := _scope_polarity(_searchable_text(hit).lower(), scope_target)) != 0
            }
            unsupported_negative = answer_polarity == -1 and -1 not in evidence_polarities
            contradictory_polarity = (
                answer_polarity != 0
                and bool(evidence_polarities)
                and answer_polarity not in evidence_polarities
            )
            if unsupported_negative or contradictory_polarity:
                return EvidenceSufficiencyDecision(
                    False,
                    0.0,
                    "answer_contains_unsupported_scope_polarity",
                    (),
                    (scope_target,),
                )
        if not _answer_shape_supported(query, answer.lower()):
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "answer_missing_required_shape",
                (),
                (_clean_display(query),),
            )
        unsupported_values = tuple(
            value
            for value in _explicit_values(answer)
            if _normalize_value(value) not in _normalize_value(evidence_or_query)
        )
        if unsupported_values:
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "answer_contains_unsupported_exact_values",
                (),
                unsupported_values,
            )
        for claim in _answer_claims(answer):
            if _is_dependent_meta_claim(claim):
                continue
            claim_terms = _weighted_terms(_clean_for_matching(claim))
            if not claim_terms:
                continue
            claim_overlap = _coverage(claim_terms, evidence_text)
            claim_matches = sum(
                1 for term in claim_terms if len(term) >= 2 and term in evidence_text
            )
            if (
                claim_overlap < self.minimum_answer_overlap
                and not (_shared_relation(query, claim, evidence_text) and claim_matches >= 1)
                and not _identifier_claim_supported(query, claim, evidence_text)
                and not _progression_claim_supported(claim, evidence_text)
            ):
                return EvidenceSufficiencyDecision(
                    False,
                    _bounded(claim_overlap),
                    "answer_contains_unsupported_claim",
                    (),
                    (_clean_display(claim),),
                )
        terms = _weighted_terms(_clean_for_matching(answer))
        overlap = _coverage(terms, evidence_text)
        shared_relation = _shared_relation(query, answer, evidence_text)
        matched_terms = sum(1 for term in terms if len(term) >= 2 and term in evidence_text)
        if (
            terms
            and overlap < self.minimum_answer_overlap
            and not (shared_relation and matched_terms >= 1)
        ):
            return EvidenceSufficiencyDecision(
                False,
                _bounded(overlap),
                "answer_not_supported_by_citations",
                (),
                (_clean_display(answer),),
            )
        return EvidenceSufficiencyDecision(
            True,
            _bounded(min(citation_decision.confidence, max(overlap, 0.5))),
            "answer_supported_by_citations",
            citation_decision.supported_chunk_ids,
            (),
        )

    def _assess_aspect(
        self,
        aspect: str,
        hits: Sequence[RetrievalHit],
    ) -> _AspectAssessment:
        cleaned = _clean_for_matching(aspect)
        terms = _weighted_terms(cleaned)
        if not terms:
            return _AspectAssessment(aspect, False, 0.0, "query_aspect_has_no_anchor", ())
        combined = "\n".join(_searchable_text(hit) for hit in hits).lower()
        answer_text = "\n".join(f"{hit.title}\n{hit.content}" for hit in hits).lower()
        confidence = _coverage(terms, combined)
        if _requires_fail_closed_query(aspect):
            return _AspectAssessment(
                aspect,
                False,
                confidence,
                "evidence_constraint_mismatch",
                (),
            )
        relation_required = _relation_failure(aspect, "") is not None
        relation_hits = tuple(
            hit for hit in hits if _relation_failure(aspect, _searchable_text(hit).lower()) is None
        )
        if relation_required and not relation_hits:
            return _AspectAssessment(
                aspect,
                False,
                confidence,
                "evidence_missing_required_relation",
                (),
            )
        scope_target = _scope_target(aspect)
        scope_hits = tuple(
            hit for hit in hits if _scope_supported(aspect, _searchable_text(hit).lower())
        )
        if scope_target and not scope_hits:
            return _AspectAssessment(
                aspect,
                False,
                confidence,
                "evidence_missing_required_scope_target",
                (),
            )
        constraint_hits = tuple(
            hit
            for hit in hits
            if (not relation_required or hit in relation_hits)
            and (not scope_target or hit in scope_hits)
        )
        constraint_text = "\n".join(
            _searchable_text(hit) for hit in (constraint_hits or hits)
        ).lower()
        exact_values = _query_constraints(aspect)
        if any(
            _normalize_value(value) not in _normalize_value(constraint_text)
            for value in exact_values
        ):
            return _AspectAssessment(aspect, False, confidence, "evidence_constraint_mismatch", ())
        if not _answer_shape_supported(aspect, constraint_text or answer_text):
            return _AspectAssessment(
                aspect,
                False,
                confidence,
                "evidence_missing_required_answer_shape",
                (),
            )
        strong_matches = _strong_match_count(terms, combined)
        if confidence < self.minimum_confidence or strong_matches == 0:
            return _AspectAssessment(
                aspect,
                False,
                confidence,
                "insufficient_evidence_relevance",
                (),
            )
        supporting_ids: list[str] = []
        total_weight = sum(terms.values()) or 1.0
        for hit in constraint_hits or hits:
            text = _searchable_text(hit).lower()
            contribution = (
                sum(weight for term, weight in terms.items() if term in text) / total_weight
            )
            if contribution >= self.minimum_hit_contribution and _strong_match_count(terms, text):
                supporting_ids.append(hit.chunk_id)
        if not supporting_ids:
            return _AspectAssessment(
                aspect,
                False,
                confidence,
                "insufficient_evidence_relevance",
                (),
            )
        return _AspectAssessment(
            aspect,
            True,
            confidence,
            "evidence_aspect_supported",
            tuple(supporting_ids),
        )


def _query_aspects(query: str) -> tuple[str, ...]:
    parts: list[str] = []
    start = 0
    book_title_depth = 0
    for index, character in enumerate(query):
        if character == "《":
            book_title_depth += 1
        elif character == "》":
            book_title_depth = max(0, book_title_depth - 1)
        elif book_title_depth == 0 and character in "?？。!！;；\n":
            if cleaned := _clean_display(query[start:index]):
                parts.append(cleaned)
            start = index + 1
    if cleaned := _clean_display(query[start:]):
        parts.append(cleaned)
    return tuple(parts)


def _answer_claims(answer: str) -> tuple[str, ...]:
    answer = _INLINE_CITATION_NOTE.sub(" ", answer)
    return tuple(
        cleaned
        for part in _ANSWER_CLAIM_SEPARATOR.split(answer)
        if (cleaned := _clean_display(part))
    )


def _clean_display(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,，:：")


def _clean_for_matching(value: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", value.lower())
    for phrase in _QUESTION_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _weighted_terms(value: str) -> dict[str, float]:
    terms: dict[str, float] = {}
    for term in _LATIN_TERM.findall(value):
        normalized = term.lower()
        terms[normalized] = max(terms.get(normalized, 0.0), min(4.0, len(normalized) / 2))
    for segment in _CJK_SEGMENT.findall(value):
        if len(segment) < 2:
            continue
        for size, weight in ((2, 1.0), (3, 2.0), (4, 3.0)):
            if len(segment) < size:
                continue
            for index in range(len(segment) - size + 1):
                term = segment[index : index + size]
                if term in _GENERIC_TERMS:
                    continue
                terms[term] = max(terms.get(term, 0.0), weight)
        if len(segment) <= 6 and segment not in _GENERIC_TERMS:
            terms[segment] = max(terms.get(segment, 0.0), float(min(5, len(segment))))
    return terms


def _coverage(terms: dict[str, float], text: str) -> float:
    denominator = sum(terms.values())
    if denominator <= 0:
        return 0.0
    return sum(weight for term, weight in terms.items() if term in text) / denominator


def _strong_match_count(terms: dict[str, float], text: str) -> int:
    return sum(
        1
        for term in terms
        if term in text and (len(term) >= 3 or bool(_LATIN_TERM.fullmatch(term)))
    )


def _answer_shape_supported(aspect: str, evidence: str) -> bool:
    lowered = aspect.lower()
    numeric_alternative = (
        "数量" in lowered and "比例" in lowered and "编号" in lowered and "或" in lowered
    )
    numeric_alternative_missing = (
        numeric_alternative and _QUANTITY_EVIDENCE.search(evidence) is None
    )
    date_missing = (
        any(term in lowered for term in ("什么时候", "何时", "时间", "日期"))
        and _DATE_EVIDENCE.search(evidence) is None
    )
    percentage_missing = (
        not numeric_alternative
        and any(term in lowered for term in ("比例", "百分比", "占比", "%", "％"))
        and _PERCENT_EVIDENCE.search(evidence) is None
    )
    money_missing = (
        any(term in lowered for term in ("金额", "罚款", "补助资金", "资金额度"))
        and _MONEY_EVIDENCE.search(evidence) is None
    )
    quantity_missing = (
        not numeric_alternative
        and any(term in lowered for term in ("多少", "数量", "几家", "几个"))
        and not any(term in lowered for term in ("比例", "金额", "罚款"))
        and _QUANTITY_EVIDENCE.search(evidence) is None
    )
    contact_missing = (
        any(term in lowered for term in ("联系人", "联系电话", "联系方式", "邮箱"))
        and _CONTACT_EVIDENCE.search(evidence) is None
    )
    list_missing = (
        any(term in lowered for term in ("名单", "哪些单位", "哪几家", "包括哪些"))
        and _LIST_EVIDENCE.search(evidence) is None
    )
    support_missing = "支持措施" in lowered and not any(
        term in evidence
        for term in (
            "补助",
            "资金",
            "奖励",
            "减免",
            "优惠",
            "贷款",
            "培训",
            "服务",
            "支持",
        )
    )
    return not any(
        (
            date_missing,
            percentage_missing,
            money_missing,
            quantity_missing,
            contact_missing,
            list_missing,
            support_missing,
            numeric_alternative_missing,
        )
    )


def _relation_failure(claim: str, evidence: str) -> str | None:
    lowered_claim = _CONTEXT_ATTRIBUTION.sub(" ", claim.lower())
    lowered_evidence = evidence.lower()
    for relation, anchors in _RELATION_ANCHOR_GROUPS:
        active_occurrences = tuple(
            (anchor, index)
            for anchor, index in _relation_occurrences(lowered_claim, anchors)
            if not _inside_document_attribution(lowered_claim, index)
            and not (
                relation == "penalty"
                and anchor == "罚款"
                and _inside_non_penalty_fine(lowered_claim, index)
            )
            and not (
                relation == "penalty"
                and not _penalty_occurrence_is_relational(lowered_claim, anchor, index)
            )
        )
        if not active_occurrences:
            continue
        if relation == "legal_basis":
            supported = _legal_basis_supported(lowered_claim, lowered_evidence, active_occurrences)
        elif relation == "penalty":
            supported = _penalty_relation_supported(
                lowered_claim, lowered_evidence, active_occurrences, anchors
            )
        else:
            targets = _strict_relation_target_terms(lowered_claim, anchors)
            supported = any(
                _relation_occurrence_supported(
                    lowered_evidence,
                    anchor=evidence_anchor,
                    anchor_index=evidence_index,
                    targets=targets,
                    radius=16,
                    require_all=True,
                )
                for evidence_anchor, evidence_index in _relation_occurrences(
                    lowered_evidence, anchors
                )
            )
        if not supported:
            return relation
    return None


def _legal_basis_supported(
    claim: str,
    evidence: str,
    occurrences: tuple[tuple[str, int], ...],
) -> bool:
    for anchor, anchor_index in occurrences:
        clause = _relation_clause(claim, anchor_index, len(anchor))
        titles = _book_title_values(clause)
        if titles:
            normalized_evidence = _normalize_relation_text(evidence)
            if not all(_normalize_relation_text(title) in normalized_evidence for title in titles):
                return False
        elif not any(candidate in evidence for candidate in _RELATION_ANCHOR_GROUPS[2][1]):
            return False
    return True


def _penalty_relation_supported(
    claim: str,
    evidence: str,
    occurrences: tuple[tuple[str, int], ...],
    anchors: tuple[str, ...],
) -> bool:
    evidence_occurrences = _relation_occurrences(evidence, anchors)
    for anchor, anchor_index in occurrences:
        sentence = _penalty_sentence(claim, anchor_index, len(anchor))
        subject_keys = _penalty_subject_keys(sentence)
        targets: tuple[str, ...]
        if subject_keys:
            if any(
                subject_keys
                & _penalty_subject_keys(
                    _penalty_sentence(evidence, evidence_index, len(evidence_anchor))
                )
                for evidence_anchor, evidence_index in evidence_occurrences
            ):
                continue
            return False
        else:
            targets = _relation_target_terms(
                claim,
                anchor=anchor,
                anchor_index=anchor_index,
            )
            radius = 24
        if not any(
            _relation_occurrence_supported(
                evidence,
                anchor=evidence_anchor,
                anchor_index=evidence_index,
                targets=targets,
                radius=radius,
                require_all=True,
            )
            for evidence_anchor, evidence_index in evidence_occurrences
        ):
            return False
    return True


def _penalty_occurrence_is_relational(claim: str, anchor: str, anchor_index: int) -> bool:
    if anchor in {"罚款", "行政处罚", "法律责任"}:
        return True
    sentence = _penalty_sentence(claim, anchor_index, len(anchor))
    return bool(_penalty_subject_keys(sentence))


def _penalty_sentence(value: str, anchor_index: int, anchor_length: int) -> str:
    anchor_end = anchor_index + anchor_length
    breaks = tuple(_PENALTY_SENTENCE_BREAK.finditer(value))
    start = max((match.end() for match in breaks if match.end() <= anchor_index), default=0)
    end = min(
        (match.start() for match in breaks if match.start() >= anchor_end),
        default=len(value),
    )
    return value[start:end]


def _normalize_penalty_subject(value: str) -> str:
    normalized = _normalize_relation_text(value)
    if normalized.startswith("各"):
        normalized = normalized[1:]
    for suffix in ("单位", "各方", "主体", "人员", "机构", "部门", "企业"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            candidate = normalized[: -len(suffix)]
            return candidate if len(candidate) >= 2 else normalized
    return normalized


def _penalty_subject_keys(value: str) -> frozenset[str]:
    has_violation = any(term in value for term in ("违反", "违法", "违规"))
    has_liability_assertion = "法律责任" in value and any(
        term in value for term in ("承担", "追究", "明确", "负有")
    )
    if any(marker in value for marker in ("参建单位", "参建各方")) and (
        has_violation or has_liability_assertion
    ):
        return frozenset(("参建",))
    direct = tuple(_PENALTY_SUBJECT.finditer(value))
    matches = direct or tuple(_PENALTY_ROLE.finditer(value))
    if not matches or not (has_violation or has_liability_assertion):
        return frozenset()
    subject = str(matches[-1].group("subject"))
    return frozenset((_normalize_penalty_subject(subject),))


def _relation_occurrences(value: str, anchors: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    occurrences: list[tuple[str, int]] = []
    occupied: list[tuple[int, int]] = []
    for anchor in sorted(anchors, key=len, reverse=True):
        for index in _find_all(value, anchor):
            end = index + len(anchor)
            if any(start <= index and end <= occupied_end for start, occupied_end in occupied):
                continue
            occurrences.append((anchor, index))
            occupied.append((index, end))
    return tuple(sorted(occurrences, key=lambda item: item[1]))


def _relation_target_terms(
    claim: str,
    *,
    anchor: str,
    anchor_index: int,
) -> tuple[str, ...]:
    anchor_end = anchor_index + len(anchor)
    breaks = tuple(_RELATION_CLAUSE_BREAK.finditer(claim))
    clause_start = max((match.end() for match in breaks if match.end() <= anchor_index), default=0)
    clause_end = min(
        (match.start() for match in breaks if match.start() >= anchor_end),
        default=len(claim),
    )
    after = _clean_for_matching(claim[anchor_end:clause_end])
    before = _clean_for_matching(claim[clause_start:anchor_index])
    cleaned = after if _relation_terms(after) else before
    return _relation_terms(cleaned)


def _strict_relation_target_terms(claim: str, anchors: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = _clean_for_matching(claim)
    for anchor in anchors:
        cleaned = cleaned.replace(anchor, " ")
    return _relation_terms(cleaned)


def _relation_terms(value: str) -> tuple[str, ...]:
    cleaned = _clean_for_matching(value)
    terms: list[str] = [term.lower() for term in _LATIN_TERM.findall(cleaned)]
    for segment in _CJK_SEGMENT.findall(cleaned):
        if 2 <= len(segment) <= 6 and segment not in _GENERIC_TERMS:
            terms.append(segment.lower())
        elif len(segment) > 6:
            terms.extend((segment[:6].lower(), segment[-6:].lower()))
    return tuple(dict.fromkeys(terms))


def _relation_clause(value: str, anchor_index: int, anchor_length: int) -> str:
    anchor_end = anchor_index + anchor_length
    breaks = tuple(_RELATION_CLAUSE_BREAK.finditer(value))
    start = max((match.end() for match in breaks if match.end() <= anchor_index), default=0)
    end = min(
        (match.start() for match in breaks if match.start() >= anchor_end),
        default=len(value),
    )
    return value[start:end]


def _book_title_values(value: str) -> tuple[str, ...]:
    titles: list[str] = []
    stack: list[int] = []
    for index, character in enumerate(value):
        if character == "《":
            stack.append(index)
        elif character == "》" and stack:
            start = stack.pop()
            if title := value[start + 1 : index].strip():
                titles.append(title)
    return tuple(dict.fromkeys(titles))


def _normalize_relation_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _inside_non_penalty_fine(value: str, index: int) -> bool:
    return any(match.start() <= index < match.end() for match in _NON_PENALTY_FINE.finditer(value))


def _find_all(value: str, needle: str) -> tuple[int, ...]:
    positions: list[int] = []
    start = 0
    while True:
        index = value.find(needle, start)
        if index < 0:
            return tuple(positions)
        positions.append(index)
        start = index + max(1, len(needle))


def _inside_document_attribution(value: str, index: int) -> bool:
    return any(
        match.start() <= index < match.end() for match in _DOCUMENT_ATTRIBUTION.finditer(value)
    )


def _relation_occurrence_supported(
    evidence: str,
    *,
    anchor: str,
    anchor_index: int,
    targets: tuple[str, ...],
    radius: int,
    require_all: bool,
) -> bool:
    if not targets:
        return True
    matches = 0
    for target in targets:
        candidates = tuple(
            index for index in _find_all(evidence, target) if abs(index - anchor_index) <= radius
        )
        if not candidates:
            if require_all:
                return False
            continue
        nearest = min(candidates, key=lambda index: abs(index - anchor_index))
        start = min(anchor_index, nearest)
        end = max(anchor_index + len(anchor), nearest + len(target))
        if _RELATION_CLAUSE_BREAK.search(evidence[start:end]) is None:
            matches += 1
        elif require_all:
            return False
    return matches == len(targets) if require_all else matches > 0


def _requires_fail_closed_query(value: str) -> bool:
    lowered = value.lower()
    unresolved_time = (
        bool(_UNRESOLVED_TEMPORAL_REFERENCE.search(lowered))
        and any(term in lowered for term in _TEMPORAL_STATUS_TERMS)
        and not bool(_DATE_EVIDENCE.search(lowered))
    )
    source_conflation = bool(_SOURCE_AUTHORITY_CONFLATION.search(lowered))
    unverified_material = bool(_UNVERIFIED_MATERIAL_REFERENCE.search(lowered))
    contrary_to_source = bool(_CONTRARY_TO_SOURCE_REQUEST.search(lowered))
    return unresolved_time or source_conflation or unverified_material or contrary_to_source


def _scope_supported(claim: str, evidence: str) -> bool:
    target = _scope_target(claim)
    if not target:
        return True
    lowered_evidence = evidence.lower()
    lowered_target = target.lower()
    for index in _find_all(lowered_evidence, lowered_target):
        window = lowered_evidence[max(0, index - 50) : index + len(target) + 50]
        if any(cue in window for cue in _SCOPE_BINDING_CUES):
            return True
    normalized_target = _normalize_scope_text(lowered_target)
    binding_text = "\n".join(_scope_binding_clauses(lowered_evidence))
    normalized_binding = _normalize_scope_text(binding_text)
    if len(normalized_target) >= 2 and normalized_target in normalized_binding:
        return True
    return _scope_title_clause_composition(
        normalized_target,
        lowered_evidence,
        normalized_binding,
    )


def _scope_polarity(value: str, target: str) -> int:
    lowered = value.lower()
    windows = [
        lowered[max(0, index - 40) : index + len(target) + 40]
        for index in _find_all(lowered, target.lower())
    ]
    if not windows:
        return 0
    negative = re.compile(
        r"不(?:在.{0,12})?(?:适用|包括|涵盖|覆盖)|不适用|不包括|不涵盖|"
        r"(?:不|未|没有)(?:直接)?针对|无需|不得"
    )
    if any(negative.search(window) for window in windows):
        return -1
    if any(
        any(
            marker in window
            for marker in ("适用", "面向", "针对", "涵盖", "包括", "覆盖", "必须", "应当")
        )
        for window in windows
    ):
        return 1
    return 0


def _shared_relation(query: str, answer: str, evidence: str) -> bool:
    lowered_query = query.lower()
    lowered_answer = answer.lower()
    lowered_evidence = evidence.lower()
    for _relation, anchors in _RELATION_ANCHOR_GROUPS:
        if (
            any(anchor in lowered_query for anchor in anchors)
            and any(anchor in lowered_answer for anchor in anchors)
            and any(anchor in lowered_evidence for anchor in anchors)
        ):
            return True
    return all(
        any(anchor in value for anchor in _SUPPORT_CONCEPT_TERMS)
        for value in (lowered_query, lowered_answer, lowered_evidence)
    )


def _scope_target(value: str) -> str | None:
    match = _SCOPE_TARGET.search(value)
    if match is not None:
        target = match.group("target")
    else:
        context_match = _SCOPE_CONTEXT_TARGET.search(value)
        if context_match is not None:
            target = context_match.group("target")
        else:
            negative_match = _NEGATIVE_SCOPE_TARGET.search(value)
            if negative_match is not None:
                target = negative_match.group("target")
            else:
                noun_match = _SCOPE_NOUN_TARGET.search(value)
                if noun_match is not None:
                    target = noun_match.group("target")
                else:
                    universal = _UNIVERSAL_SCOPE_TARGET.search(value)
                    if universal is None:
                        return None
                    target = universal.group("covered") or universal.group("required")
    for trailing in _SCOPE_TRAILING_WORDS:
        if target.endswith(trailing) and len(target) > len(trailing) + 1:
            target = target[: -len(trailing)]
    target = target.strip()
    if not target or target in _SCOPE_PLACEHOLDER_TARGETS:
        return None
    return target


def _normalize_scope_text(value: str) -> str:
    normalized = _normalize_relation_text(value).replace("省内", "省")
    for phrase in _SCOPE_FILLER_PHRASES:
        normalized = normalized.replace(phrase, "")
    return normalized


def _scope_binding_clauses(value: str) -> tuple[str, ...]:
    return tuple(
        clause
        for clause in _SCOPE_CLAUSE_BREAK.split(value)
        if any(cue in clause for cue in _SCOPE_BINDING_CUES)
    )


def _scope_title_clause_composition(
    normalized_target: str,
    evidence: str,
    normalized_binding: str,
) -> bool:
    title = next((line.strip() for line in evidence.splitlines() if line.strip()), "")
    normalized_title = _normalize_scope_text(title)
    if len(normalized_target) < 7 or not normalized_binding:
        return False
    if normalized_target in normalized_title:
        return True
    for suffix_length in range(4, min(8, len(normalized_target) - 2) + 1):
        prefix = normalized_target[:-suffix_length]
        suffix = normalized_target[-suffix_length:]
        if prefix in normalized_title and suffix in normalized_binding:
            return True
    return False


def _is_dependent_meta_claim(value: str) -> bool:
    lowered = value.lower().strip()
    if _DEPENDENT_META_CLAIM.search(lowered) is None:
        return False
    if _explicit_values(lowered) or _book_title_values(lowered):
        return False
    return not any(
        anchor in lowered for _relation, anchors in _RELATION_ANCHOR_GROUPS for anchor in anchors
    )


def _identifier_claim_supported(query: str, claim: str, evidence: str) -> bool:
    identifiers = tuple(_POLICY_IDENTIFIER.findall(claim))
    if not identifiers or not any(marker in f"{query}\n{claim}" for marker in ("编号", "文号")):
        return False
    normalized_evidence = _normalize_value(evidence)
    return all(_normalize_value(identifier) in normalized_evidence for identifier in identifiers)


def _progression_claim_supported(claim: str, evidence: str) -> bool:
    if _explicit_values(claim) or _book_title_values(claim):
        return False
    match = _PROGRESSION_SYNTHESIS.search(claim)
    if match is None:
        return False
    if sum(marker in evidence for marker in ("政策目标", "实施对象", "示范项目", "培育对象")) < 2:
        return False
    for name in ("start", "end"):
        endpoint = _normalize_relation_text(match.group(name))
        terms = _weighted_terms(_clean_for_matching(endpoint))
        matched = sum(term in evidence for term in terms)
        paired_anchors = tuple(
            endpoint[index : index + 2] for index in range(0, len(endpoint) - 1, 2)
        )
        lexical_match = _coverage(terms, evidence) >= 0.35 and matched >= 3
        compressed_match = len(paired_anchors) >= 2 and all(
            anchor in evidence for anchor in paired_anchors
        )
        if not (lexical_match or compressed_match):
            return False
    return True


def _explicit_values(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0) for match in _EXPLICIT_VALUE.finditer(value)))


def _query_constraints(value: str) -> tuple[str, ...]:
    constraints: list[str] = []
    for match in _EXPLICIT_VALUE.finditer(value):
        before = value[max(0, match.start() - 8) : match.start()].lower()
        after = value[match.end() : match.end() + 4].lower()
        is_filter_boundary = after.startswith(
            ("之后", "以后", "以来", "之前", "以前")
        ) or before.endswith(("截至", "晚于", "早于", "after", "since", "before"))
        if not is_filter_boundary:
            constraints.append(match.group(0))
    return tuple(dict.fromkeys(constraints))


def _normalize_value(value: str) -> str:
    return re.sub(r"[\s,，]", "", value).lower()


def _searchable_text(hit: RetrievalHit) -> str:
    metadata_values = [
        str(value)
        for value in hit.metadata.values()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool)
    ]
    return "\n".join((hit.title, hit.content, *metadata_values))


def _unique_hits(hits: Sequence[RetrievalHit]) -> tuple[RetrievalHit, ...]:
    unique: list[RetrievalHit] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.chunk_id not in seen:
            unique.append(hit)
            seen.add(hit.chunk_id)
    return tuple(unique)


def _bounded(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(min(1.0, max(0.0, value)), 6)
