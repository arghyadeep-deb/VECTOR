"""KNOWN_ISSUES #0 Part 1 -- ollama_safe's threading.Semaphore had no acquire
timeout; `with _OLLAMA_SYNC_SEMAPHORE:` blocked forever if a slot-holder never
released it. Ranked SECONDARY in the original loop-stall hunt because it
needed a slot-holder to already be stuck -- but fccdeb91f proved a holder CAN
hang indefinitely (the exact ThreadPoolExecutor-shutdown bug fixed one layer
up, in vectorcode_llm.chat()), so that precondition is no longer hypothetical.
When a holder hangs, every caller queued behind it now hangs too -- the
semaphore turns one stuck call into many.

Fixed: bounded `.acquire(timeout=CONFIG["ollama_semaphore_timeout_sec"])`
with an explicit `finally: release()`, at all three acquire sites (chat(),
chat_stream(), warm_models()). On acquire-timeout: log loudly, then fall back
exactly like a dead Ollama daemon already does (never fabricate a fake
success -- chat()'s pre-existing honest-failure contract, not a new one).

These tests use the REAL module-level threading.Semaphore (not mocked) --
only the transport/fallback functions are stubbed so the timing measured is
genuinely the semaphore's own bound, not network latency.
"""
from __future__ import annotations

import time

import pytest

from core.config import CONFIG


pytestmark = pytest.mark.unit


def _hold_every_slot(ollama_safe):
    """Acquire every configured concurrency slot from THIS thread and never
    release it within the test body -- simulates a stuck holder that never
    reaches its own `finally: release()`. Caller must release afterward."""
    limit = CONFIG["ollama_max_concurrent"]
    held = [ollama_safe._OLLAMA_SYNC_SEMAPHORE.acquire() for _ in range(limit)]
    assert all(held), "failed to acquire every slot -- test setup is broken"
    return held


def test_chat_acquire_times_out_instead_of_blocking_forever(monkeypatch):
    """A second caller behind a permanently-stuck slot-holder must return
    within the configured acquire-timeout bound, not hang indefinitely.
    Real timing assertion: before the fix this call would never return."""
    import core.inference.ollama_safe as ollama_safe

    _ACQUIRE_TIMEOUT = 0.5
    monkeypatch.setitem(CONFIG, "ollama_semaphore_timeout_sec", _ACQUIRE_TIMEOUT)
    # Isolate the measurement to the semaphore's own bound -- no real network,
    # no dependency on _multi_backend_fallback's own (possibly slow) chain.
    monkeypatch.setattr(ollama_safe, "_multi_backend_fallback", lambda *a, **kw: "")

    held = _hold_every_slot(ollama_safe)
    try:
        start = time.monotonic()
        result = ollama_safe.chat(
            "vector-fast", [{"role": "user", "content": "hi"}], timeout=30.0,
        )
        elapsed = time.monotonic() - start

        assert result == "", "must return the honest empty-string failure, never a fabricated success"
        assert elapsed < _ACQUIRE_TIMEOUT * 4, (
            f"chat() took {elapsed:.2f}s against a {_ACQUIRE_TIMEOUT}s configured "
            f"acquire timeout -- the bounded acquire is not actually bounding the wait "
            f"(before the fix this call blocked until the stuck holder released, i.e. "
            f"never, in production)"
        )
    finally:
        for _ in held:
            ollama_safe._OLLAMA_SYNC_SEMAPHORE.release()


def test_chat_stream_acquire_times_out_yields_empty_and_stops(monkeypatch):
    """The streaming generator must honor the same bounded acquire -- yield
    "" once and stop, rather than hang for the caller's iteration lifetime."""
    import core.inference.ollama_safe as ollama_safe

    _ACQUIRE_TIMEOUT = 0.3
    monkeypatch.setitem(CONFIG, "ollama_semaphore_timeout_sec", _ACQUIRE_TIMEOUT)

    held = _hold_every_slot(ollama_safe)
    try:
        start = time.monotonic()
        tokens = list(
            ollama_safe.chat_stream("vector-fast", [{"role": "user", "content": "hi"}])
        )
        elapsed = time.monotonic() - start

        assert tokens == [""]
        assert elapsed < _ACQUIRE_TIMEOUT * 4, (
            f"chat_stream() took {elapsed:.2f}s against a {_ACQUIRE_TIMEOUT}s "
            f"acquire timeout -- streaming path is still blocking forever"
        )
    finally:
        for _ in held:
            ollama_safe._OLLAMA_SYNC_SEMAPHORE.release()


def test_warm_models_acquire_times_out_marks_failure_and_continues(monkeypatch):
    """warm_models() must not block process startup forever on a stuck slot;
    a timed-out model is recorded as a failure and warm-up proceeds."""
    import core.inference.ollama_safe as ollama_safe

    _ACQUIRE_TIMEOUT = 0.3
    monkeypatch.setitem(CONFIG, "ollama_semaphore_timeout_sec", _ACQUIRE_TIMEOUT)

    held = _hold_every_slot(ollama_safe)
    try:
        start = time.monotonic()
        results = ollama_safe.warm_models(models=["vector-fast"])
        elapsed = time.monotonic() - start

        assert results == {"vector-fast": False}
        assert elapsed < _ACQUIRE_TIMEOUT * 4, (
            f"warm_models() took {elapsed:.2f}s against a {_ACQUIRE_TIMEOUT}s "
            f"acquire timeout -- startup warm-up is still blockable forever"
        )
    finally:
        for _ in held:
            ollama_safe._OLLAMA_SYNC_SEMAPHORE.release()


def test_semaphore_still_releases_normally_on_the_happy_path(monkeypatch):
    """Sanity check the new manual acquire/release (replacing `with sem:`)
    didn't leak a permit on the ordinary success path -- N sequential calls
    must never deadlock or exhaust the pool."""
    import core.inference.ollama_safe as ollama_safe
    import sys
    import types

    class FakeOllamaClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def chat(self, **kwargs):
            return {"message": {"content": "ok"}}

    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=FakeOllamaClient))

    limit = CONFIG["ollama_max_concurrent"]
    for _ in range(limit * 5):
        result = ollama_safe.chat("vector-fast", [{"role": "user", "content": "hi"}], timeout=2.0)
        assert result == "ok"

    # Every permit must be back -- acquiring the full pool immediately (non-blocking)
    # must succeed if and only if nothing leaked.
    held = [ollama_safe._OLLAMA_SYNC_SEMAPHORE.acquire(timeout=0.1) for _ in range(limit)]
    try:
        assert all(held), "a semaphore permit leaked on the happy path (manual acquire/release regression)"
    finally:
        for h in held:
            if h:
                ollama_safe._OLLAMA_SYNC_SEMAPHORE.release()


def test_ollama_semaphore_timeout_config_value_present_and_sane():
    assert isinstance(CONFIG.get("ollama_semaphore_timeout_sec"), (int, float))
    assert 1.0 <= CONFIG["ollama_semaphore_timeout_sec"] <= 300.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
