from __future__ import annotations

import pytest

from app.bm25 import BM25Document, BM25Index
from app.embedding import DeterministicEmbeddingProvider
from app.llm import AnswerResult
from app.providers import ProviderResponseError
from app.rag import GroundingService
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

    async def generate_answer(self, *, query, context, prompt) -> AnswerResult:
        del query, context, prompt
        return self.result


async def _service(result: AnswerResult) -> ChatService:
    content = "软件企业研发投入可以申请资金补助。"
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
                "chunk-1",
                await embedding.embed_query(content),
                "document-1",
                content,
                "研发支持政策",
                "https://example.gov/policy",
                metadata,
            )
        ]
    )
    bm25 = BM25Index()
    bm25.rebuild(
        [
            BM25Document(
                "chunk-1",
                "document-1",
                "研发支持政策",
                content,
                "https://example.gov/policy",
                metadata,
            )
        ]
    )
    return ChatService(
        StubChatRepository(),
        QueryRouter(),
        RetrievalEngine(
            bm25_index=bm25,
            embedding_provider=embedding,
            vector_store=vector_store,
            rerank_provider=NoRerankProvider(),
        ),
        GroundingService(),
        orchestrator=StubLLM(result),
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
