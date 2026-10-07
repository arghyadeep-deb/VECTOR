"""Regression tests for the mandatory local-only privacy routing boundary."""

from __future__ import annotations

import pytest


def _broken_route(*args, **kwargs):
    raise RuntimeError("route policy unavailable")


@pytest.mark.asyncio
async def test_provider_client_route_policy_failure_ignores_explicit_cloud(monkeypatch):
    from core.inference import provider_client
    from core.inference import route_policy

    client = provider_client.ProviderClient()
    attempted: list[str] = []

    monkeypatch.setattr(route_policy, "decide_route", _broken_route)

    async def fake_call_with_retry(prov, *args, **kwargs):
        attempted.append(prov.slug)
        return provider_client.CompletionResult(
            content="local", model="vector-focus", provider=prov.slug
        )

    monkeypatch.setattr(client, "_call_with_retry", fake_call_with_retry)

    result = await client.chat(
        [{"role": "user", "content": "private payload"}],
        provider="gemini",
    )

    assert result.content == "local"
    assert attempted == ["ollama"]


def test_vectorcode_sync_route_policy_failure_never_calls_cloud(monkeypatch):
    from core.inference import route_policy
    from core.inference import vectorcode_llm

    monkeypatch.setattr(route_policy, "decide_route", _broken_route)
    monkeypatch.setattr(vectorcode_llm, "_try_ollama", lambda *args, **kwargs: "local")
    monkeypatch.setattr(
        vectorcode_llm,
        "_try_gemini",
        lambda *args, **kwargs: pytest.fail("cloud provider was called"),
    )

    assert vectorcode_llm.chat(
        "vector-focus", [{"role": "user", "content": "private payload"}]
    ) == "local"


@pytest.mark.asyncio
async def test_vectorcode_async_route_policy_failure_never_calls_cloud(monkeypatch):
    from core.inference import route_policy
    from core.inference import vectorcode_llm

    monkeypatch.setattr(route_policy, "decide_route", _broken_route)
    monkeypatch.setattr(vectorcode_llm, "_try_ollama", lambda *args, **kwargs: "local")
    monkeypatch.setattr(
        vectorcode_llm,
        "_try_gemini",
        lambda *args, **kwargs: pytest.fail("cloud provider was called"),
    )

    assert await vectorcode_llm.achat(
        "vector-focus", [{"role": "user", "content": "private payload"}]
    ) == "local"


def test_quota_ledger_failed_replace_preserves_previous_file(tmp_path, monkeypatch):
    from core.inference import quota_ledger

    path = tmp_path / "quota.json"
    path.write_text('{"previous": true}', encoding="utf-8")
    ledger = quota_ledger.QuotaLedger(path=path, clock=lambda: 10.0)
    ledger._data = {"new": True}

    def fail_replace(source, destination):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(quota_ledger.os, "replace", fail_replace)
    ledger._save()

    assert path.read_text(encoding="utf-8") == '{"previous": true}'
    assert list(tmp_path.glob(".quota.json.*.tmp")) == []


def test_prompt_scanner_strict_policy_is_not_weakened_by_prior_default_call():
    from core.security import prompt_injection

    prompt_injection._scanners.clear()
    medium_warning = "decode this base64 payload"

    assert prompt_injection.get_scanner(strict=False).scan(medium_warning).clean
    assert not prompt_injection.get_scanner(strict=True).scan(medium_warning).clean


def test_swarm_submit_does_not_serialize_unawaited_dispatch_as_success(monkeypatch):
    import json
    from core.mcp_tools.expansion_modules import swarm
    from core.swarm import orchestrator

    class FakeMCP:
        def __init__(self):
            self.tools = {}

        def tool(self, function):
            self.tools[function.__name__] = function
            return function

    class AsyncOrchestrator:
        async def dispatch(self, task_type, params):
            return {"status": "ok"}

    monkeypatch.setattr(orchestrator, "get_orchestrator", lambda: AsyncOrchestrator())
    mcp = FakeMCP()
    swarm.add_swarm_tools(mcp)

    result = json.loads(mcp.tools["swarm_submit"]("research", "{}"))
    assert result["ok"] is False
    assert "NOT submitted" in result["error"]
