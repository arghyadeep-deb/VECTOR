"""Regression test: inject_context() must not drop fitting results just
because an earlier (often higher-ranked) result alone exceeds the token
budget.

The truncation loop used `break` on the first over-budget result instead of
`continue`, so one oversized top result silently discarded every later,
smaller result that would otherwise have fit -- context injection failed
completely instead of partially.
"""

from __future__ import annotations

from vectorcode.src.vc_tools.storage._abc import RetrievalResult
from vectorcode.src.vc_tools.storage.context import ContextConfig, inject_context


class _FixedBackend:
    def __init__(self, results):
        self._results = results

    def retrieve(self, query, top_k=5):
        return self._results[:top_k]


def test_oversized_first_result_does_not_discard_fitting_later_result() -> None:
    oversized = RetrievalResult(content=" ".join(["word"] * 5000), score=0.9, source="big")
    small = RetrievalResult(content="a short relevant snippet", score=0.8, source="small")
    backend = _FixedBackend([oversized, small])
    cfg = ContextConfig(max_context_tokens=100)

    messages = inject_context("query", [], backend, config=cfg)

    assert len(messages) == 1
    assert "small" in messages[0].content
    assert "a short relevant snippet" in messages[0].content
