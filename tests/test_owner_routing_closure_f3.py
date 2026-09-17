"""OWNER ROUTING CLOSURE — F3 (unbounded IntentMatcher cold start) tests.

Background (VECTOR_TECHNICAL_KNOWLEDGE/RGC2R_RGD2_COMBINED_REALITY_GATE_
REPORT.md Section 8/36): IntentMatcher._ensure_embeddings_loaded() embedded
499 examples in 103.90s on a fresh process, entirely unbounded — the first
owner /command after every restart pays this cost with no timeout and no
progress signal. Root cause trace (core/city/intent_matcher.py): the
original method set `self._embeddings = []` (non-None) BEFORE the async
embedding loop started, so a second concurrent caller during the ~100s
window would see "already loaded" and could index into a still-partially-
filled list (a genuine correctness bug, not just slowness).

Fix: the embedding bootstrap becomes a single shared background asyncio
Task (`_init_task`), published atomically only once fully built. `match()`
takes an optional `wait_timeout` — None preserves the exact prior blocking
behavior for existing callers (tests, the calibration script, the __main__
demo — none of which should be forced to change), while governor.py's real
/command path passes a small bound so a still-loading matcher is skipped
for THIS request only, without cancelling the shared background task —
later requests reuse the same, by-then-further-along-or-complete task.

These tests use fully mocked, deterministic `_embed()` timing (no real
Ollama round trips) per the skill's "mocks only for deterministic timing
tests" allowance — production behavior is separately verified live in
Section 18 of the mission (fresh-process cold-start trace).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.intent_matcher import IntentMatcher


def _matcher_with_examples(n: int = 3) -> IntentMatcher:
    m = IntentMatcher("data/intent_examples.json")
    m._examples = [{"text": f"example {i}", "district": "research", "task_type": "search_web"} for i in range(n)]
    return m


# ── 1. Matcher already ready — no wait needed ───────────────────────────────

@pytest.mark.asyncio
async def test_matcher_already_ready_returns_immediately():
    m = _matcher_with_examples(2)
    m._embeddings = [[1.0] * 768, [0.0] * 768]
    with patch.object(IntentMatcher, "_embed", new=AsyncMock(return_value=[1.0] * 768)):
        result = await asyncio.wait_for(m.match("anything", wait_timeout=0.01), timeout=2.0)
    assert result is not None


# ── 2/3. Matcher slow initialization -> bounded owner-command fallback ─────

@pytest.mark.asyncio
async def test_slow_init_with_bounded_wait_returns_none_not_hang():
    """A matcher whose embedding load takes far longer than the bounded
    wait_timeout must return None promptly (graceful fallback), not block
    for the full duration."""
    m = _matcher_with_examples(2)

    async def _slow_embed(self, text):
        await asyncio.sleep(5.0)
        return [1.0] * 768

    with patch.object(IntentMatcher, "_embed", new=_slow_embed):
        result = await asyncio.wait_for(m.match("anything", wait_timeout=0.2), timeout=3.0)
    assert result is None


# ── 4/5. Initialization eventually completes; later request uses it ────────

@pytest.mark.asyncio
async def test_background_init_continues_after_bounded_timeout_and_later_request_succeeds():
    """The FIRST call times out (bounded wait), but the SAME background task
    keeps running — once it completes, a SECOND call on the same matcher
    instance must succeed using the now-ready embeddings, without
    re-triggering a second embedding pass."""
    m = _matcher_with_examples(2)
    embed_calls = []

    async def _tracked_embed(self, text):
        embed_calls.append(text)
        await asyncio.sleep(0.15)
        return [1.0] * 768

    with patch.object(IntentMatcher, "_embed", new=_tracked_embed):
        first = await asyncio.wait_for(m.match("query one", wait_timeout=0.01), timeout=3.0)
        assert first is None, "first call must time out (bootstrap not yet done)"
        # allow the background task to finish (2 examples * 0.15s query embed each)
        await asyncio.sleep(0.6)
        second = await asyncio.wait_for(m.match("a totally different query", wait_timeout=2.0), timeout=3.0)
    assert second is not None, "second call must succeed once background init has completed"
    # exactly 2 example embeds (the bootstrap pass) — the query texts
    # ("query one", "a totally different query") are separate, expected,
    # per-match() embed calls, not part of the bootstrap; only bootstrap
    # example texts start with "example "
    example_embeds = [c for c in embed_calls if c.startswith("example ")]
    assert len(example_embeds) == 2, (
        f"expected exactly one bootstrap pass over the 2 examples, got "
        f"{len(example_embeds)} example embeds: {embed_calls!r} — a "
        f"duplicate/second bootstrap indicates the shared-task guard is not "
        f"working"
    )


# ── 6. No duplicate initialization under concurrency ────────────────────────

@pytest.mark.asyncio
async def test_concurrent_callers_share_single_init_task():
    """Two callers hitting a cold matcher concurrently must share exactly
    ONE embedding bootstrap pass, not two independent ones (the original
    bug: a non-None-but-still-empty self._embeddings list made a second
    concurrent caller believe loading was already complete)."""
    m = _matcher_with_examples(3)
    embed_calls = []

    async def _tracked_embed(self, text):
        embed_calls.append(text)
        await asyncio.sleep(0.1)
        return [1.0] * 768

    with patch.object(IntentMatcher, "_embed", new=_tracked_embed):
        results = await asyncio.gather(
            m.match("query a", wait_timeout=5.0),
            m.match("query b", wait_timeout=5.0),
        )
    assert all(r is not None for r in results)
    example_embeds = [c for c in embed_calls if c.startswith("example ")]
    assert len(example_embeds) == 3, (
        f"expected exactly one shared bootstrap pass over the 3 examples "
        f"regardless of concurrent callers, got {len(example_embeds)}: "
        f"{embed_calls!r}"
    )


# ── 7. Initialization failure does not crash /command ───────────────────────

@pytest.mark.asyncio
async def test_embed_failure_during_init_does_not_raise():
    m = _matcher_with_examples(2)

    async def _failing_embed(self, text):
        raise RuntimeError("ollama unreachable")

    with patch.object(IntentMatcher, "_embed", new=_failing_embed):
        result = await asyncio.wait_for(m.match("anything", wait_timeout=2.0), timeout=3.0)
    assert result is None, (
        "an embedding failure during bootstrap must fail gracefully to "
        "None, never raise out of match()"
    )


# ── 8. Backward compatibility: default (no wait_timeout) still blocks ──────

@pytest.mark.asyncio
async def test_default_wait_timeout_is_unbounded_for_existing_callers():
    """Existing callers (tests/test_intent_matcher.py, scripts/
    calibrate_intent_threshold.py, the __main__ demo block) call
    match(text) with no wait_timeout argument at all and expect it to wait
    out a real, possibly-slow embedding pass to completion — this must be
    completely unaffected by the F3 repair. Only governor.py's real
    /command call site opts into a bound."""
    m = _matcher_with_examples(1)

    async def _slow_embed(self, text):
        await asyncio.sleep(0.3)
        return [1.0] * 768

    with patch.object(IntentMatcher, "_embed", new=_slow_embed):
        result = await asyncio.wait_for(m.match("example 0"), timeout=3.0)
    assert result is not None, (
        "match() with no wait_timeout must still wait out the full "
        "embedding bootstrap, exactly like every pre-existing caller "
        "already relies on"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
