"""Task 88 (R1 runtime remediation) -- `_multi_backend_fallback()` used to
accept a `timeout` parameter and never reference it: none of its three
engine.generate() calls (LiteLLM, Apple FM, Gemma C++) received a bound and
none were wrapped in a circuit breaker, so a hung engine blocked this
synchronous function -- and therefore its caller's thread -- indefinitely.
Reachable from the event-loop thread via Governor._llm_classify() and
AgentBase.vchat(), both of which call ollama_safe.chat() synchronously from
inside `async def` functions.

Fixed: the three-engine attempt now runs on a dedicated single-worker
`concurrent.futures.ThreadPoolExecutor`, and `_multi_backend_fallback()`
bounds its *wait* on that worker to `timeout` seconds via
`Future.result(timeout=...)`. Engine order and the total-failure
`return ""` contract are unchanged; only the caller-side wait is bounded.

These tests mock every fallback engine at its real import location
(`vectorcode.src.vc_engine.litellm.LiteLLMEngine`,
`vectorcode.src.vc_engine.apple_fm_shim.AppleFMEngine` (does not exist as a
real class today -- created with `create=True`, see Task 88's report),
`vectorcode.src.vc_engine.gemma_cpp.GemmaCppEngine`) so that NO real network
call, model load, or subprocess is ever reached -- the exact discipline the
58A "stale mock" incident (two real process launches during testing before
mocking was complete, VECTOR_TECHNICAL_KNOWLEDGE Task 58A) exists to avoid.
"""
from __future__ import annotations

import threading
import time

import pytest

pytestmark = pytest.mark.unit


def _patch_all_engines(monkeypatch, *, litellm=None, apple_fm=None, gemma=None):
    """Patch all three engine classes at their real import locations.
    Each of litellm/apple_fm/gemma, if given, is a callable(*, model,
    fallback_messages) invoked in place of the real engine's constructor +
    generate(); if None, the branch is made to raise ImportError (matching
    'this backend is unavailable' -- the same shape a real missing
    dependency already produces via the existing broad `except Exception`)."""
    import vectorcode.src.vc_engine.litellm as litellm_mod
    import vectorcode.src.vc_engine.gemma_cpp as gemma_mod

    class _FakeLiteLLM:
        def generate(self, messages, *, model, max_tokens=2048, **kw):
            if litellm is None:
                raise RuntimeError("litellm unavailable (test stub)")
            return litellm(model=model, fallback_messages=messages)

    class _FakeAppleFM:
        def generate(self, messages, *, model, max_tokens=2048, **kw):
            if apple_fm is None:
                raise RuntimeError("apple_fm unavailable (test stub)")
            return apple_fm(model=model, fallback_messages=messages)

    class _FakeGemma:
        def generate(self, messages, *, model, max_tokens=2048, **kw):
            if gemma is None:
                raise RuntimeError("gemma unavailable (test stub)")
            return gemma(model=model, fallback_messages=messages)

    monkeypatch.setattr(litellm_mod, "LiteLLMEngine", _FakeLiteLLM)
    # apple_fm_shim.py has no AppleFMEngine class in current source at all
    # (it is a standalone FastAPI server module, see Task 88's report) --
    # the real code's `from ...apple_fm_shim import AppleFMEngine` already
    # raises ImportError on every platform today. create=True lets the test
    # attach the attribute anyway so both branches (present/absent) of this
    # test suite can exercise the call path uniformly.
    import vectorcode.src.vc_engine.apple_fm_shim as apple_fm_mod
    monkeypatch.setattr(apple_fm_mod, "AppleFMEngine", _FakeAppleFM, raising=False)
    monkeypatch.setattr(gemma_mod, "GemmaCppEngine", _FakeGemma)

    # Force litellm-candidate routing regardless of the model name used in
    # a given test, and make _to_vectorcode_messages a passthrough so the
    # fake engines above receive exactly what was passed to chat/fallback.
    import core.inference.ollama_safe as ollama_safe
    monkeypatch.setattr(ollama_safe, "_is_litellm_candidate", lambda m: True)
    monkeypatch.setattr(ollama_safe, "_to_vectorcode_messages", lambda msgs: msgs)


def test_bounded_wait_when_every_engine_hangs(monkeypatch):
    """TEST 1 -- BOUNDED BLOCKING. All three engines block far longer than
    the configured timeout. _multi_backend_fallback() must still return
    within a small, bounded wall-clock window -- not wait for the hang."""
    import core.inference.ollama_safe as ollama_safe

    release_workers = threading.Event()

    def _hang(*, model, fallback_messages):
        # Blocks until the test explicitly releases it (or the process
        # exits) -- simulates a genuinely stuck network/native call. Never
        # sleeps for a fixed "long" duration, so the test itself never has
        # to wait out a real long timer.
        release_workers.wait(timeout=30)
        return {"content": "should never be observed by the caller"}

    _patch_all_engines(monkeypatch, litellm=_hang, apple_fm=None, gemma=None)

    _TIMEOUT = 0.3
    start = time.monotonic()
    result = ollama_safe._multi_backend_fallback(
        "vector-fast", [{"role": "user", "content": "hi"}], _TIMEOUT,
        caller_id="test_bounded_wait",
    )
    elapsed = time.monotonic() - start

    try:
        assert result == "", "must return the honest empty-string failure, never fabricate a result"
        assert elapsed < _TIMEOUT * 6, (
            f"_multi_backend_fallback took {elapsed:.2f}s against a {_TIMEOUT}s "
            f"configured deadline -- the fix is not actually bounding the wait "
            f"(before the fix this call blocked until the engine returned, i.e. "
            f"indefinitely for a genuinely hung engine)"
        )
    finally:
        # Release the still-running worker thread so it doesn't leak past
        # the end of this test process.
        release_workers.set()


def test_fallback_order_preserved_on_success(monkeypatch):
    """TEST 2 -- SUCCESS REGRESSION. LiteLLM succeeds immediately; Apple FM
    and Gemma must never even be attempted (same short-circuit-on-success
    order as before this fix), and the returned text must be exactly what
    the engine produced."""
    import core.inference.ollama_safe as ollama_safe

    calls = []

    def _litellm_ok(*, model, fallback_messages):
        calls.append("litellm")
        return {"content": "litellm says hi"}

    def _apple_fm_should_not_run(*, model, fallback_messages):
        calls.append("apple_fm")
        return {"content": "should not be reached"}

    def _gemma_should_not_run(*, model, fallback_messages):
        calls.append("gemma")
        return {"content": "should not be reached"}

    _patch_all_engines(
        monkeypatch,
        litellm=_litellm_ok, apple_fm=_apple_fm_should_not_run, gemma=_gemma_should_not_run,
    )

    result = ollama_safe._multi_backend_fallback(
        "vector-fast", [{"role": "user", "content": "hi"}], 5.0,
        caller_id="test_success_regression",
    )

    assert result == "litellm says hi"
    assert calls == ["litellm"], f"expected only litellm to run, got {calls}"


def test_fallback_order_falls_through_on_failure(monkeypatch):
    """TEST 2b -- SUCCESS REGRESSION (order). LiteLLM and Apple FM fail;
    Gemma succeeds. All three must be attempted in the documented order
    (LiteLLM -> Apple FM -> Gemma C++), unchanged from before this fix."""
    import core.inference.ollama_safe as ollama_safe

    calls = []

    def _litellm_fail(*, model, fallback_messages):
        calls.append("litellm")
        raise RuntimeError("litellm down")

    def _apple_fm_fail(*, model, fallback_messages):
        calls.append("apple_fm")
        raise RuntimeError("apple_fm down")

    def _gemma_ok(*, model, fallback_messages):
        calls.append("gemma")
        return {"content": "gemma says hi"}

    _patch_all_engines(monkeypatch, litellm=_litellm_fail, apple_fm=_apple_fm_fail, gemma=_gemma_ok)

    result = ollama_safe._multi_backend_fallback(
        "vector-fast", [{"role": "user", "content": "hi"}], 5.0,
        caller_id="test_order_regression",
    )

    assert result == "gemma says hi"
    assert calls == ["litellm", "apple_fm", "gemma"], f"engine order changed: {calls}"


def test_total_failure_returns_empty_string(monkeypatch):
    """All three engines fail cleanly (not a timeout) -- existing
    total-failure contract must be preserved exactly: return ''."""
    import core.inference.ollama_safe as ollama_safe

    def _fail(*, model, fallback_messages):
        raise RuntimeError("unavailable")

    _patch_all_engines(monkeypatch, litellm=_fail, apple_fm=_fail, gemma=_fail)

    result = ollama_safe._multi_backend_fallback(
        "vector-fast", [{"role": "user", "content": "hi"}], 5.0,
        caller_id="test_total_failure",
    )
    assert result == ""


def test_timeout_recorded_honestly_in_observability(monkeypatch):
    """TEST 3 -- FAILURE/OBSERVABILITY REGRESSION. On a genuine deadline hit,
    the existing (unmodified, no-schema-change) observability contract must
    record a distinguishable, honest status -- not silently look identical
    to an ordinary clean failure, and never fabricate a success."""
    import core.inference.ollama_safe as ollama_safe

    release_workers = threading.Event()
    recorded: list[dict] = []

    def _hang(*, model, fallback_messages):
        release_workers.wait(timeout=30)
        return {"content": "unused"}

    def _fake_record_observability(caller_id, model, provider, content, latency_ms, *,
                                    status="ok", error_kind="", input_tokens=0, output_tokens=0):
        recorded.append({
            "caller_id": caller_id, "model": model, "provider": provider,
            "content": content, "status": status, "error_kind": error_kind,
        })

    _patch_all_engines(monkeypatch, litellm=_hang, apple_fm=None, gemma=None)
    monkeypatch.setattr(ollama_safe, "_record_observability", _fake_record_observability)

    try:
        result = ollama_safe._multi_backend_fallback(
            "vector-fast", [{"role": "user", "content": "hi"}], 0.2,
            caller_id="test_observability_honesty",
        )
        assert result == ""
        assert len(recorded) == 1, f"expected exactly one observability record, got {recorded}"
        rec = recorded[0]
        assert rec["caller_id"] == "test_observability_honesty", "caller_id must survive the timeout path"
        assert rec["status"] != "ok", "a timed-out fallback must never be recorded as status='ok'"
        assert rec["content"] == "", "must never fabricate content on a timeout"
        # Distinguishable from an ordinary clean multi-engine failure (which
        # chat() itself records with status="error") without requiring any
        # schema change -- both `status` and `error_kind` are pre-existing
        # free-text columns.
        assert rec["status"] == "timeout"
        assert rec["error_kind"]
    finally:
        release_workers.set()


def test_caller_id_reaches_a_successful_engine_record(monkeypatch):
    """Observability for the ordinary success path (no timeout involved)
    must still carry the real caller_id through to the fallback engine's
    own _record_observability call -- unchanged from before this fix."""
    import core.inference.ollama_safe as ollama_safe

    recorded: list[dict] = []

    def _fake_record_observability(caller_id, model, provider, content, latency_ms, *,
                                    status="ok", error_kind="", input_tokens=0, output_tokens=0):
        recorded.append({"caller_id": caller_id, "provider": provider, "status": status})

    def _litellm_ok(*, model, fallback_messages):
        return {"content": "ok"}

    _patch_all_engines(monkeypatch, litellm=_litellm_ok)
    monkeypatch.setattr(ollama_safe, "_record_observability", _fake_record_observability)

    result = ollama_safe._multi_backend_fallback(
        "vector-fast", [{"role": "user", "content": "hi"}], 5.0,
        caller_id="test_caller_id_propagation",
    )

    assert result == "ok"
    assert len(recorded) == 1
    assert recorded[0]["caller_id"] == "test_caller_id_propagation"
    assert recorded[0]["provider"] == "litellm_fallback"
    assert recorded[0]["status"] == "ok"


def test_no_asyncio_wait_for_used_and_function_stays_synchronous():
    """Guard against a future regression that would reintroduce
    asyncio.wait_for inside this synchronous function (explicitly
    prohibited for Task 88 -- the function may run with no event loop)."""
    import asyncio
    import inspect

    import core.inference.ollama_safe as ollama_safe

    assert not inspect.iscoroutinefunction(ollama_safe._multi_backend_fallback)
    src = inspect.getsource(ollama_safe._multi_backend_fallback)
    # Check for an actual call/await, not prose mentioning the name in the
    # docstring (which deliberately explains why asyncio.wait_for is NOT
    # used here).
    assert "asyncio.wait_for(" not in src
    assert "await " not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
