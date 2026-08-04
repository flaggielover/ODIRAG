from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date


def content_hash(text: str) -> str:
    canonical = re.sub(r"\s+", "", text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def simhash(text: str, *, bits: int = 64) -> int:
    if bits <= 0 or bits > 256:
        raise ValueError("bits must be between 1 and 256")
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text.lower())
    if not tokens:
        return 0
    weights = [0] * bits
    for token in tokens:
        digest = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest(), "big")
        for index in range(bits):
            weights[index] += 1 if digest & (1 << index) else -1
    result = 0
    for index, weight in enumerate(weights):
        if weight >= 0:
            result |= 1 << index
    return result


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def is_near_duplicate(left: str, right: str, *, max_distance: int = 3) -> bool:
    return hamming_distance(simhash(left), simhash(right)) <= max_distance


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    document_id: str
    official: bool
    source_priority: int
    publish_date: date | None
    word_count: int


def choose_authoritative(candidates: list[DuplicateCandidate]) -> DuplicateCandidate:
    if not candidates:
        raise ValueError("at least one duplicate candidate is required")
    return max(
        candidates,
        key=lambda item: (
            item.official,
            item.source_priority,
            item.publish_date or date.min,
            item.word_count,
            item.document_id,
        ),
    )
