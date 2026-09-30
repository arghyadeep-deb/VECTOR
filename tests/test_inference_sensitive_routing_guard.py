"""Regression tests for the non-negotiable local-only inference gate.

Explicit provider overrides and the security-domain alias used to bypass the
sensitivity check. The route policy also mistook free cloud APIs for local
providers, preventing the documented ordinary cloud routing path.
"""
from __future__ import annotations

import asyncio

from core.inference import route_policy, vectorcode_llm
from core.inference.llm_providers import PROVIDERS
from core.inference.provider_client import CompletionResult, ProviderClient


def test_free_cloud_provider_is_not_treated_as_local(monkeypatch):
    cloud = PROVIDERS["gemini"]
    monkeypatch.setattr(type(cloud), "is_configured", property(lambda self: True))

    plan = route_policy.decide_route("Summarize this ordinary public text")

    assert "gemini" in plan.providers
    assert plan.providers[-1] == "ollama"


def test_sync_explicit_cloud_provider_cannot_bypass_sensitive_gate(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(vectorcode_llm, "_try_gemini", lambda *a, **k: calls.append("gemini") or "cloud")
    monkeypatch.setattr(vectorcode_llm, "_try_ollama", lambda *a, **k: calls.append("ollama") or "local")

    result = vectorcode_llm.chat(
        "vector-focus", [{"role": "user", "content": "ordinary text"}],
        provider="gemini", sensitive=True,
    )

    assert result == "local"
    assert calls == ["ollama"]


def test_async_security_domain_forces_local_even_with_cloud_override(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(vectorcode_llm, "_try_gemini", lambda *a, **k: calls.append("gemini") or "cloud")
    monkeypatch.setattr(vectorcode_llm, "_try_ollama", lambda *a, **k: calls.append("ollama") or "local")

    result = asyncio.run(vectorcode_llm.achat(
        "vector-reasoning", [{"role": "user", "content": "review this"}],
        provider="gemini", domain="security",
    ))

    assert result == "local"
    assert calls == ["ollama"]


def test_provider_client_red_tier_overrides_explicit_cloud_provider(monkeypatch):
    attempted: list[str] = []

    async def fake_call(self, prov, model, messages, temperature, max_tokens, tools):
        attempted.append(prov.slug)
        return CompletionResult(content="local", model=model, provider=prov.slug)

    monkeypatch.setattr(ProviderClient, "_call_with_retry", fake_call)

    result = asyncio.run(ProviderClient().chat(
        [{"role": "user", "content": "perform protected action"}],
        provider="gemini", permission_tier="RED",
    ))

    assert result.provider == "ollama"
    assert attempted == ["ollama"]


def test_provider_client_scans_system_context_for_secrets(monkeypatch):
    attempted: list[str] = []

    async def fake_call(self, prov, model, messages, temperature, max_tokens, tools):
        attempted.append(prov.slug)
        return CompletionResult(content="local", model=model, provider=prov.slug)

    monkeypatch.setattr(ProviderClient, "_call_with_retry", fake_call)

    result = asyncio.run(ProviderClient().chat(
        [
            {"role": "system", "content": "Use API key: protected-value"},
            {"role": "user", "content": "Summarize the context"},
        ],
        provider="gemini",
    ))

    assert result.provider == "ollama"
    assert attempted == ["ollama"]


def test_logical_model_chain_always_terminates_on_ollama(monkeypatch):
    from core.inference import model_pool

    attempted: list[str] = []
    monkeypatch.setattr(model_pool, "is_logical_model", lambda model: model == "test-alias")
    monkeypatch.setattr(model_pool, "get_backends", lambda model: [("gemini", "gemini-2.5-flash")])

    async def fake_call(self, prov, model, messages, temperature, max_tokens, tools):
        attempted.append(prov.slug)
        if prov.slug != "ollama":
            raise RuntimeError("provider unavailable")
        return CompletionResult(content="local", model=model, provider=prov.slug)

    monkeypatch.setattr(ProviderClient, "_call_with_retry", fake_call)

    result = asyncio.run(ProviderClient().chat(
        [{"role": "user", "content": "ordinary public request"}],
        model="test-alias",
    ))

    assert result.provider == "ollama"
    assert attempted[-1] == "ollama"


if __name__ == "__main__":
    raise SystemExit("Run with: pytest tests/test_inference_sensitive_routing_guard.py -v")
