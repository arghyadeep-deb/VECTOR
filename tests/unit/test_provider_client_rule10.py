"""CLAUDE.md Rule 10 ("Free-tier only at runtime — no paid Anthropic/OpenAI
keys at runtime") runtime enforcement in ProviderClient._call().

Real code paths only: the real _call() method, the real _call_with_retry()
retry/failover loop, the real KeyPool. Only the actual HTTP-issuing driver
methods (_call_anthropic/_call_openai_compat) are ever mocked, and every
test that could otherwise reach them if the gate regressed mocks them
explicitly -- no test in this file can make a real network call even under
a real regression.
"""
from __future__ import annotations

import pytest

from core.inference.key_pool import reset_pools
from core.inference.llm_providers import get_provider
from core.inference.provider_client import ProviderClient, Rule10PolicyRefusal


@pytest.fixture(autouse=True)
def _isolated_keys(monkeypatch):
    """Every test in this file gets a clean slate: no real key configured,
    the override explicitly unset, and no pool state leaked from another
    test's monkeypatched ANTHROPIC_API_KEY/OPENAI_API_KEY."""
    monkeypatch.delenv("VECTOR_ALLOW_PAID_ANTHROPIC_OPENAI", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_pools()
    yield
    reset_pools()


@pytest.mark.asyncio
async def test_anthropic_call_blocked_by_default(monkeypatch):
    client = ProviderClient()
    prov = get_provider("anthropic")
    # Even if the gate regressed and let this through, this must not be
    # able to reach the network.
    called = {"hit": False}

    async def _would_be_real_call(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("driver must never be reached when Rule 10 blocks")

    monkeypatch.setattr(client, "_call_anthropic", _would_be_real_call)

    with pytest.raises(Rule10PolicyRefusal, match="rule10"):
        await client._call(prov, "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.7, 100, None)
    assert called["hit"] is False


@pytest.mark.asyncio
async def test_openai_call_blocked_by_default(monkeypatch):
    client = ProviderClient()
    prov = get_provider("openai")
    called = {"hit": False}

    async def _would_be_real_call(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("driver must never be reached when Rule 10 blocks")

    monkeypatch.setattr(client, "_call_openai_compat", _would_be_real_call)

    with pytest.raises(Rule10PolicyRefusal, match="rule10"):
        await client._call(prov, "gpt-4o-mini", [{"role": "user", "content": "hi"}], 0.7, 100, None)
    assert called["hit"] is False


@pytest.mark.asyncio
async def test_override_env_var_lets_the_call_through(monkeypatch):
    """With the explicit opt-in set, the Rule 10 gate must not fire -- the
    call should reach the real driver dispatch (mocked here so no network
    call happens), not raise Rule10PolicyRefusal."""
    monkeypatch.setenv("VECTOR_ALLOW_PAID_ANTHROPIC_OPENAI", "1")
    client = ProviderClient()
    prov = get_provider("anthropic")

    async def _fake_call_anthropic(*args, **kwargs):
        return "reached-the-driver"

    monkeypatch.setattr(client, "_call_anthropic", _fake_call_anthropic)
    result = await client._call(prov, "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.7, 100, None)
    assert result == "reached-the-driver"


@pytest.mark.asyncio
async def test_retry_fails_over_after_exactly_one_attempt_with_zero_key_pool(monkeypatch):
    """2026-09-23 regression test for the real bug an independent review
    found: a naive "put '403' in the message" fix collided with
    _call_with_retry()'s OWN is_key_err classifier, which suppresses the
    non-retryable raise when the key pool has more than one key -- so the
    deterministic policy block got retried against every configured key
    anyway. Rule10PolicyRefusal is now caught and re-raised FIRST, before
    any of that string-matching logic runs. This test's pool is empty
    (size 0, since ANTHROPIC_API_KEY is unset by the autouse fixture) --
    see test_retry_fails_over_after_exactly_one_attempt_with_one_real_key
    below for the genuine single-key (size 1) case, and the multi-key case
    further down."""
    client = ProviderClient()
    prov = get_provider("anthropic")
    attempts = {"count": 0}

    async def _always_blocked(*args, **kwargs):
        attempts["count"] += 1
        raise Rule10PolicyRefusal("[VECTOR][rule10] refusing paid provider 'anthropic' at runtime")

    monkeypatch.setattr(client, "_call", _always_blocked)
    with pytest.raises(Rule10PolicyRefusal):
        await client._call_with_retry(prov, "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.7, 100, None, max_retries=3)
    assert attempts["count"] == 1, "must fail over after exactly one attempt, never retry a policy block"


@pytest.mark.asyncio
async def test_retry_fails_over_after_exactly_one_attempt_with_one_real_key(monkeypatch):
    """2026-09-23 (independent review correctly noted the test above, despite
    its name, exercises a size-0 pool, not size-1): a genuine single-key
    pool, to directly cover the pool.size <= 1 branch of _call_with_retry()'s
    pre-existing is_rl handling too."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-one")
    reset_pools()

    client = ProviderClient()
    prov = get_provider("anthropic")
    attempts = {"count": 0}

    async def _always_blocked(*args, **kwargs):
        attempts["count"] += 1
        raise Rule10PolicyRefusal("[VECTOR][rule10] refusing paid provider 'anthropic' at runtime")

    monkeypatch.setattr(client, "_call", _always_blocked)
    with pytest.raises(Rule10PolicyRefusal):
        await client._call_with_retry(prov, "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.7, 100, None, max_retries=3)
    assert attempts["count"] == 1, "must fail over after exactly one attempt, never retry a policy block"


@pytest.mark.asyncio
async def test_retry_fails_over_after_exactly_one_attempt_with_multi_key_pool(monkeypatch):
    """The exact shape of the real bug: a multi-key pool (comma-separated
    ANTHROPIC_API_KEY) used to make _call_with_retry() treat a Rule 10
    refusal as a rotatable key error and retry it against every key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-one,key-two,key-three")
    reset_pools()

    client = ProviderClient()
    prov = get_provider("anthropic")
    attempts = {"count": 0}

    async def _always_blocked(*args, **kwargs):
        attempts["count"] += 1
        raise Rule10PolicyRefusal("[VECTOR][rule10] refusing paid provider 'anthropic' at runtime")

    monkeypatch.setattr(client, "_call", _always_blocked)
    with pytest.raises(Rule10PolicyRefusal):
        await client._call_with_retry(prov, "claude-sonnet-4-6", [{"role": "user", "content": "hi"}], 0.7, 100, None, max_retries=3)
    assert attempts["count"] == 1, "a multi-key pool must not turn a policy block into 3 retries across keys"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
