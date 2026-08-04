from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from app.retrieval.models import RetrievalHit


@dataclass(frozen=True, slots=True)
class BM25Document:
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_url: str
    metadata: dict[str, Any]


class BM25Index:
    def __init__(self) -> None:
        self._documents: list[BM25Document] = []
        self._tokenized_documents: list[list[str]] = []
        self._engine: BM25Okapi | None = None

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def rebuild(self, documents: list[BM25Document]) -> None:
        self._documents = list(documents)
        self._tokenized_documents = [
            _tokenize(f"{document.title} {document.content}") for document in documents
        ]
        self._engine = BM25Okapi(self._tokenized_documents) if self._tokenized_documents else None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "documents": [
                {
                    "chunk_id": document.chunk_id,
                    "document_id": document.document_id,
                    "title": document.title,
                    "content": document.content,
                    "source_url": document.source_url,
                    "metadata": document.metadata,
                }
                for document in self._documents
            ],
        }
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported BM25 snapshot schema")
        raw_documents = payload.get("documents")
        if not isinstance(raw_documents, list):
            raise ValueError("BM25 snapshot documents must be a list")
        documents = []
        for item in raw_documents:
            if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
                raise ValueError("invalid BM25 snapshot document")
            documents.append(
                BM25Document(
                    chunk_id=str(item["chunk_id"]),
                    document_id=str(item["document_id"]),
                    title=str(item["title"]),
                    content=str(item["content"]),
                    source_url=str(item["source_url"]),
                    metadata=dict(item["metadata"]),
                )
            )
        index = cls()
        index.rebuild(documents)
        return index

    def search(
        self, query: str, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[RetrievalHit]:
        if self._engine is None or top_k <= 0:
            return []
        query_tokens = _tokenize(query)
        query_token_set = set(query_tokens)
        scores = self._engine.get_scores(query_tokens)
        candidates = []
        for index, score in enumerate(scores):
            document = self._documents[index]
            if query_token_set.intersection(self._tokenized_documents[index]) and _matches(
                document.metadata, filters or {}
            ):
                candidates.append((float(score), document))
        candidates.sort(key=lambda item: (-item[0], item[1].chunk_id))
        normalized_scores = _normalize([score for score, _document in candidates])
        return [
            RetrievalHit(
                document.chunk_id,
                document.document_id,
                document.content,
                document.title,
                document.source_url,
                normalized_scores[rank - 1],
                rank=rank,
                source="bm25",
                metadata=document.metadata,
            )
            for rank, (_score, document) in enumerate(candidates[:top_k], start=1)
        ]


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text)]


def _matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key.endswith("_gte"):
            if metadata.get(key[:-4]) is None or str(metadata[key[:-4]]) < str(expected):
                return False
        elif key.endswith("_lte"):
            if metadata.get(key[:-4]) is None or str(metadata[key[:-4]]) > str(expected):
                return False
        elif metadata.get(key) != expected:
            return False
    return True


def _normalize(scores: list[float]) -> list[float]:
    if not scores:
        return []
    minimum = min(scores)
    maximum = max(scores)
    if maximum == minimum:
        return [1.0] * len(scores)
    return [(score - minimum) / (maximum - minimum) for score in scores]
