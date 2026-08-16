from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

NO_FAILURE = "NO_FAILURE"


def build_failure_analysis(
    evaluation: Mapping[str, Any],
    gold_dataset: Mapping[str, Any],
    traces: Mapping[str, Mapping[str, Any]],
    lineage: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Join one evaluation report to persisted stage traces and Gold provenance."""

    gold_by_id = {str(item["question_id"]): item for item in gold_dataset.get("questions", [])}
    cases = [
        _case_analysis(item, gold_by_id.get(str(item.get("question_id")), {}), traces)
        for item in evaluation.get("questions", [])
    ]
    distribution = Counter(str(item["root_cause_category"]) for item in cases)
    failures = [
        item for item in cases if item["root_cause_category"] not in {NO_FAILURE, "CORRECT_REFUSAL"}
    ]
    return {
        "schema_version": 2,
        "source_run": {
            "run_name": evaluation.get("run_name"),
            "started_at": evaluation.get("started_at"),
            "finished_at": evaluation.get("finished_at"),
            "evaluation_run_id": _mapping(evaluation.get("metadata")).get("evaluation_run_id"),
        },
        "question_count": len(cases),
        "metric_contract": _metric_contract(),
        "trace_limitations": [
            (
                "Historical traces without selected_context_chunk_ids use evidence-gate "
                "supported_chunk_ids as a context proxy."
            ),
            (
                "Traces generated before answer_validation_decision was introduced do not "
                "preserve the final validator confidence or unsupported aspects."
            ),
        ],
        "refusal_confusion_matrix": _refusal_metrics(cases),
        "retention_funnel": _retention_funnel(cases),
        "root_cause_distribution": [
            {
                "category": category,
                "count": count,
                "percent_of_all": _ratio(count, len(cases)),
                "percent_of_failures": (
                    _ratio(count, len(failures))
                    if category not in {NO_FAILURE, "CORRECT_REFUSAL"}
                    else 0.0
                ),
            }
            for category, count in sorted(
                distribution.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "citation_audit": _citation_audit(cases, lineage),
        "cases": cases,
    }


def _case_analysis(
    case: Mapping[str, Any],
    gold: Mapping[str, Any],
    traces: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    trace_id = str(_mapping(case.get("retrieval_trace")).get("trace_id") or "")
    trace = traces.get(trace_id, {})
    evidence = _mapping(trace.get("evidence_decision"))
    answer_validation = _mapping(evidence.get("answer_validation_decision"))
    rerank_metadata = _mapping(trace.get("rerank_metadata"))
    expected_chunks = _strings(case.get("expected_chunk_ids"))
    expected_documents = _strings(case.get("expected_document_ids"))
    fusion_chunks = _hit_ids(trace.get("fusion_results"))
    reported_chunks = _strings(case.get("retrieved_chunk_ids"))
    retrieval_chunks = fusion_chunks or reported_chunks
    reranked_chunks = _hit_ids(trace.get("rerank_results"))
    final_context_chunks = _hit_ids(trace.get("final_context")) or reported_chunks
    effective_rerank_chunks = (
        reranked_chunks if rerank_metadata.get("applied") is True else final_context_chunks
    )
    selected_chunks = _strings(
        evidence.get("selected_context_chunk_ids") or evidence.get("supported_chunk_ids")
    )
    selected_context_source = (
        "persisted_llm_context"
        if "selected_context_chunk_ids" in evidence
        else "evidence_supported_ids_proxy"
    )
    generated_cited_chunks = _strings(evidence.get("generated_cited_chunk_ids"))
    cited_chunks = _strings(case.get("cited_chunk_ids"))
    cited_documents = _strings(case.get("cited_document_ids"))
    should_refuse = bool(case.get("should_refuse"))
    refused = bool(case.get("refused"))
    refusal_reasons = _strings(_mapping(case.get("chat_metadata")).get("refusal_reasons"))
    metrics = _mapping(case.get("metrics"))
    retrieval_any = _overlap(expected_chunks, retrieval_chunks)
    retrieval_complete = _contains_all(retrieval_chunks, expected_chunks)
    final_any = _overlap(expected_chunks, final_context_chunks)
    final_complete = _contains_all(final_context_chunks, expected_chunks)
    selected_any = _overlap(expected_chunks, selected_chunks)
    selected_complete = _contains_all(selected_chunks, expected_chunks)
    metric_failures = _metric_failures(
        should_refuse=should_refuse,
        refused=refused,
        metrics=metrics,
        evidence=evidence,
        expected_chunks=expected_chunks,
        cited_chunks=cited_chunks,
    )
    if case.get("error"):
        root_cause, detail = "EVALUATION_ERROR", str(case.get("error"))
    else:
        root_cause, detail = _root_cause(
            should_refuse=should_refuse,
            refused=refused,
            refusal_reasons=refusal_reasons,
            expected_chunks=expected_chunks,
            expected_documents=expected_documents,
            cited_chunks=cited_chunks,
            cited_documents=cited_documents,
            retrieval_chunks=retrieval_chunks,
            reranked_chunks=effective_rerank_chunks,
            final_context_chunks=final_context_chunks,
            selected_chunks=selected_chunks,
            evidence=evidence,
            rerank_applied=rerank_metadata.get("applied") is True,
            answer_present=bool(str(case.get("answer") or "").strip()) and not refused,
        )
    return {
        "id": case.get("question_id"),
        "category": case.get("category"),
        "question": case.get("question"),
        "should_refuse": should_refuse,
        "expected_answer": gold.get("expected_answer"),
        "expected_document_ids": expected_documents,
        "expected_chunk_ids": expected_chunks,
        "retrieval_top5": retrieval_chunks[:5],
        "retrieval_top10": retrieval_chunks[:10],
        "reranked_chunks": reranked_chunks,
        "effective_post_rerank_chunks": effective_rerank_chunks,
        "final_context_chunks": final_context_chunks,
        "final_retrieval_chunks": final_context_chunks,
        "selected_evidence_chunks": selected_chunks,
        "selected_context_source": selected_context_source,
        "final_cited_chunk_ids": cited_chunks,
        "generated_cited_chunk_ids_before_validation": generated_cited_chunks,
        "generated_answer_before_validation": evidence.get("generated_answer"),
        "final_cited_document_ids": cited_documents,
        "refusal": refused,
        "refusal_reason": refusal_reasons,
        "evidence_gate_result": evidence,
        "answer_validation_result": answer_validation,
        "relation_validation_result": _relation_result(
            evidence, answer_validation, refusal_reasons
        ),
        "citation_validation_result": _citation_result(
            refused, refusal_reasons, cited_chunks, evidence
        ),
        "answer_present": bool(str(case.get("answer") or "").strip()) and not refused,
        "answer_correctness_status": _answer_status(
            should_refuse, refused, metrics, case.get("error")
        ),
        "retrieval_hit": retrieval_any,
        "retrieval_complete": retrieval_complete,
        "expected_evidence_after_rerank": _overlap(expected_chunks, effective_rerank_chunks),
        "expected_evidence_after_rerank_complete": _contains_all(
            effective_rerank_chunks, expected_chunks
        ),
        "expected_evidence_in_final_context": final_any,
        "expected_evidence_in_final_context_complete": final_complete,
        "expected_evidence_in_context": selected_any,
        "expected_evidence_in_context_complete": selected_complete,
        "metric_failures": metric_failures,
        "root_cause_category": root_cause,
        "root_cause_detail": detail,
        "trace_id": trace_id or None,
        "rerank_metadata": rerank_metadata,
        "stage_timings_ms": _mapping(trace.get("stage_timings")),
    }


def _root_cause(
    *,
    should_refuse: bool,
    refused: bool,
    refusal_reasons: Sequence[str],
    expected_chunks: Sequence[str],
    expected_documents: Sequence[str],
    cited_chunks: Sequence[str],
    cited_documents: Sequence[str],
    retrieval_chunks: Sequence[str],
    reranked_chunks: Sequence[str],
    final_context_chunks: Sequence[str],
    selected_chunks: Sequence[str],
    evidence: Mapping[str, Any],
    rerank_applied: bool,
    answer_present: bool,
) -> tuple[str, str]:
    if should_refuse:
        if refused:
            return "CORRECT_REFUSAL", "Gold refusal was preserved with no emitted answer."
        return "OTHER", "Gold refusal case emitted an answer."
    if not _overlap(expected_chunks, retrieval_chunks):
        return "RETRIEVAL_MISS", "No expected Gold chunk was present before rerank."
    if (
        rerank_applied
        and _overlap(expected_chunks, retrieval_chunks)
        and not _overlap(expected_chunks, reranked_chunks)
    ):
        return (
            "RERANK_DROPPED_REQUIRED_EVIDENCE",
            "Expected Gold evidence was present before rerank and absent afterward.",
        )
    if not _overlap(expected_chunks, final_context_chunks):
        return (
            "CONTEXT_PACKING_DROPPED_EVIDENCE",
            "Expected Gold evidence was absent from the final retrieval context.",
        )
    if evidence.get("sufficient") is False:
        return (
            "EVIDENCE_GATE_FALSE_NEGATIVE",
            str(evidence.get("reason") or "evidence gate rejected a Gold-supported case"),
        )
    if refused:
        if any(
            reason.startswith("answer_") or reason == "citations_do_not_cover_query"
            for reason in refusal_reasons
        ):
            return (
                "POST_ANSWER_VALIDATION_UNRESOLVED",
                "|".join(refusal_reasons) or "post-answer validation rejected the generated output",
            )
        return "INCORRECT_REFUSAL", "Gold-supported case was refused after evidence passed."
    if not answer_present:
        return "INCORRECT_REFUSAL", "Gold-supported case has no answer payload."
    if cited_chunks and not _overlap(expected_chunks, cited_chunks):
        if _overlap(expected_documents, cited_documents):
            return (
                "CITATION_EXPECTATION_MISMATCH",
                "Emitted citations passed safety validation and cite an expected document, "
                "but do not overlap the exact Gold seed chunks.",
            )
        return "CITATION_MAPPING_ERROR", "Emitted citations miss Gold chunks and documents."
    if expected_chunks and not _contains_all(cited_chunks, expected_chunks):
        return (
            "MULTI_CHUNK_CITATION_INCOMPLETE",
            "Only part of the exact Gold chunk set was cited.",
        )
    if selected_chunks and not cited_chunks:
        return "CITATION_MAPPING_ERROR", "Selected evidence produced no final citation."
    return NO_FAILURE, "No failure under the current exact Gold contract."


def _metric_failures(
    *,
    should_refuse: bool,
    refused: bool,
    metrics: Mapping[str, Any],
    evidence: Mapping[str, Any],
    expected_chunks: Sequence[str],
    cited_chunks: Sequence[str],
) -> list[str]:
    failures: list[str] = []
    if bool(metrics.get("chunk_hit") == 0.0) and expected_chunks:
        failures.append("retrieval")
    if bool(metrics.get("refusal_correct") == 0.0):
        failures.append("refusal")
    if evidence.get("sufficient") is not None and bool(evidence.get("sufficient")) == should_refuse:
        failures.append("evidence_sufficiency")
    if not (should_refuse and refused):
        if float(metrics.get("citation_accuracy") or 0.0) < 1.0:
            failures.append("exact_citation_precision")
        if float(metrics.get("citation_completeness") or 0.0) < 1.0:
            failures.append("exact_citation_recall")
    if not refused and not cited_chunks:
        failures.append("citation_missing")
    return failures


def _refusal_metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    assessed = [item for item in cases if item["root_cause_category"] != "EVALUATION_ERROR"]
    gold_answer_pred_answer = sum(
        not item["should_refuse"] and not item["refusal"] for item in assessed
    )
    gold_answer_pred_refuse = sum(
        not item["should_refuse"] and item["refusal"] for item in assessed
    )
    gold_refuse_pred_answer = sum(
        item["should_refuse"] and not item["refusal"] for item in assessed
    )
    gold_refuse_pred_refuse = sum(item["should_refuse"] and item["refusal"] for item in assessed)
    predicted_refusals = gold_answer_pred_refuse + gold_refuse_pred_refuse
    gold_refusals = gold_refuse_pred_answer + gold_refuse_pred_refuse
    gold_answers = gold_answer_pred_answer + gold_answer_pred_refuse
    correct = gold_answer_pred_answer + gold_refuse_pred_refuse
    return {
        "rows": {
            "gold_answer": {
                "pred_answer": gold_answer_pred_answer,
                "pred_refuse": gold_answer_pred_refuse,
            },
            "gold_refuse": {
                "pred_answer": gold_refuse_pred_answer,
                "pred_refuse": gold_refuse_pred_refuse,
            },
        },
        "refusal_precision": _ratio(gold_refuse_pred_refuse, predicted_refusals),
        "refusal_recall": _ratio(gold_refuse_pred_refuse, gold_refusals),
        "refusal_accuracy": _ratio(correct, len(assessed)),
        "supported_answer_recall": _ratio(gold_answer_pred_answer, gold_answers),
        "evaluation_error_count": len(cases) - len(assessed),
        "quality_assessed_questions": len(assessed),
    }


def _retention_funnel(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    supported = [item for item in cases if not item["should_refuse"]]
    stages = (
        ("gold_evidence_present_in_top10", "retrieval_hit", "retrieval_complete"),
        (
            "present_after_rerank",
            "expected_evidence_after_rerank",
            "expected_evidence_after_rerank_complete",
        ),
        (
            "present_in_final_retrieval",
            "expected_evidence_in_final_context",
            "expected_evidence_in_final_context_complete",
        ),
        (
            "present_after_context_packing",
            "expected_evidence_in_context",
            "expected_evidence_in_context_complete",
        ),
    )
    result: dict[str, Any] = {"supported_case_count": len(supported)}
    for name, any_key, complete_key in stages:
        any_count = sum(bool(item[any_key]) for item in supported)
        complete_count = sum(bool(item[complete_key]) for item in supported)
        result[name] = {
            "any_count": any_count,
            "any_rate": _ratio(any_count, len(supported)),
            "complete_count": complete_count,
            "complete_rate": _ratio(complete_count, len(supported)),
        }
    cited_any = sum(
        _overlap(item["expected_chunk_ids"], item["final_cited_chunk_ids"]) for item in supported
    )
    cited_complete = sum(
        _contains_all(item["final_cited_chunk_ids"], item["expected_chunk_ids"])
        for item in supported
    )
    result["cited"] = {
        "any_count": cited_any,
        "any_rate": _ratio(cited_any, len(supported)),
        "complete_count": cited_complete,
        "complete_rate": _ratio(cited_complete, len(supported)),
    }
    return result


def _citation_audit(
    cases: Sequence[Mapping[str, Any]], lineage: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    answered = [item for item in cases if item["answer_present"]]
    failures = [
        item
        for item in answered
        if "exact_citation_precision" in item["metric_failures"]
        or "exact_citation_recall" in item["metric_failures"]
    ][:10]
    full_successes = [
        item
        for item in answered
        if "exact_citation_precision" not in item["metric_failures"]
        and "exact_citation_recall" not in item["metric_failures"]
    ]
    overlap_successes = [
        item
        for item in answered
        if _overlap(item["expected_chunk_ids"], item["final_cited_chunk_ids"])
        and item not in full_successes
        and item not in failures
    ]
    successes = [*full_successes, *overlap_successes][:5]
    return {
        "selection": (
            "first 10 emitted-citation exact failures plus all full exact successes and "
            "then nonzero exact-overlap successes, capped at 5"
        ),
        "failure_count": len(failures),
        "success_count": len(successes),
        "cases": [_citation_audit_case(item, "failure", lineage) for item in failures]
        + [_citation_audit_case(item, "success", lineage) for item in successes],
    }


def _citation_audit_case(
    case: Mapping[str, Any],
    outcome: str,
    lineage: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    expected = set(_strings(case.get("expected_chunk_ids")))
    expected_documents = set(_strings(case.get("expected_document_ids")))
    cited = _strings(case.get("final_cited_chunk_ids"))
    chunks = []
    for chunk_id in cited:
        item = dict(lineage.get(chunk_id, {}))
        document_id = str(item.get("document_id") or "")
        item.update(
            {
                "chunk_id": chunk_id,
                "exact_gold_chunk": chunk_id in expected,
                "expected_document": document_id in expected_documents,
                "adjacent_to_gold_seed": _adjacent_to_expected(item, expected, lineage),
            }
        )
        chunks.append(item)
    evidence = _mapping(case.get("evidence_gate_result"))
    return {
        "outcome": outcome,
        "id": case.get("id"),
        "category": case.get("category"),
        "question": case.get("question"),
        "expected_chunk_ids": list(expected),
        "cited_chunks": chunks,
        "answer_support_validated": evidence.get("answer_support_validated"),
        "semantic_review_status": "TRACEABLE_REVIEW_REQUIRED",
    }


def _adjacent_to_expected(
    cited: Mapping[str, Any],
    expected: set[str],
    lineage: Mapping[str, Mapping[str, Any]],
) -> bool:
    document_id = cited.get("document_id")
    chunk_index = cited.get("chunk_index")
    if not isinstance(chunk_index, int):
        return False
    return any(
        expected_item.get("document_id") == document_id
        and isinstance(expected_item.get("chunk_index"), int)
        and abs(chunk_index - int(expected_item["chunk_index"])) == 1
        for chunk_id in expected
        if (expected_item := lineage.get(chunk_id)) is not None
    )


def _relation_result(
    evidence: Mapping[str, Any],
    answer_validation: Mapping[str, Any],
    refusal_reasons: Sequence[str],
) -> dict[str, Any]:
    if evidence.get("reason") == "evidence_missing_required_relation":
        return {
            "stage": "pre_answer_evidence_gate",
            "status": "rejected",
            "reason": evidence.get("reason"),
        }
    if "answer_contains_unsupported_relation" in refusal_reasons:
        return {
            "stage": "post_answer_validation",
            "status": "rejected",
            "reason": answer_validation.get("reason") or "answer_contains_unsupported_relation",
            "confidence": answer_validation.get("confidence"),
            "unsupported_aspects": _strings(answer_validation.get("unsupported_aspects")),
        }
    return {"stage": "not_triggered", "status": "passed_or_not_applicable", "reason": None}


def _citation_result(
    refused: bool,
    refusal_reasons: Sequence[str],
    cited_chunks: Sequence[str],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if "citations_do_not_cover_query" in refusal_reasons:
        return {"status": "rejected", "reason": "citations_do_not_cover_query"}
    if refused and evidence.get("answer_support_validated") is None:
        return {"status": "not_run", "reason": "answer_generation_not_reached"}
    if refused:
        return {
            "status": "rejected",
            "reason": (refusal_reasons[0] if refusal_reasons else "refusal"),
        }
    return {
        "status": "passed" if cited_chunks else "failed",
        "reason": None if cited_chunks else "no_citations",
    }


def _answer_status(
    should_refuse: bool,
    refused: bool,
    metrics: Mapping[str, Any],
    error: Any,
) -> str:
    if error:
        return "EVALUATION_ERROR"
    if should_refuse:
        return "CORRECT_REFUSAL" if refused else "UNSAFE_ANSWER"
    if refused:
        return "INCORRECT_REFUSAL"
    if float(metrics.get("answer_point_coverage") or 0.0) == 1.0:
        return "EXACT_GOLD_ANSWER_POINT_MATCH"
    return "ANSWER_ACCEPTED_CORRECTNESS_NOT_ESTABLISHED_BY_CURRENT_GOLD_CONTRACT"


def _metric_contract() -> dict[str, str]:
    return {
        "citation_precision": (
            "Per-question exact chunk-set precision, macro-averaged over every case except "
            "correct Gold refusals; supported false refusals therefore score zero."
        ),
        "citation_recall": (
            "Per-question exact expected-chunk-set recall over the same denominator; Gold "
            "expected chunks are seed provenance, not marked exhaustive."
        ),
        "refusal_accuracy": "Mean of predicted_refusal == should_refuse over all cases.",
        "evidence_sufficiency_accuracy": (
            "Post-processed comparison of the pre-answer evidence decision to "
            "not should_refuse; later safety refusals are outside this decision."
        ),
        "multi_chunk": (
            "No category-specific threshold exists; full exact recall requires every expected "
            "chunk and extra citations reduce exact precision."
        ),
    }


def _hit_ids(value: Any) -> list[str]:
    return [
        str(item["chunk_id"])
        for item in value or []
        if isinstance(item, Mapping) and item.get("chunk_id")
    ]


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value if item is not None and str(item)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _overlap(expected: Sequence[str], actual: Sequence[str]) -> bool:
    return bool(set(expected) & set(actual)) if expected else True


def _contains_all(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return set(expected) <= set(actual) if expected else True


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
