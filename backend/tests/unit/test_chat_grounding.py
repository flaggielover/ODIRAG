from __future__ import annotations

from decimal import Decimal

import pytest

from app.bm25 import BM25Document, BM25Index
from app.embedding import DeterministicEmbeddingProvider
from app.llm import AnswerResult
from app.providers import ProviderResponseError
from app.rag import EvidenceSufficiencyGate, GroundingService
from app.rerank import NoRerankProvider
from app.retrieval import RetrievalEngine
from app.router import QueryRouter
from app.services.chat import ChatService
from app.vector_store import InMemoryVectorStore, VectorPoint


class StubChatRepository:
    def __init__(self) -> None:
        self.trace = None

    async def count_approved_documents(self, filters) -> int:
        del filters
        return 1

    async def add_trace(self, trace):
        self.trace = trace
        return trace

    async def get_trace(self, trace_id: str):
        if self.trace is not None and self.trace.trace_id == trace_id:
            return self.trace
        return None

    async def commit(self) -> None:
        return None


class StubLLM:
    model_name = "stub-grounded-model"

    def __init__(self, result: AnswerResult) -> None:
        self.result = result
        self.calls = 0
        self.contexts = []

    async def generate_answer(self, *, query, context, prompt) -> AnswerResult:
        del query, prompt
        self.calls += 1
        self.contexts.append(context)
        return self.result


async def _service(
    result: AnswerResult,
    *,
    documents: list[tuple[str, str, str, str]] | None = None,
) -> ChatService:
    documents = documents or [
        (
            "chunk-1",
            "软件企业研发投入可以申请资金补助。",
            "研发支持政策",
            "https://example.gov/policy",
        )
    ]
    metadata = {
        "official_status": "official",
        "source_name": "示例政府",
        "publish_date": "2026-02-01",
        "region": "四川",
    }
    embedding = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    await vector_store.upsert(
        [
            VectorPoint(
                chunk_id,
                await embedding.embed_query(content),
                f"document-{chunk_id}",
                content,
                title,
                source_url,
                metadata,
            )
            for chunk_id, content, title, source_url in documents
        ]
    )
    bm25 = BM25Index()
    bm25.rebuild(
        [
            BM25Document(
                chunk_id,
                f"document-{chunk_id}",
                title,
                content,
                source_url,
                metadata,
            )
            for chunk_id, content, title, source_url in documents
        ]
    )
    llm = StubLLM(result)
    return ChatService(
        StubChatRepository(),
        QueryRouter(),
        RetrievalEngine(
            bm25_index=bm25,
            embedding_provider=embedding,
            vector_store=vector_store,
            rerank_provider=NoRerankProvider(),
        ),
        EvidenceSufficiencyGate(),
        GroundingService(),
        orchestrator=llm,
        prompt="Use only evidence",
    )


@pytest.mark.asyncio
async def test_llm_answer_uses_only_stored_citations_and_urls() -> None:
    service = await _service(
        AnswerResult(
            answer="政策提供研发资金支持，来源 https://example.gov/policy",
            cited_chunk_ids=["chunk-1"],
        )
    )
    answer = await service.answer("软件企业有哪些研发支持措施？")
    assert not answer.refusal
    assert answer.citations[0].chunk_id == "chunk-1"
    assert answer.citations[0].url == "https://example.gov/policy"


@pytest.mark.asyncio
async def test_chat_trace_persists_provider_usage_and_cost() -> None:
    service = await _service(
        AnswerResult(
            answer="政策提供研发资金支持，来源 https://example.gov/policy",
            cited_chunk_ids=["chunk-1"],
            token_usage={"total_tokens": 20},
            cost=Decimal("0.0007"),
        )
    )
    await service.answer("软件企业有哪些研发支持措施？")
    trace = service.repository.trace
    assert trace is not None
    assert trace.token_usage_json == {
        "total_tokens": 20,
        "cost_measurement": "provider_reported",
    }
    assert trace.cost == Decimal("0.0007")


@pytest.mark.asyncio
async def test_llm_answer_rejects_unknown_citation_or_url() -> None:
    invalid_citation = await _service(
        AnswerResult(answer="不受支持的回答", cited_chunk_ids=["missing"])
    )
    with pytest.raises(ProviderResponseError, match="citations"):
        await invalid_citation.answer("软件企业有哪些研发支持措施？")

    invalid_url = await _service(
        AnswerResult(
            answer="来源 https://untrusted.example/policy",
            cited_chunk_ids=["chunk-1"],
        )
    )
    with pytest.raises(ProviderResponseError, match="unknown URL"):
        await invalid_url.answer("软件企业有哪些研发支持措施？")


@pytest.mark.asyncio
async def test_insufficient_gate_refusal_has_no_citations_and_skips_llm() -> None:
    service = await _service(AnswerResult(answer="不应被调用", cited_chunk_ids=["chunk-1"]))

    answer = await service.answer("火星地表是否已经发现活体恐龙？")

    assert answer.refusal
    assert answer.citations == ()
    assert answer.refusal_reasons == ("insufficient_evidence_relevance",)
    assert answer.evidence_sufficiency is not None
    assert not answer.evidence_sufficiency.sufficient
    assert service.orchestrator.calls == 0
    assert service.repository.trace.evidence_decision_json["status"] == "insufficient"


@pytest.mark.asyncio
async def test_numeric_fact_question_does_not_bypass_gate_as_document_count() -> None:
    service = await _service(AnswerResult(answer="不应被调用", cited_chunk_ids=["chunk-1"]))

    answer = await service.answer("APP备案罚款金额是多少？")

    assert answer.query_type.value == "rag"
    assert answer.refusal
    assert answer.refusal_reasons == ("evidence_missing_required_relation",)
    assert answer.citations == ()
    assert service.orchestrator.calls == 0


@pytest.mark.asyncio
async def test_llm_receives_only_gate_supported_hits() -> None:
    service = await _service(
        AnswerResult(answer="研发补助比例为30%。", cited_chunk_ids=["supported"]),
        documents=[
            (
                "supported",
                "软件企业研发补助比例为30%。",
                "研发补助政策",
                "https://example.gov/policy",
            ),
            (
                "unrelated",
                "城市公园开放时间为每日六时。",
                "公园通知",
                "https://example.gov/park",
            ),
        ],
    )

    answer = await service.answer("软件企业研发补助比例具体如何规定？")

    assert not answer.refusal
    assert [item["chunk_id"] for item in service.orchestrator.contexts[0]] == ["supported"]


@pytest.mark.asyncio
async def test_answer_with_value_absent_from_citation_becomes_safe_refusal() -> None:
    service = await _service(
        AnswerResult(answer="软件企业研发补助比例为80%。", cited_chunk_ids=["ratio"]),
        documents=[
            (
                "ratio",
                "软件企业研发补助比例为30%。",
                "研发补助政策",
                "https://example.gov/policy",
            )
        ],
    )

    answer = await service.answer("软件企业研发补助比例具体如何规定？")

    assert answer.refusal
    assert answer.refusal_reasons == ("answer_contains_unsupported_exact_values",)
    assert answer.citations == ()
    assert answer.answer_support_validated is False
    assert service.orchestrator.calls == 1
