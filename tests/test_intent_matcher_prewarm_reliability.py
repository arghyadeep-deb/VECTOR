"""IntentMatcher client reuse — one lazily-built ollama.Client per matcher.

Before this change `_embed_sync` constructed a fresh `ollama.Client` for every
embedding call (N bootstrap embeds + one per query). These tests use a fake
`ollama.Client` that counts constructions — no real Ollama or network access —
and pin: one construction per matcher across bootstrap + queries, laziness,
per-instance (not module-level) ownership, exactly-once under concurrent
worker threads, and that a failed constructor is retried rather than cached.
"""
from __future__ import annotations

import asyncio
import contextlib
import itertools
import random
import re
import sys
import time
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.intent_matcher import (
    EMBED_ABORT_CONSECUTIVE_FAILURES,
    EMBED_RETRY_PASSES,
    IntentMatcher,
)


def _vec(text: str) -> list[float]:
    rnd = random.Random(text)
    return [rnd.random() for _ in range(768)]


def _counting_ollama(*, fail_first: int = 0, ctor_delay: float = 0.0):
    """Return (fake Client class, state). `state["attempts"]` counts every
    constructor call; `state["built"]` lists the instances that were
    successfully constructed. The first `fail_first` attempts raise.
    `ctor_delay` widens the race window between concurrent first callers."""
    attempt_counter = itertools.count(1)
    state: dict = {"attempts": 0, "built": [], "prompts": []}

    class _Client:
        def __init__(self, *a, **k):
            n = next(attempt_counter)
            state["attempts"] = max(state["attempts"], n)
            if ctor_delay:
                time.sleep(ctor_delay)
            if n <= fail_first:
                raise RuntimeError("ollama client construction failed")
            state["built"].append(self)

        def embeddings(self, model=None, prompt=""):
            state["prompts"].append(prompt)
            return {"embedding": _vec(prompt)}

    return _Client, state


def _matcher(n: int = 5) -> IntentMatcher:
    m = IntentMatcher("data/intent_examples.json")
    m._examples = [{"text": f"example {i}", "district": "research", "task_type": "search_web"} for i in range(n)]
    return m


def _failure_ollama(
    *, fail_prompts=(), fail_prompt_calls=None, zero_prompts=(), fail_first_calls: int = 0, vector_fn=_vec
):
    state = {"calls": [], "prompt_calls": {}}
    fail_prompt_calls = fail_prompt_calls or {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def embeddings(self, model=None, prompt=""):
            state["calls"].append(prompt)
            state["prompt_calls"][prompt] = state["prompt_calls"].get(prompt, 0) + 1
            if (
                len(state["calls"]) <= fail_first_calls
                or prompt in fail_prompts
                or state["prompt_calls"][prompt] <= fail_prompt_calls.get(prompt, 0)
            ):
                raise RuntimeError("embedding failed")
            if prompt in zero_prompts:
                return {"embedding": [0.0] * 768}
            return {"embedding": vector_fn(prompt)}

    return _Client, state


# ── Acceptance: one client across bootstrap + several match() calls ───────

@pytest.mark.asyncio
async def test_bootstrap_and_queries_construct_the_client_exactly_once():
    m = _matcher(5)
    client_cls, state = _counting_ollama()
    with patch("ollama.Client", client_cls):
        await m.prewarm()
        await m._init_task
        for q in ("query one", "query two", "query three"):
            await m.match(q, wait_timeout=None)
    assert len(state["prompts"]) == 5 + 3, "sanity: every bootstrap and query embed hit the client"
    assert len(state["built"]) == 1, f"expected one client construction, saw {len(state['built'])}"
    assert state["attempts"] == 1


# ── Acceptance: lazy — constructing the matcher makes no ollama call ──────

def test_constructing_matcher_makes_no_ollama_call():
    client_cls, state = _counting_ollama()
    with patch("ollama.Client", client_cls):
        m = _matcher(3)
    assert state["attempts"] == 0 and state["prompts"] == []
    assert m._client is None


# ── Acceptance: per-instance ownership, no module-level sharing ───────────

@pytest.mark.asyncio
async def test_each_matcher_instance_builds_its_own_single_client():
    m1, m2 = _matcher(3), _matcher(3)
    client_cls, state = _counting_ollama()
    with patch("ollama.Client", client_cls):
        await m1.match("query a", wait_timeout=None)
        await m2.match("query b", wait_timeout=None)
        await m1.match("query c", wait_timeout=None)
        await m2.match("query d", wait_timeout=None)
    assert len(state["built"]) == 2, "one client per matcher instance"
    assert m1._client is not m2._client
    assert m1._client in state["built"] and m2._client in state["built"]


# ── Acceptance: exactly one construction under concurrency ────────────────

@pytest.mark.asyncio
async def test_single_client_under_gathered_prewarm_and_match():
    m = _matcher(5)
    client_cls, state = _counting_ollama(ctor_delay=0.05)
    with patch("ollama.Client", client_cls):
        await asyncio.gather(
            m.prewarm(), m.prewarm(),
            m.match("query a", wait_timeout=None),
            m.match("query b", wait_timeout=None),
        )
        await m._init_task
    assert len(state["built"]) == 1
    assert state["attempts"] == 1


@pytest.mark.asyncio
async def test_single_client_when_worker_threads_race_on_first_use():
    m = _matcher(5)
    client_cls, state = _counting_ollama(ctor_delay=0.05)
    with patch("ollama.Client", client_cls):
        # bootstrap (its embeds run via to_thread) racing direct worker-thread embeds
        await asyncio.gather(
            m.prewarm(),
            asyncio.to_thread(m._embed_sync, "query a"),
            asyncio.to_thread(m._embed_sync, "query b"),
            asyncio.to_thread(m._embed_sync, "query c"),
        )
        await m._init_task
    assert len(state["built"]) == 1
    assert state["attempts"] == 1, "racing first callers must not each construct a client"


# ── Acceptance: a constructor failure is not cached forever ───────────────

@pytest.mark.asyncio
async def test_constructor_failure_is_retried_on_the_next_embed():
    m = _matcher(3)
    client_cls, state = _counting_ollama(fail_first=1)
    with patch("ollama.Client", client_cls):
        first = await m._embed("query a")
        assert first is None, "the failed attempt is contained by _embed"
        assert state["attempts"] == 1 and state["built"] == [] and m._client is None

        second = await m._embed("query b")
        assert second is not None and len(second) == 768
        assert state["attempts"] == 2 and len(state["built"]) == 1

        third = await m._embed("query c")
        assert third is not None
    assert state["attempts"] == 2, "once built, the client is reused, not rebuilt"


def test_constructor_failure_propagates_from_embed_sync_and_leaves_no_client():
    m = _matcher(1)
    client_cls, state = _counting_ollama(fail_first=1)
    with patch("ollama.Client", client_cls):
        with pytest.raises(RuntimeError):
            m._embed_sync("query a")
        assert m._client is None
        assert m._embed_sync("query b") is not None
    assert state["attempts"] == 2 and len(state["built"]) == 1


@pytest.mark.asyncio
async def test_failed_example_is_never_cached_or_matched_and_zero_query_is_rejected():
    m = _matcher(3)
    m.set_threshold(0.0)

    def orthogonal_vec(prompt: str) -> list[float]:
        vector = [0.0] * 768
        vector[int(prompt.rsplit(" ", 1)[-1])] = 1.0
        return vector

    client_cls, state = _failure_ollama(
        fail_prompt_calls={"example 1": 1 + EMBED_RETRY_PASSES},
        zero_prompts={"zero query"},
        vector_fn=orthogonal_vec,
    )
    with patch("ollama.Client", client_cls):
        await m._ensure_embeddings_loaded()
        assert state["calls"].count("example 1") == 1 + EMBED_RETRY_PASSES
        assert "example 1" not in m._embedding_cache
        assert await m.match("example 1") is None
        assert any(m._embedding_cache["example 1"])

        assert await m.match("zero query") is None

    assert m._embeddings is not None and m._embeddings[1] is None
    assert all(vector is None or any(vector) for vector in m._embeddings)
    assert all(any(vector) for vector in m._embedding_cache.values())


@pytest.mark.asyncio
async def test_partial_failure_is_degraded_but_ready_examples_still_match():
    m = _matcher(3)
    client_cls, _ = _failure_ollama(fail_prompts={"example 1"})
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    try:
        with patch("ollama.Client", client_cls):
            await m._ensure_embeddings_loaded()
            assert await m.match("example 1") is None
            result = await m.match("example 0")
    finally:
        logger.remove(sink_id)

    assert result is not None and result["type"] == "search_web"
    assert any("bootstrap degraded" in message for message in messages)
    assert {
        "examples_loaded", "embeddings_cached", "similarity_threshold", "model"
    } <= m.get_stats().keys()
    assert m.get_stats().items() >= {
        "ready": True,
        "degraded": True,
        "embedded_count": 2,
        "failed_count": 1,
        "bootstrap_state": "degraded",
    }.items()


@pytest.mark.asyncio
async def test_transient_failures_are_retried_and_recover_all_examples():
    m = _matcher(3)
    client_cls, state = _failure_ollama(fail_first_calls=2)
    with patch("ollama.Client", client_cls):
        assert await m._ensure_embeddings_loaded() is True

    stats = m.get_stats()
    assert stats["embedded_count"] == 3 and stats["failed_count"] == 0
    assert stats["ready"] is True and stats["degraded"] is False
    assert len(state["calls"]) == 5


@pytest.mark.asyncio
async def test_all_failures_are_bounded_and_publish_no_embedding_list():
    n = 3
    m = _matcher(n)
    client_cls, state = _failure_ollama(fail_prompts={f"example {i}" for i in range(n)})
    with patch("ollama.Client", client_cls):
        assert await m._ensure_embeddings_loaded() is False
        assert await m.match("example 0") is None

    assert m._embeddings is None
    assert not m._embedding_cache
    assert len(state["calls"]) <= n * (1 + EMBED_RETRY_PASSES)
    assert m.get_stats().items() >= {
        "ready": False,
        "degraded": True,
        "embedded_count": 0,
        "failed_count": n,
        "bootstrap_state": "failed",
    }.items()


def test_cosine_similarity_zero_norm_is_safe_under_numpy_path():
    m = _matcher(1)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        similarity = m._cosine_similarity([0.0] * 768, _vec("nonzero"))
    assert similarity == 0.0
    assert not caught


# ── Bounded bootstrap: wall-clock budget + consecutive-failure abort ──────
# Fake clients only: no real Ollama, no network. `block` is a real (short)
# time.sleep inside the client so the budget is exercised against real elapsed
# time; the longest test here runs well under a second.

def _bounded_ollama(*, block: float = 0.0, ok_calls: int = 0):
    """Fake Client: the first `ok_calls` embeddings succeed, every later call
    raises a timeout-style error. Each call first blocks `block` seconds."""
    state: dict = {"calls": []}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def embeddings(self, model=None, prompt=""):
            state["calls"].append(prompt)
            if block:
                time.sleep(block)
            if len(state["calls"]) > ok_calls:
                raise TimeoutError("timed out")
            return {"embedding": _vec(prompt)}

    return _Client, state


@contextlib.contextmanager
def _captured_logs():
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        yield messages
    finally:
        logger.remove(sink_id)


def _summary_lines(messages: list[str]) -> list[str]:
    """The per-attempt completion summary is the only line carrying `elapsed=`."""
    return [message for message in messages if "elapsed=" in message]


@pytest.mark.asyncio
async def test_always_timeout_client_aborts_after_consecutive_failures():
    n = 200
    m = _matcher(n)
    client_cls, state = _bounded_ollama()  # every call times out
    with _captured_logs() as messages, patch("ollama.Client", client_cls):
        assert await m._ensure_embeddings_loaded() is False
        assert await m.match("example 0") is None

    assert len(state["calls"]) <= EMBED_ABORT_CONSECUTIVE_FAILURES * (1 + EMBED_RETRY_PASSES)
    assert len(state["calls"]) < n
    assert m._embeddings is None and not m._embedding_cache
    stats = m.get_stats()
    assert stats["bootstrap_state"] == "failed"
    assert stats["embedded_count"] == 0 and stats["failed_count"] == n
    assert stats["bootstrap_stop_reason"] == "abort"
    # Failure is contained: the shared task finished cleanly, nothing unretrieved.
    assert m._init_task.done() and not m._init_task.cancelled()
    assert m._init_task.exception() is None
    summaries = _summary_lines(messages)
    assert len(summaries) == 1
    assert f"failed={n}" in summaries[0] and "embedded=0" in summaries[0]
    assert "stop=abort" in summaries[0]


@pytest.mark.asyncio
async def test_slow_client_stops_at_budget_and_keeps_embedded_examples():
    n, block, budget = 10, 0.1, 0.3
    m = _matcher(n)
    m._bootstrap_budget_seconds = budget
    client_cls, state = _bounded_ollama(block=block, ok_calls=10**9)
    with patch("ollama.Client", client_cls):
        t0 = time.perf_counter()
        assert await m._ensure_embeddings_loaded() is True
        wall = time.perf_counter() - t0

    assert wall < budget + block + 0.3, "attempt must end within budget plus one call (plus scheduling slack)"
    stats = m.get_stats()
    assert 3 <= stats["embedded_count"] <= 4, "about budget / block examples get embedded"
    assert stats["failed_count"] == n - stats["embedded_count"]
    assert len(state["calls"]) == stats["embedded_count"], "no calls are made after the budget is spent"
    assert stats["bootstrap_state"] == "degraded" and stats["degraded"] is True
    assert stats["ready"] is True
    assert stats["bootstrap_stop_reason"] == "budget"
    assert budget <= stats["bootstrap_elapsed_seconds"] < budget + block + 0.3
    # Embedded examples are real vectors, the rest are None.
    real = [v for v in m._embeddings if v is not None]
    assert len(real) == stats["embedded_count"] and all(len(v) == 768 for v in real)
    assert m._embeddings[: len(real)] == real, "examples are embedded in order; the tail is what got dropped"


@pytest.mark.asyncio
async def test_abort_after_partial_success_keeps_embedded_examples():
    n, ok = 20, 3
    m = _matcher(n)
    client_cls, state = _bounded_ollama(ok_calls=ok)
    with patch("ollama.Client", client_cls):
        assert await m._ensure_embeddings_loaded() is True

    stats = m.get_stats()
    assert stats["embedded_count"] == ok and stats["failed_count"] == n - ok
    assert stats["bootstrap_state"] == "degraded" and stats["bootstrap_stop_reason"] == "abort"
    assert len(state["calls"]) == ok + EMBED_ABORT_CONSECUTIVE_FAILURES
    assert [v is not None for v in m._embeddings] == [True] * ok + [False] * (n - ok)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["ready", "degraded", "failed", "budget", "abort", "no_examples"])
async def test_exactly_one_summary_line_per_attempt(scenario):
    m = _matcher(0 if scenario == "no_examples" else 6)
    if scenario == "no_examples":
        client_cls, _ = _bounded_ollama(ok_calls=10**9)
    elif scenario == "ready":
        client_cls, _ = _bounded_ollama(ok_calls=10**9)
    elif scenario == "degraded":
        client_cls, _ = _failure_ollama(fail_prompts={"example 2"})
    elif scenario == "failed":
        client_cls, _ = _failure_ollama(fail_prompts={f"example {i}" for i in range(6)})
    elif scenario == "budget":
        m._bootstrap_budget_seconds = 0.0
        client_cls, _ = _bounded_ollama(ok_calls=10**9)
    else:
        client_cls, _ = _bounded_ollama()
    with _captured_logs() as messages, patch("ollama.Client", client_cls):
        await m._ensure_embeddings_loaded()
        await m.match("example 0")  # later requests must not log another bootstrap summary
        await m.prewarm()
        await m._init_task

    summaries = _summary_lines(messages)
    assert len(summaries) == 1, summaries
    stats = m.get_stats()
    match = re.search(r"embedded=(\d+) failed=(\d+) elapsed=(\d+\.\d+)s", summaries[0])
    assert match, summaries[0]
    assert int(match.group(1)) == stats["embedded_count"]
    assert int(match.group(2)) == stats["failed_count"]
    assert float(match.group(3)) == pytest.approx(stats["bootstrap_elapsed_seconds"], abs=0.006)
    if scenario == "no_examples":
        assert (stats["embedded_count"], stats["failed_count"]) == (0, 0)
        assert stats["bootstrap_state"] == "failed" and stats["bootstrap_stop_reason"] == "no_examples"


def test_stats_expose_bootstrap_elapsed_and_stop_reason_additively():
    m = _matcher(2)
    before = m.get_stats()
    assert before["bootstrap_elapsed_seconds"] is None and before["bootstrap_stop_reason"] is None
    assert {
        "examples_loaded", "embeddings_cached", "similarity_threshold", "model", "ready",
        "degraded", "embedded_count", "failed_count", "bootstrap_state",
    } <= before.keys()

    client_cls, _ = _bounded_ollama(ok_calls=10**9)
    with patch("ollama.Client", client_cls):
        assert asyncio.run(m._ensure_embeddings_loaded()) is True
    after = m.get_stats()
    assert after["bootstrap_state"] == "ready" and after["bootstrap_stop_reason"] == "complete"
    assert isinstance(after["bootstrap_elapsed_seconds"], float) and after["bootstrap_elapsed_seconds"] >= 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("ends_by", ["budget", "abort"])
async def test_no_partial_list_is_observable_when_bootstrap_is_bounded(ends_by):
    n = 12
    m = _matcher(n)
    if ends_by == "budget":
        m._bootstrap_budget_seconds = 0.1
        client_cls, _ = _bounded_ollama(block=0.03, ok_calls=10**9)
    else:
        client_cls, _ = _bounded_ollama(block=0.01, ok_calls=3)
    observed: list = []
    with patch("ollama.Client", client_cls):
        await m.prewarm()
        while not m._init_task.done():
            observed.append(None if m._embeddings is None else len(m._embeddings))
            await asyncio.sleep(0.005)

    assert observed and set(observed) <= {None}, f"partial list visible while running: {set(observed)}"
    assert m.get_stats()["bootstrap_stop_reason"] == ends_by
    assert m._embeddings is not None and len(m._embeddings) == n, "published whole, once, at the end"
