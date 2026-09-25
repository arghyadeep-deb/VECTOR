"""A provider host that does not resolve must fail over at once, not after 3s of backoff.

Found 2026-09-25: github_models' base URL (models.inference.ai.azure.com) no longer
exists in DNS. `_call_with_retry` treated `[Errno 11001] getaddrinfo failed` like a
transient error and slept 1s + 2s before every fallback, so every domain chain that
starts with github_models paid ~3s of dead time per call.
"""
import pytest

from core.inference import provider_client as pc
from core.inference.llm_providers import PROVIDERS


class _Result:
    content = "ok"


@pytest.fixture
def client(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    c = pc.ProviderClient()
    c._sleeps = sleeps
    return c


async def _run(client, errors):
    """Drive _call_with_retry with a scripted sequence of failures then success."""
    calls = []

    async def scripted(*_a, **_k):
        calls.append(1)
        if len(calls) <= len(errors):
            raise Exception(errors[len(calls) - 1])
        return _Result()

    client._call = scripted
    prov = PROVIDERS["github_models"]
    try:
        await client._call_with_retry(prov, "m", [{"role": "user", "content": "x"}], 0.0, 8, None)
        outcome = "ok"
    except Exception as e:  # noqa: BLE001
        outcome = str(e)
    return len(calls), outcome


@pytest.mark.parametrize("msg", [
    "[Errno 11001] getaddrinfo failed",
    "[Errno -2] Name or service not known",
    "Temporary failure in name resolution",
])
async def test_dns_failure_fails_over_immediately(client, msg):
    attempts, outcome = await _run(client, [msg] * 3)
    assert attempts == 1
    assert client._sleeps == []
    assert "getaddrinfo" in outcome or "name" in outcome.lower()


async def test_ordinary_transient_error_is_still_retried(client):
    attempts, outcome = await _run(client, ["HTTP 503: upstream hiccup"])
    assert attempts == 2
    assert outcome == "ok"
    assert client._sleeps == [1.0]
