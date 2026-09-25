"""T89A runtime boundary review — Governor.dispatch()'s async body used to call
the plain sync route_task() directly (no await, no thread hop). route_task()
falls through to _llm_classify() for any task_type that isn't an exact/
substring DISTRICT_TASK_MAP match, and _llm_classify() calls the SYNCHRONOUS
ollama_safe.chat() (and, before that, its own _cloud_classify() cloud path).
dispatch() is VECTOR's highest-volume routing path, so a direct call there
blocked the calling coroutine's event loop for the full duration of every
classification round-trip -- ordinary multi-second inference/cloud latency,
not just a hang.

Fixed: a new Governor.route_task_async() is used by dispatch() instead of
route_task(). Keyword/exact matching (cheap, no I/O) stays inline and
synchronous; only the LLM-fallback path is moved off the event loop thread
via a genuine `await asyncio.to_thread(...)`. route_task()/_llm_classify()
themselves are UNCHANGED -- they keep serving their ~10 other sync call sites
directly.

These tests use a REAL asyncio event loop (asyncio_mode = auto, see
pytest.ini) and a real timing assertion -- a second, independent coroutine's
own progress is measured while route_task_async() is in flight, not just
"mock was called". No real Ollama/network/subprocess: only
Governor._llm_classify (an instance method) or ollama_safe.chat are stubbed.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from core.city.governor import Governor


pytestmark = pytest.mark.unit


async def test_route_task_async_llm_fallback_does_not_block_event_loop(monkeypatch):
    """A slow (but bounded) classification call must not stall a concurrent,
    independent coroutine running on the same event loop. Before the fix,
    route_task_async() didn't exist and dispatch() called the sync
    route_task() -> _llm_classify() -> ollama_safe.chat() chain directly;
    a real time.sleep() inside that chain would have frozen the whole loop
    for its duration, and the ticker below would have measured ~0 progress
    strictly during the call (verified directly against the pre-fix call
    pattern -- gov.route_task() called synchronously from inside a
    coroutine -- which scores exactly 0 ticks under this same harness)."""
    gov = Governor()
    SLEEP = 0.3

    def slow_llm_classify(task_type: str) -> str:
        # Simulates real synchronous Ollama/cloud latency inside
        # Governor._llm_classify -- a blocking call on whatever thread
        # invokes it, exactly like the real ollama_safe.chat() round-trip.
        time.sleep(SLEEP)
        return "research"

    monkeypatch.setattr(gov, "_llm_classify", slow_llm_classify)

    progress = {"ticks": 0}
    stop = {"flag": False}

    async def ticker() -> None:
        while not stop["flag"]:
            progress["ticks"] += 1
            await asyncio.sleep(0.005)

    ticker_task = asyncio.create_task(ticker())
    start = time.monotonic()
    district = await gov.route_task_async("totally_unknown_task_xyz_89a")
    elapsed = time.monotonic() - start
    stop["flag"] = True
    await ticker_task

    assert district == "research"
    assert elapsed >= SLEEP, "test setup broken -- the slow classify stub did not actually run"
    # If route_task_async() blocked the loop synchronously for SLEEP seconds
    # (the pre-fix behavior), the ticker would have advanced 0 times strictly
    # during the call -- confirmed empirically: the pre-fix call pattern
    # (gov.route_task() invoked directly/unawaited from inside a coroutine)
    # scores exactly 0 ticks under this identical harness. A genuine
    # asyncio.to_thread hand-off lets the ticker keep advancing throughout;
    # require a solid double-digit count, not just ">0", to reject flukes.
    assert progress["ticks"] >= 15, (
        f"ticker only advanced {progress['ticks']} times strictly during the "
        f"{elapsed:.3f}s route_task_async() call -- the event loop was "
        f"blocked instead of yielded (asyncio.to_thread hand-off is not "
        f"working); the equivalent pre-fix sync call pattern scores 0 here"
    )


async def test_route_task_async_keyword_match_is_synchronous_and_fast():
    """The cheap keyword/exact-match path must not pay any thread-hop cost --
    only the LLM fallback needs asyncio.to_thread."""
    gov = Governor()
    start = time.monotonic()
    result = await gov.route_task_async("review my git code")
    elapsed = time.monotonic() - start
    assert result == "coding"
    assert elapsed < 0.2, f"keyword match took {elapsed:.3f}s -- unexpectedly went through a thread hop"


def test_route_task_sync_unchanged(monkeypatch):
    """route_task()/_llm_classify() must be byte-for-byte behaviorally
    unchanged for their ~10 other synchronous call sites (tests,
    core/api/routers/commands.py, core/memory/router.py,
    core/voice/realtime.py, vc_agents/routing_agent.py) -- this fix only
    added a new method and one dispatch() call site, it did not touch the
    existing sync ones."""
    import core.inference.ollama_safe as ollama_safe

    monkeypatch.setattr(ollama_safe, "chat", lambda *a, **kw: "")
    gov = Governor()
    assert gov.route_task("totally_unknown_task_xyz_89a") == "research"
    assert gov.route_task("review my git code") == "coding"


async def test_dispatch_routes_unknown_task_via_async_llm_fallback(monkeypatch):
    """End-to-end: dispatch() must still resolve an LLM-fallback task_type to
    a real district using route_task_async(), with no real Ollama call."""
    import core.inference.ollama_safe as ollama_safe

    monkeypatch.setattr(ollama_safe, "chat", lambda *a, **kw: "")
    gov = Governor()
    # "_llm_classified" is what classify_chat_intent() sets on a freshly LLM-invented task type -- the one kind of
    # unknown type that is still routed (an unmarked invented name is refused since 2026-09-25).
    result = await gov.dispatch({"type": "totally_unknown_task_xyz_89a", "_llm_classified": True})
    assert result.get("district") == "research"
    assert "task_id" in result


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
