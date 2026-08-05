"""Verifies the Ollama concurrency bound added to core/inference/ollama_safe.py
(sync) and core/inference/provider_client.py (async).

Context: OLLAMA_MAX_LOADED_MODELS=1 (.claude/rules/models.md, 12GB RTX
5070 Ti) means the Ollama daemon holds exactly one model resident and serves
requests off a single decode slot. Nothing on VECTOR's side bounded how many
requests it fired at Ollama concurrently — two brain processes were once
observed holding 90 simultaneous connections against it. These tests fire
many concurrent callers at each code path and assert the observed peak
in-flight count never exceeds CONFIG["ollama_max_concurrent"].

No live Ollama daemon is required — the transport is stubbed at the module
boundary each call site actually uses (`ollama.Client` for the sync path,
`httpx.AsyncClient` for the async path), so these tests measure the real
semaphore behaviour without a network dependency.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
import types

import pytest

from core.config import CONFIG


# ── Sync path: core/inference/ollama_safe.chat() ────────────────────────────

def test_ollama_safe_chat_bounds_sync_concurrency(monkeypatch):
    """Fires N callers (N = 4x the configured limit) at ollama_safe.chat()
    from real OS threads and asserts the stubbed transport never sees more
    than CONFIG["ollama_max_concurrent"] calls in flight at once."""
    import core.inference.ollama_safe as ollama_safe

    limit = CONFIG["ollama_max_concurrent"]
    assert limit >= 1

    lock = threading.Lock()
    state = {"current": 0, "peak": 0}

    class FakeOllamaClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def chat(self, **kwargs):
            with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])
            time.sleep(0.05)  # simulate real Ollama decode latency
            with lock:
                state["current"] -= 1
            return {"message": {"content": "stub-response"}}

    fake_ollama_module = types.SimpleNamespace(Client=FakeOllamaClient)
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama_module)

    n_callers = limit * 4
    results: list[str] = []
    results_lock = threading.Lock()

    def worker():
        r = ollama_safe.chat("vector-fast", [{"role": "user", "content": "hi"}])
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(n_callers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not any(t.is_alive() for t in threads), (
        "a thread never completed — the semaphore may have deadlocked"
    )
    assert len(results) == n_callers
    assert all(r == "stub-response" for r in results)
    assert state["peak"] >= 1
    assert state["peak"] <= limit, (
        f"peak concurrent sync Ollama calls ({state['peak']}) exceeded "
        f"CONFIG['ollama_max_concurrent'] ({limit})"
    )


def test_ollama_safe_chat_stream_bounds_sync_concurrency(monkeypatch):
    """Same bound, but through the streaming generator path — the semaphore
    must stay held for the full duration the caller spends iterating, so
    two callers draining their streams concurrently must still never exceed
    the configured limit."""
    import core.inference.ollama_safe as ollama_safe

    limit = CONFIG["ollama_max_concurrent"]
    lock = threading.Lock()
    state = {"current": 0, "peak": 0}

    class FakeOllamaClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def chat(self, **kwargs):
            with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])

            def _gen():
                try:
                    for tok in ("hello", " ", "world"):
                        time.sleep(0.02)
                        yield {"message": {"content": tok}}
                finally:
                    with lock:
                        state["current"] -= 1

            return _gen()

    fake_ollama_module = types.SimpleNamespace(Client=FakeOllamaClient)
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama_module)

    n_callers = limit * 3
    all_tokens: list[list[str]] = [[] for _ in range(n_callers)]

    def worker(idx):
        for tok in ollama_safe.chat_stream("vector-fast", [{"role": "user", "content": "hi"}]):
            all_tokens[idx].append(tok)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_callers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not any(t.is_alive() for t in threads), (
        "a thread never completed — the streaming semaphore may have deadlocked"
    )
    assert all("".join(toks) == "hello world" for toks in all_tokens)
    assert state["peak"] <= limit, (
        f"peak concurrent streaming Ollama calls ({state['peak']}) exceeded "
        f"CONFIG['ollama_max_concurrent'] ({limit})"
    )


# ── Async path: core/inference/provider_client._call_openai_compat() ────────

class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self.text = "ok"
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _make_fake_httpx_module(state: dict, lock: asyncio.Lock):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            async with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])
            await asyncio.sleep(0.05)  # simulate real Ollama decode latency
            async with lock:
                state["current"] -= 1
            return _FakeHttpResponse({
                "choices": [{"message": {"content": "stub-response"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            })

    return types.SimpleNamespace(AsyncClient=FakeAsyncClient)


@pytest.mark.asyncio
async def test_provider_client_ollama_bounds_async_concurrency(monkeypatch):
    """Fires N concurrent coroutines at ProviderClient._call_openai_compat()
    routed to the "ollama" provider and asserts the stubbed httpx transport
    never sees more than CONFIG["ollama_max_concurrent"] POSTs in flight."""
    from core.inference.llm_providers import get_provider
    from core.inference.provider_client import ProviderClient

    limit = CONFIG["ollama_max_concurrent"]
    lock = asyncio.Lock()
    state = {"current": 0, "peak": 0}

    fake_httpx = _make_fake_httpx_module(state, lock)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    prov = get_provider("ollama")
    assert prov is not None
    client = ProviderClient()

    n_callers = limit * 4
    tasks = [
        client._call_openai_compat(
            prov, "vector-coder", [{"role": "user", "content": "hi"}],
            0.7, 128, None,
        )
        for _ in range(n_callers)
    ]
    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)

    assert len(results) == n_callers
    assert all(r.content == "stub-response" for r in results)
    assert state["peak"] >= 1
    assert state["peak"] <= limit, (
        f"peak concurrent async Ollama calls ({state['peak']}) exceeded "
        f"CONFIG['ollama_max_concurrent'] ({limit})"
    )


@pytest.mark.asyncio
async def test_provider_client_non_ollama_provider_is_not_bounded_by_ollama_semaphore(monkeypatch):
    """The async bound must be specific to the "ollama" provider — a cloud
    provider routed through the same _call_openai_compat() code path must
    NOT share (or be limited by) Ollama's semaphore."""
    from core.inference.llm_providers import get_provider
    from core.inference.provider_client import ProviderClient, _OLLAMA_ASYNC_SEMAPHORE

    lock = asyncio.Lock()
    state = {"current": 0, "peak": 0}
    fake_httpx = _make_fake_httpx_module(state, lock)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    # Exhaust the Ollama semaphore entirely so any accidental sharing would
    # deadlock a non-ollama call routed through the same helper.
    limit = CONFIG["ollama_max_concurrent"]
    held = [await _OLLAMA_ASYNC_SEMAPHORE.acquire() for _ in range(limit)]
    try:
        prov = get_provider("groq")
        assert prov is not None
        client = ProviderClient()
        result = await asyncio.wait_for(
            client._call_openai_compat(
                prov, "some-model", [{"role": "user", "content": "hi"}],
                0.7, 128, None,
            ),
            timeout=2.0,
        )
        assert result.content == "stub-response"
    finally:
        for _ in held:
            _OLLAMA_ASYNC_SEMAPHORE.release()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
