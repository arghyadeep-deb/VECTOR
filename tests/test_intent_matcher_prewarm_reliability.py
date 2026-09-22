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
import itertools
import random
import sys
import time
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.intent_matcher import EMBED_RETRY_PASSES, IntentMatcher


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
