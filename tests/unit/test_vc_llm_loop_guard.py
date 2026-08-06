"""KNOWN_ISSUES #0 Part 2 -- vectorcode_llm.chat() is a plain sync function;
called from inside a coroutine with a RUNNING event loop and no `await`/
`asyncio.to_thread`, it blocks that loop for up to timeout + grace seconds
(fccdeb91f). ~112 files call it exactly this way from district agents' async
run() methods today.

Rewriting all 112 call sites is a much bigger, riskier change than this bug
warrants, so chat() does NOT raise by default. Instead it detects the
running-loop shape and warns LOUDLY, naming the exact calling file/line/
function so offenders are enumerable from the logs and can be migrated to
`achat()` (the async-native replacement added alongside this guard) one at a
time. An opt-in strict mode (CONFIG["vc_llm_loop_guard_strict"]) raises
instead, for tests/CI, so the antipattern can't grow silently without risking
a simultaneous production outage across all 112 sites.

Log capture uses loguru's own `logger.add(sink, level=...)` (this codebase
never routes through stdlib logging, so pytest's `caplog` fixture cannot see
these messages) -- same pattern as
tests/unit/test_agent_registry_successor_class.py.
"""
from __future__ import annotations

import asyncio

import pytest
from loguru import logger

from core.config import CONFIG


pytestmark = pytest.mark.unit


def _stub_fast_chat(monkeypatch):
    """Make chat()'s/achat()'s real network/provider path an instant no-op
    so these tests measure only the loop-guard behaviour, never real
    inference or network calls."""
    import core.inference.vectorcode_llm as vc_llm

    async def _fake_pc_chat(*_a, **_kw):
        class _R:
            content = "stub-response"

        return _R()

    monkeypatch.setattr(
        "core.inference.provider_client.ProviderClient.chat", _fake_pc_chat
    )
    monkeypatch.setattr(vc_llm, "_try_gemini", lambda *a, **kw: "")
    monkeypatch.setattr(vc_llm, "_try_openrouter", lambda *a, **kw: "")
    monkeypatch.setattr(vc_llm, "_try_ollama", lambda *a, **kw: "")
    return vc_llm


# ── Warn mode (the production default) ──────────────────────────────────────

def test_chat_from_running_loop_warns_and_identifies_caller(monkeypatch):
    vc_llm = _stub_fast_chat(monkeypatch)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_strict", False)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_cooldown_sec", 0.0)
    vc_llm._LOOP_WARNING_LAST.clear()

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="WARNING")

    async def _bad_caller():
        # This IS the antipattern under test: a plain sync chat() call made
        # directly from inside a coroutine, no `await`/`asyncio.to_thread`.
        return vc_llm.chat(model="vector-fast", messages=[{"role": "user", "content": "hi"}])

    try:
        result = asyncio.run(_bad_caller())
    finally:
        logger.remove(sink_id)

    assert result == "stub-response"  # the call itself still completes normally
    joined = "\n".join(captured)
    assert "BLOCKING CALL" in joined
    assert "chat(model=" in joined
    assert __file__ in joined, "must name the real calling file"
    assert "_bad_caller" in joined, "must name the real calling function"
    assert "achat" in joined, "must point at the migration path"


def test_chat_with_no_running_loop_is_silent_and_unchanged(monkeypatch):
    """The overwhelmingly common, correct call shape -- chat() from a plain
    thread with no event loop of its own -- must be completely unaffected:
    no warning logged, no behaviour change."""
    vc_llm = _stub_fast_chat(monkeypatch)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_strict", False)

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="WARNING")
    try:
        result = vc_llm.chat(model="vector-fast", messages=[{"role": "user", "content": "hi"}])
    finally:
        logger.remove(sink_id)

    assert result == "stub-response"
    assert not any("BLOCKING CALL" in m for m in captured)


def test_loop_guard_warning_is_rate_limited_per_call_site(monkeypatch):
    """A hot call site (same file/line, called repeatedly) must not re-log
    the warning inside the configured cooldown -- otherwise a tight loop
    calling chat() from an async context would drown the logs. All three
    calls below must originate from the SAME source line (the loop body) so
    they resolve to the same call site."""
    vc_llm = _stub_fast_chat(monkeypatch)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_strict", False)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_cooldown_sec", 300.0)
    vc_llm._LOOP_WARNING_LAST.clear()

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="WARNING")

    async def _bad_caller():
        for _ in range(3):
            vc_llm.chat(model="vector-fast", messages=[{"role": "user", "content": "hi"}])

    try:
        asyncio.run(_bad_caller())
    finally:
        logger.remove(sink_id)

    warnings = [m for m in captured if "BLOCKING CALL" in m]
    assert len(warnings) == 1, (
        f"expected exactly 1 warning across 3 same-site calls within the "
        f"cooldown window, got {len(warnings)} -- rate limiting is broken "
        f"(this is what keeps ~112 potential call sites from drowning the logs)"
    )


# ── Strict mode (opt-in, for tests/CI) ──────────────────────────────────────

def test_strict_mode_raises_from_running_loop(monkeypatch):
    vc_llm = _stub_fast_chat(monkeypatch)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_strict", True)

    async def _bad_caller():
        return vc_llm.chat(model="vector-fast", messages=[{"role": "user", "content": "hi"}])

    with pytest.raises(RuntimeError, match="BLOCKING CALL"):
        asyncio.run(_bad_caller())


def test_strict_mode_does_not_raise_with_no_running_loop(monkeypatch):
    """Strict mode only guards the running-loop shape -- an ordinary sync
    call (no event loop on this thread) must still succeed normally."""
    vc_llm = _stub_fast_chat(monkeypatch)
    monkeypatch.setitem(CONFIG, "vc_llm_loop_guard_strict", True)

    result = vc_llm.chat(model="vector-fast", messages=[{"role": "user", "content": "hi"}])
    assert result == "stub-response"


# ── achat() -- the async-native replacement ──────────────────────────────────

async def test_achat_returns_directly_with_no_thread_round_trip(monkeypatch):
    """achat() is the migration target chat()'s warning points at -- confirm
    it actually works from a real running event loop and never fires its own
    running-loop warning against itself (it's the correct call shape)."""
    vc_llm = _stub_fast_chat(monkeypatch)

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="WARNING")
    try:
        result = await vc_llm.achat(
            model="vector-fast", messages=[{"role": "user", "content": "hi"}]
        )
    finally:
        logger.remove(sink_id)

    assert result == "stub-response"
    assert not any("BLOCKING CALL" in m for m in captured)


async def test_achat_does_not_block_a_concurrent_sibling_coroutine(monkeypatch):
    """Proof achat() genuinely awaits rather than blocking: a slow (mocked)
    ProviderClient.chat() must not prevent a concurrently scheduled sibling
    coroutine from making progress -- the same shape used to prove
    to_thread() offloading elsewhere in this codebase
    (tests/unit/test_loop_stall_fixes.py's benchmarker test)."""
    import core.inference.vectorcode_llm as vc_llm

    _SLOW_SEC = 0.3

    async def _slow_pc_chat(*_a, **_kw):
        await asyncio.sleep(_SLOW_SEC)

        class _R:
            content = "slow-stub-response"

        return _R()

    monkeypatch.setattr(
        "core.inference.provider_client.ProviderClient.chat", _slow_pc_chat
    )

    ticks = 0

    async def _ticker():
        nonlocal ticks
        for _ in range(15):
            await asyncio.sleep(0.02)
            ticks += 1

    results = await asyncio.gather(
        vc_llm.achat(model="vector-fast", messages=[{"role": "user", "content": "hi"}]),
        _ticker(),
    )

    assert results[0] == "slow-stub-response"
    assert ticks >= 8, (
        f"only {ticks} concurrent ticks during a {_SLOW_SEC}s achat() call -- "
        f"achat() is blocking the event loop instead of awaiting cooperatively"
    )


def test_vc_llm_loop_guard_config_values_present_and_sane():
    assert isinstance(CONFIG.get("vc_llm_loop_guard_strict"), bool)
    assert isinstance(CONFIG.get("vc_llm_loop_guard_cooldown_sec"), (int, float))
    assert 0.0 <= CONFIG["vc_llm_loop_guard_cooldown_sec"] <= 3600.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
