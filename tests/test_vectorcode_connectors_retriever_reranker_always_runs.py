"""Regression for vectorcode/src/connectors/retriever.py:

TwoStageRetriever.retrieve() only invoked its configured Reranker when
len(candidates) > top_k. A reranker's entire purpose is to improve the
*order* of results, which matters just as much (arguably more) when the
candidate pool is small -- a sparse knowledge base or a narrow query often
returns fewer than top_k matches. In that common case a configured
reranker was silently skipped, always falling back to raw BM25 order.

Fixed: rerank whenever a reranker is configured and candidates is
non-empty, regardless of its size relative to top_k.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.retriever import Reranker, TwoStageRetriever
from vectorcode.src.vc_tools.storage._abc import RetrievalResult


class _RecordingReranker(Reranker):
    def __init__(self) -> None:
        self.called_with: List[RetrievalResult] | None = None

    def rerank(self, query, candidates, *, top_k=10):
        self.called_with = candidates
        # Reverse order so the test can tell reranking actually happened.
        return list(reversed(candidates))[:top_k]


class _FakeStore:
    def __init__(self, results: List[RetrievalResult]) -> None:
        self._results = results

    def retrieve(self, query, *, top_k=5, **filter_kwargs):
        return self._results[:top_k]


def _result(i: int) -> RetrievalResult:
    return RetrievalResult(content=f"doc-{i}", score=1.0, source="test", metadata={})


def test_reranker_runs_even_when_candidates_fewer_than_top_k():
    # Only 2 candidates exist, but top_k=10 -- the exact "sparse knowledge
    # base" case where the old len(candidates) > top_k gate skipped
    # reranking entirely.
    candidates = [_result(1), _result(2)]
    store = _FakeStore(candidates)
    reranker = _RecordingReranker()
    retriever = TwoStageRetriever(store, reranker=reranker, recall_k=10)

    results = retriever.retrieve("query", top_k=10)

    assert reranker.called_with is not None, "reranker must be invoked"
    assert [r.content for r in results] == ["doc-2", "doc-1"]


def test_reranker_runs_when_candidates_equal_top_k():
    candidates = [_result(1), _result(2), _result(3)]
    store = _FakeStore(candidates)
    reranker = _RecordingReranker()
    retriever = TwoStageRetriever(store, reranker=reranker, recall_k=10)

    results = retriever.retrieve("query", top_k=3)

    assert reranker.called_with is not None, "reranker must be invoked"
    assert [r.content for r in results] == ["doc-3", "doc-2", "doc-1"]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
