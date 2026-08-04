"""Provider contracts and helpers for autonomous source-pool expansion."""

from app.source_discovery.providers import (
    BraveCandidateDiscoveryProvider,
    CandidateDiscoveryProvider,
    CandidateHit,
    build_candidate_provider,
)

__all__ = [
    "BraveCandidateDiscoveryProvider",
    "CandidateDiscoveryProvider",
    "CandidateHit",
    "build_candidate_provider",
]
