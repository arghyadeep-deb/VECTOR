"""Regression test for the 2026-09-24 external review's Phase 3 finding
(loop thread freeze, KNOWN_ISSUES #0): a real thread dump
(data/logs/thread_dumps.log) caught the MAIN event loop thread blocked for
60+ real seconds inside script_generator.py's _llm(), which span up its
own ThreadPoolExecutor + nested asyncio.run() and blocked on
Future.result(timeout=120) -- even though every real caller (run(),
video_pipeline.py's _generate_script()) is already async, so that blocking
call froze the entire event loop (every other in-flight API request and
governor dispatch) for up to 120s on every script/hook/CTA generation.

Proves the fix concretely: while one ScriptGenerator call is in flight
(with a slow-but-async mocked LLM), a concurrently-scheduled, unrelated
coroutine on the SAME event loop keeps making forward progress -- which
would be impossible if _llm() still blocked the loop synchronously.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.content.script_generator import ScriptGenerator, _llm


def test_llm_and_all_public_methods_are_real_coroutines():
    assert inspect.iscoroutinefunction(_llm)
    for name in ("generate_script", "generate_hook", "generate_cta", "expand_script", "run"):
        assert inspect.iscoroutinefunction(getattr(ScriptGenerator, name)), (
            f"{name} must be async -- it calls _llm(), which is now async"
        )


@pytest.mark.asyncio
async def test_generate_script_does_not_block_the_event_loop():
    """The decisive proof: a concurrent, independent coroutine must keep
    making progress WHILE generate_script()'s (mocked, slow) LLM call is
    in flight. If _llm() still blocked synchronously (the original bug),
    the counter below would never increment until generate_script()
    returned."""
    gen = ScriptGenerator()
    tick_count = 0

    async def _ticker():
        nonlocal tick_count
        while True:
            await asyncio.sleep(0.02)
            tick_count += 1

    class _FakeResult:
        content = "INTRO: hello\nMAIN CONTENT: world\nSUMMARY: done"

    async def _slow_chat(*a, **kw):
        await asyncio.sleep(0.3)  # simulates a real network/LLM round trip
        return _FakeResult()

    ticker_task = asyncio.create_task(_ticker())
    try:
        with patch("core.inference.provider_client.ProviderClient.chat", new=_slow_chat):
            await gen.generate_script("test topic", duration_min=1.0)
    finally:
        ticker_task.cancel()

    assert tick_count >= 5, (
        f"expected the concurrent ticker to have advanced multiple times "
        f"while generate_script() was in flight (event loop must not be "
        f"blocked), got only {tick_count} ticks"
    )


@pytest.mark.asyncio
async def test_llm_awaits_provider_client_directly_no_thread_pool():
    """The original bug's exact mechanism: a nested ThreadPoolExecutor +
    asyncio.run() + Future.result(timeout=120). Confirm _llm() no longer
    creates a new thread or a new event loop at all."""
    import threading
    seen_thread_ids = set()

    class _FakeResult:
        content = "ok"

    async def _capture_thread_chat(*a, **kw):
        seen_thread_ids.add(threading.get_ident())
        return _FakeResult()

    with patch("core.inference.provider_client.ProviderClient.chat", new=_capture_thread_chat):
        result = await _llm("test prompt")

    assert result == "ok"
    assert seen_thread_ids == {threading.get_ident()}, (
        "the real LLM call must run on the SAME thread as the caller -- "
        "no nested ThreadPoolExecutor"
    )


@pytest.mark.asyncio
async def test_generate_script_still_returns_correct_shape():
    class _FakeResult:
        content = "INTRO: hi\nMAIN CONTENT: stuff\nSUMMARY: bye"

    async def _fake_chat(*a, **kw):
        return _FakeResult()

    gen = ScriptGenerator()
    with patch("core.inference.provider_client.ProviderClient.chat", new=_fake_chat):
        result = await gen.generate_script("test topic", duration_min=2.0)

    assert result["topic"] == "test topic"
    assert "error" not in result
    assert result["content"] == _FakeResult.content


@pytest.mark.asyncio
async def test_repeat_topic_within_cooldown_returns_cached_script_without_llm_call():
    """KNOWN_ISSUES #81: the identical "AI trends" topic was regenerated
    1,306+ times/day. Second call for the same topic must hit the cache
    (real content preserved for downstream composition), not the LLM."""
    ScriptGenerator.reset_script_cache()
    calls = {"n": 0}

    class _FakeResult:
        content = "INTRO: hi\nMAIN CONTENT: stuff\nSUMMARY: bye"

    async def _counting_chat(*a, **kw):
        calls["n"] += 1
        return _FakeResult()

    with patch("core.inference.provider_client.ProviderClient.chat", new=_counting_chat):
        first = await ScriptGenerator().generate_script("AI trends", duration_min=5.0)
        second = await ScriptGenerator().generate_script("AI trends", duration_min=5.0)  # fresh instance, like real callers

    assert calls["n"] == 1, "second call for the same topic must not hit the LLM again"
    assert "cached" not in first
    assert second["cached"] is True
    assert second["content"] == first["content"]
    ScriptGenerator.reset_script_cache()


@pytest.mark.asyncio
async def test_different_topic_or_duration_is_not_served_from_cache():
    ScriptGenerator.reset_script_cache()
    calls = {"n": 0}

    class _FakeResult:
        content = "INTRO: x"

    async def _counting_chat(*a, **kw):
        calls["n"] += 1
        return _FakeResult()

    with patch("core.inference.provider_client.ProviderClient.chat", new=_counting_chat):
        await ScriptGenerator().generate_script("topic A", duration_min=5.0)
        await ScriptGenerator().generate_script("topic B", duration_min=5.0)
        await ScriptGenerator().generate_script("topic A", duration_min=8.0)

    assert calls["n"] == 3
    ScriptGenerator.reset_script_cache()


@pytest.fixture(autouse=True)
def _clean_script_cache():
    ScriptGenerator.reset_script_cache()
    yield
    ScriptGenerator.reset_script_cache()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
