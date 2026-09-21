"""PRE-RG-D2 FINAL CLOSURE — Target C (non-blocking IntentMatcher prewarm).

Background (V1_TRUST_ACTION_IDENTITY_PERMISSION_CLOSURE_REPORT.md §14 #3):
the owner-routing F3 repair moved the ~100 s embedding bootstrap into a
shared background asyncio.Task — but `IntentMatcher._embed()` still called
the SYNCHRONOUS `ollama.Client(...).embeddings()` directly inside
`async def`. A coroutine that makes a blocking call never yields, so the
"background" task froze the whole event loop: uvicorn only began listening
after all 499 embeddings finished (live: 0 HTTP lines between prewarm start
and "Uvicorn running"; listener ≈2 min after process start). The F3 unit
tests missed it because they mocked `_embed` with `await asyncio.sleep`,
which yields — they never exercised a real blocking call.

These tests use a REAL synchronous blocker (`time.sleep` inside a fake
`ollama.Client.embeddings`), which is exactly the failure shape, plus a
heartbeat coroutine that measures how long the event loop is starved.
"""
from __future__ import annotations

import asyncio
import random
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.intent_matcher import IntentMatcher

BLOCK_SECS = 0.2


def _vec(text: str) -> list[float]:
    rnd = random.Random(text)
    return [rnd.random() for _ in range(768)]


def _fake_ollama(*, block=BLOCK_SECS, calls=None, fail=False):
    class _Client:
        def __init__(self, *a, **k):
            pass

        def embeddings(self, model=None, prompt=""):
            if calls is not None:
                calls.append(prompt)
            time.sleep(block)  # a REAL synchronous block
            if fail:
                raise RuntimeError("ollama unreachable")
            return {"embedding": _vec(prompt)}
    return _Client


def _matcher(n=3) -> IntentMatcher:
    m = IntentMatcher("data/intent_examples.json")
    m._examples = [{"text": f"example {i}", "district": "research", "task_type": "search_web"} for i in range(n)]
    return m


async def _max_loop_gap(coro_factory) -> float:
    """Run `coro_factory()` while a 10 ms heartbeat measures the longest
    interval the event loop was unable to run other coroutines."""
    loop = asyncio.get_running_loop()
    gaps: list[float] = []
    stop = asyncio.Event()

    async def _heartbeat():
        last = loop.time()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = loop.time()
            gaps.append(now - last)
            last = now

    hb = asyncio.create_task(_heartbeat())
    await asyncio.sleep(0.03)
    try:
        await coro_factory()
    finally:
        stop.set()
        await hb
    return max(gaps)


# ── 2. A slow SYNCHRONOUS embedder must not block the event loop ──────────

@pytest.mark.asyncio
async def test_slow_synchronous_embedder_does_not_block_event_loop():
    m = _matcher(3)
    with patch("ollama.Client", _fake_ollama()):
        gap = await _max_loop_gap(lambda: m.match("example 0", wait_timeout=None))
    assert gap < BLOCK_SECS / 2, (
        f"event loop was starved for {gap:.3f}s by a synchronous embedding call "
        f"(each blocks {BLOCK_SECS}s) — the prewarm must run it off the loop"
    )


# ── 3. Startup lifecycle continues while initialization runs ──────────────

@pytest.mark.asyncio
async def test_prewarm_returns_immediately_and_loop_stays_responsive():
    m = _matcher(3)
    with patch("ollama.Client", _fake_ollama()):
        t0 = time.perf_counter()
        gap = await _max_loop_gap(lambda: m.prewarm())
        assert time.perf_counter() - t0 < BLOCK_SECS, "prewarm() must not wait for the embeddings"
        assert gap < BLOCK_SECS / 2
        assert m._embeddings is None, "bootstrap is still running in the background (not ready yet)"
        await m._init_task  # let the shared task finish inside the patch


def test_app_lifespan_schedules_prewarm_without_awaiting_it():
    src = (Path(__file__).parent.parent / "core" / "api" / "app.py").read_text(encoding="utf-8")
    assert "asyncio.create_task(_governor_mod.classify_chat_intent._matcher.prewarm())" in src
    assert "await _governor_mod.classify_chat_intent._matcher.prewarm()" not in src


# ── 4/5/6. Bounded wait expires; timeout does not cancel; bootstrap completes ─

@pytest.mark.asyncio
async def test_bounded_wait_expires_without_cancelling_the_bootstrap():
    m = _matcher(3)
    with patch("ollama.Client", _fake_ollama()):
        t0 = time.perf_counter()
        first = await m.match("example 0", wait_timeout=0.1)
        assert first is None
        assert time.perf_counter() - t0 < BLOCK_SECS * 2, "bounded wait must return promptly"
        assert not m._init_task.cancelled() and not m._init_task.done(), "timeout must not cancel the shared bootstrap"
        await m._init_task
    assert m._embeddings is not None and len(m._embeddings) == 3


# ── 7. Atomic ready state ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ready_state_is_published_atomically_only_when_complete():
    m = _matcher(4)
    observed: list = []
    with patch("ollama.Client", _fake_ollama(block=0.05)):
        await m.prewarm()
        while not m._init_task.done():
            observed.append(None if m._embeddings is None else len(m._embeddings))
            await asyncio.sleep(0.005)
    assert set(observed) <= {None}, f"a partially built list must never be visible, saw {set(observed)}"
    assert len(m._embeddings) == 4


# ── 8. A subsequent match uses the initialized matcher ────────────────────

@pytest.mark.asyncio
async def test_subsequent_match_uses_initialized_matcher_without_reinitializing():
    m = _matcher(3)
    calls: list = []
    with patch("ollama.Client", _fake_ollama(block=0.01, calls=calls)):
        await m.prewarm()
        await m._init_task
        n_after_init = len(calls)
        result = await m.match("example 1", wait_timeout=0.05)
    assert result is not None and result["type"] == "search_web"
    assert len([c for c in calls if c.startswith("example")]) == 3
    assert len(calls) == n_after_init + 0 or calls[-1] == "example 1"  # only the query itself was embedded


# ── 9. Initialization failure is contained ────────────────────────────────

@pytest.mark.asyncio
async def test_initialization_failure_is_contained():
    m = _matcher(2)
    with patch("ollama.Client", _fake_ollama(block=0.01, fail=True)):
        result = await m.match("example 0", wait_timeout=None)
    assert result is None  # no crash, no exception escaping /command's path


# ── 1/10. Exactly one initialization; no duplicate worker/task ────────────

@pytest.mark.asyncio
async def test_single_initialization_under_concurrent_access():
    m = _matcher(3)
    calls: list = []
    with patch("ollama.Client", _fake_ollama(block=0.02, calls=calls)):
        await asyncio.gather(
            m.prewarm(), m.prewarm(),
            m.match("example 0", wait_timeout=None),
            m.match("example 1", wait_timeout=None),
            m.match("example 2", wait_timeout=0.01),
        )
        await m._init_task
    example_embeds = [c for c in calls if c in ("example 0", "example 1", "example 2")]
    # 3 bootstrap embeds; a query that equals an example text is served from the embedding cache
    assert len(example_embeds) == 3, f"expected exactly one bootstrap pass, saw {calls!r}"
