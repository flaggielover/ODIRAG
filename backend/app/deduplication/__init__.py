"""Exact and near-duplicate detection."""

from app.deduplication.core import (
    DuplicateCandidate,
    choose_authoritative,
    content_hash,
    hamming_distance,
    is_near_duplicate,
    simhash,
)

__all__ = [
    "DuplicateCandidate",
    "choose_authoritative",
    "content_hash",
    "hamming_distance",
    "is_near_duplicate",
    "simhash",
]
