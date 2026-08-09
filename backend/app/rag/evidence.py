from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.retrieval import RetrievalHit

_ASPECT_SEPARATOR = re.compile(r"[?？。!！;；\n]+")
_ANSWER_CLAIM_SEPARATOR = re.compile(r"[。！？!?；;\n]+")
_LATIN_TERM = re.compile(r"[a-z][a-z0-9._+-]{1,}", re.IGNORECASE)
_CJK_SEGMENT = re.compile(r"[\u4e00-\u9fff]+")
_EXPLICIT_VALUE = re.compile(
    r"(?:19|20)\d{2}(?:年(?:\d{1,2}月(?:\d{1,2}日)?)?)?"
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
    ("legal_basis", ("法律依据", "法定依据", "依据", "根据")),
    ("support", ("支持", "补助", "资金", "奖励", "优惠", "贷款", "培训", "服务")),
)
_SCOPE_TARGET = re.compile(
    r"(?:是否)?(?:适用于|适用|面向|针对)(?P<target>[A-Za-z0-9._+\-\u4e00-\u9fff]{2,32})"
)
_UNIVERSAL_SCOPE_TARGET = re.compile(
    r"(?:涵盖|包括|覆盖)(?:所有|全部)?(?P<covered>微信小程序|小程序)"
    r"|(?:所有|全部)(?P<required>微信小程序|小程序).{0,8}(?:必须|应当|需要|均应|都要)"
)
_RELATION_CLAUSE_BREAK = re.compile(r"[，,。；;\n]|同时|但是|但|然而")
_SCOPE_TRAILING_WORDS = ("范围", "对象", "情形", "企业", "单位", "主体", "吗", "呢")


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
        relation_required = any(
            any(anchor in answer.lower() for anchor in anchors)
            for _relation, anchors in _RELATION_ANCHOR_GROUPS
        )
        relation_supported = any(
            _relation_failure(answer, _searchable_text(hit).lower()) is None for hit in cited_hits
        )
        relation_failure = _relation_failure(answer, evidence_text)
        if relation_required and (not relation_supported or relation_failure is not None):
            return EvidenceSufficiencyDecision(
                False,
                0.0,
                "answer_contains_unsupported_relation",
                (),
                (relation_failure or "relation",),
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
            if (
                answer_polarity != 0
                and evidence_polarities
                and answer_polarity not in evidence_polarities
            ):
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
            claim_terms = _weighted_terms(_clean_for_matching(claim))
            if not claim_terms:
                continue
            claim_overlap = _coverage(claim_terms, evidence_text)
            claim_matches = sum(
                1 for term in claim_terms if len(term) >= 2 and term in evidence_text
            )
            if claim_overlap < self.minimum_answer_overlap and not (
                _shared_relation(query, claim, evidence_text) and claim_matches >= 1
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
        relation_required = any(
            any(anchor in aspect.lower() for anchor in anchors)
            for _relation, anchors in _RELATION_ANCHOR_GROUPS
        )
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
    return tuple(
        cleaned for part in _ASPECT_SEPARATOR.split(query) if (cleaned := _clean_display(part))
    )


def _answer_claims(answer: str) -> tuple[str, ...]:
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
    date_missing = (
        any(term in lowered for term in ("什么时候", "何时", "时间", "日期"))
        and _DATE_EVIDENCE.search(evidence) is None
    )
    percentage_missing = (
        any(term in lowered for term in ("比例", "百分比", "占比", "%", "％"))
        and _PERCENT_EVIDENCE.search(evidence) is None
    )
    money_missing = (
        any(term in lowered for term in ("金额", "罚款", "补助资金", "资金额度"))
        and _MONEY_EVIDENCE.search(evidence) is None
    )
    quantity_missing = (
        any(term in lowered for term in ("多少", "数量", "几家", "几个"))
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
        )
    )


def _relation_failure(claim: str, evidence: str) -> str | None:
    lowered_claim = claim.lower()
    lowered_evidence = evidence.lower()
    for relation, anchors in _RELATION_ANCHOR_GROUPS:
        if not any(anchor in lowered_claim for anchor in anchors):
            continue
        if relation == "support":
            supported = any(anchor in lowered_evidence for anchor in anchors)
        else:
            targets = _relation_target_terms(claim, anchors)
            supported = any(
                _relation_occurrence_supported(
                    lowered_evidence,
                    anchor=anchor,
                    anchor_index=index,
                    targets=targets,
                )
                for anchor in anchors
                for index in _find_all(lowered_evidence, anchor)
            )
        if not supported:
            return relation
    return None


def _relation_target_terms(claim: str, anchors: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = _clean_for_matching(claim)
    for anchor in anchors:
        cleaned = cleaned.replace(anchor, " ")
    terms: list[str] = [term.lower() for term in _LATIN_TERM.findall(cleaned)]
    for segment in _CJK_SEGMENT.findall(cleaned):
        if 2 <= len(segment) <= 6 and segment not in _GENERIC_TERMS:
            terms.append(segment.lower())
        elif len(segment) > 6:
            terms.extend((segment[:6].lower(), segment[-6:].lower()))
    return tuple(dict.fromkeys(terms))


def _find_all(value: str, needle: str) -> tuple[int, ...]:
    positions: list[int] = []
    start = 0
    while True:
        index = value.find(needle, start)
        if index < 0:
            return tuple(positions)
        positions.append(index)
        start = index + max(1, len(needle))


def _relation_occurrence_supported(
    evidence: str,
    *,
    anchor: str,
    anchor_index: int,
    targets: tuple[str, ...],
) -> bool:
    if not targets:
        return True
    radius = 16
    positions: list[tuple[int, int]] = [(anchor_index, anchor_index + len(anchor))]
    for target in targets:
        candidates = tuple(
            index for index in _find_all(evidence, target) if abs(index - anchor_index) <= radius
        )
        if not candidates:
            return False
        nearest = min(candidates, key=lambda index: abs(index - anchor_index))
        positions.append((nearest, nearest + len(target)))
    start = min(item[0] for item in positions)
    end = max(item[1] for item in positions)
    return _RELATION_CLAUSE_BREAK.search(evidence[start:end]) is None


def _scope_supported(claim: str, evidence: str) -> bool:
    target = _scope_target(claim)
    if not target:
        return True
    lowered_evidence = evidence.lower()
    lowered_target = target.lower()
    for index in _find_all(lowered_evidence, lowered_target):
        window = lowered_evidence[max(0, index - 50) : index + len(target) + 50]
        if any(
            verb in window
            for verb in ("适用", "面向", "针对", "涵盖", "包括", "覆盖", "必须", "应当")
        ):
            return True
    return False


def _scope_polarity(value: str, target: str) -> int:
    lowered = value.lower()
    windows = [
        lowered[max(0, index - 40) : index + len(target) + 40]
        for index in _find_all(lowered, target.lower())
    ]
    if not windows:
        return 0
    negative = re.compile(r"不(?:在.{0,12})?(?:适用|包括|涵盖|覆盖)|不适用|不包括|不涵盖|无需|不得")
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
    return False


def _scope_target(value: str) -> str | None:
    match = _SCOPE_TARGET.search(value)
    if match is not None:
        target = match.group("target")
    else:
        universal = _UNIVERSAL_SCOPE_TARGET.search(value)
        if universal is None:
            return None
        target = universal.group("covered") or universal.group("required")
    for trailing in _SCOPE_TRAILING_WORDS:
        if target.endswith(trailing) and len(target) > len(trailing) + 1:
            target = target[: -len(trailing)]
    return target.strip() or None


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
