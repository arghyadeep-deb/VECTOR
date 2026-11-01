"""Scale gate for optional vector index backends such as TurboVec."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["VectorIndexDecision", "decide_vector_index_backend"]


@dataclass(frozen=True)
class VectorIndexDecision:
    backend: str
    should_enable: bool
    reason: str
    corpus_vectors: int


def decide_vector_index_backend(corpus_vectors: int, configured_backend: str = "nanovectordb") -> VectorIndexDecision:
    if configured_backend == "turbovec":
        if corpus_vectors < 1_000_000:
            return VectorIndexDecision("nanovectordb", False, "corpus below TurboVec benchmark threshold", corpus_vectors)
        return VectorIndexDecision("turbovec", True, "scale threshold reached; benchmark before default flip", corpus_vectors)
    return VectorIndexDecision(configured_backend, configured_backend != "turbovec", "configured backend retained", corpus_vectors)
