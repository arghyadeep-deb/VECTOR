"""Model catalog — data-driven model selection + domain chains (2026-07-02).

Offline: reads the real YAML but never touches the network.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.inference.model_catalog as mc
from core.inference.model_catalog import (
    get_catalog, get_domains, select_model, is_model_allowed,
    chain_for_domain, domain_local_only, reload_catalog,
)
from core.inference.llm_providers import PROVIDERS, TIER_ROUTING


@pytest.fixture(autouse=True)
def _fresh_catalog():
    reload_catalog()
    yield


# ── parse + cross-checks ─────────────────────────────────────────────────────

def test_catalog_parses_all_13_providers():
    assert len(get_catalog()) >= 13


def test_every_catalog_slug_exists_in_provider_registry():
    for slug in get_catalog():
        assert slug in PROVIDERS, f"catalog slug '{slug}' missing from PROVIDERS"


def test_locked_provider_models_match_registry_whitelist():
    # The YAML whitelist and the LLMProvider.models list must agree, or the
    # guardrail has holes.
    for slug in ("opencode_zen", "zai"):
        cat = get_catalog()[slug]
        assert cat.locked
        for mid in cat.models:
            assert mid in PROVIDERS[slug].models, (
                f"{slug}: catalog model '{mid}' not in LLMProvider.models")


# ── selection ────────────────────────────────────────────────────────────────

def test_select_model_expectations():
    assert select_model("cloudflare", "coding") == "@cf/moonshotai/kimi-k2.7-code"
    assert select_model("nvidia", "vision") == "meta/llama-3.2-90b-vision-instruct"
    assert select_model("cerebras", "reasoning") == "gpt-oss-120b"
    assert select_model("groq", "fast") == "openai/gpt-oss-20b"
    assert select_model("github_models", "coding") == "mistral-ai/Codestral-2501"  # catalog ID format now provider-prefixed, matching GitHub Models' real API naming


def test_heavy_alias_resolves_under_reasoning():
    assert select_model("cerebras", "heavy") == "gpt-oss-120b"


def test_unknown_tier_or_provider_returns_none():
    assert select_model("groq", "no_such_tier") is None
    assert select_model("no_such_provider", "fast") is None


# ── whitelist guardrail ──────────────────────────────────────────────────────

def test_opencode_zen_blocks_paid_models():
    for paid in ("gpt-5.5", "claude-fable-5", "claude-opus-4-8", "gemini-3.5-flash"):
        assert is_model_allowed("opencode_zen", paid) is False
    for free in ("deepseek-v4-flash-free", "big-pickle", "north-mini-code-free"):
        assert is_model_allowed("opencode_zen", free) is True


def test_zai_blocks_paid_models():
    assert is_model_allowed("zai", "glm-4.5") is False
    assert is_model_allowed("zai", "glm-5.2") is False
    assert is_model_allowed("zai", "glm-4.7-flash") is True


def test_openrouter_free_pattern():
    assert is_model_allowed("openrouter", "anthropic/claude-sonnet-5") is False
    assert is_model_allowed("openrouter", "qwen/qwen3-coder:free") is True


def test_uncataloged_provider_is_unrestricted():
    assert is_model_allowed("anthropic", "claude-sonnet-4-6") is True


def test_fallback_keeps_whitelists(monkeypatch):
    # Guardrail must survive a missing/broken YAML.
    monkeypatch.setattr(mc, "_load_from_yaml",
                        lambda: (_ for _ in ()).throw(RuntimeError("no yaml")))
    reload_catalog()
    assert is_model_allowed("opencode_zen", "gpt-5.5") is False
    assert is_model_allowed("zai", "glm-4.5") is False
    assert is_model_allowed("openrouter", "anthropic/claude-sonnet-5") is False


# ── domain chains ────────────────────────────────────────────────────────────

def test_every_domain_chain_terminates_on_local():
    for name, dom in get_domains().items():
        assert dom.chain, f"domain '{name}' has empty chain"
        assert dom.chain[-1][0] == "ollama", (
            f"domain '{name}' must end on ollama (never-crash terminal)")


def test_every_cloud_chain_model_passes_whitelist():
    for name, dom in get_domains().items():
        for prov, model in dom.chain:
            if prov == "ollama":
                continue
            assert is_model_allowed(prov, model), (
                f"domain '{name}': {prov}/{model} violates whitelist")


def test_security_domain_is_local_only():
    assert domain_local_only("security") is True
    assert all(p == "ollama" for p, _ in chain_for_domain("security"))


def test_domains_registered_in_model_pool():
    from core.inference.model_pool import MODEL_POOL
    for name in get_domains():
        assert f"domain:{name}" in MODEL_POOL


def test_chain_fallback_depth():
    # Owner requirement: 3-4 fallbacks. Cloud domains need >= 3 backends
    # before the local terminal.
    for name, dom in get_domains().items():
        if dom.local_only:
            continue
        assert len(dom.chain) >= 4, f"domain '{name}' chain too shallow"


# ── TIER_ROUTING invariants (Step 4 contract) ────────────────────────────────

def test_tier_routing_keys_unchanged():
    expected = {"agentic", "coding", "saas", "reasoning", "summarization",
                "multilingual", "long_context", "vision", "fast", "council",
                "translate", "conversation"}
    assert expected.issubset(set(TIER_ROUTING.keys()))


def test_tier_routing_slugs_exist_and_ollama_last():
    for tier, order in TIER_ROUTING.items():
        for slug in order:
            assert slug in PROVIDERS, f"{tier}: unknown provider '{slug}'"
        assert order[-1] == "ollama", f"{tier}: ollama must be terminal"


if __name__ == "__main__":
    # real test, no mocks
    ok = select_model("cloudflare", "coding") == "@cf/moonshotai/kimi-k2.7-code"
    print("✅ test_model_catalog OK" if ok else "❌ FAILED")
