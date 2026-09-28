"""Tier-aware model selection + paid-model whitelist guardrail (2026-07-02).

Offline: exercises _model_for_provider/_enforce_whitelist directly — no
network, no provider calls.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inference.provider_client import _model_for_provider, _enforce_whitelist
from core.inference.llm_providers import PROVIDERS
from core.inference.model_catalog import reload_catalog


@pytest.fixture(autouse=True)
def _fresh():
    reload_catalog()
    yield


# ── passthrough (unchanged behavior) ─────────────────────────────────────────

def test_cloud_model_passthrough_verbatim():
    groq = PROVIDERS["groq"]
    assert _model_for_provider(groq, "openai/gpt-oss-120b", "fast") == \
        "openai/gpt-oss-120b"


def test_ollama_gets_requested_local_model():
    ollama = PROVIDERS["ollama"]
    assert _model_for_provider(ollama, "vector-focus", "fast") == "vector-focus"


# ── tier-aware catalog selection (the new capability) ────────────────────────

def test_local_name_plus_tier_yields_catalog_pick():
    cf = PROVIDERS["cloudflare"]
    assert _model_for_provider(cf, "vector-focus", "coding") == \
        "@cf/moonshotai/kimi-k2.7-code"
    assert _model_for_provider(cf, "qwen3:14b", "vision") == \
        "@cf/meta/llama-3.2-11b-vision-instruct"


def test_no_model_yields_tier_pick_not_default():
    groq = PROVIDERS["groq"]
    assert _model_for_provider(groq, None, "fast") == "openai/gpt-oss-20b"
    cerebras = PROVIDERS["cerebras"]
    assert _model_for_provider(cerebras, None, "reasoning") == "gpt-oss-120b"


def test_unknown_tier_falls_back_to_default():
    groq = PROVIDERS["groq"]
    assert _model_for_provider(groq, None, "no_such_tier") == groq.default_model


# ── HARD guardrail: locked providers ─────────────────────────────────────────

def test_opencode_zen_never_emits_paid_model():
    zen = PROVIDERS["opencode_zen"]
    for paid in ("claude-opus-4-8", "gpt-5.5", "claude-fable-5", "gemini-3.5-flash"):
        for tier in ("fast", "coding", "reasoning", "agentic", "no_such_tier"):
            got = _model_for_provider(zen, paid, tier)
            assert got in zen.models, f"{paid}/{tier} leaked '{got}'"


def test_zai_never_emits_paid_model():
    zai = PROVIDERS["zai"]
    for paid in ("glm-4.5", "glm-5.2"):
        got = _model_for_provider(zai, paid, "agentic")
        assert got in zai.models, f"'{paid}' leaked as '{got}'"


def test_enforce_whitelist_direct():
    zen = PROVIDERS["opencode_zen"]
    assert _enforce_whitelist(zen, "gpt-5.5", "coding") == "north-mini-code-free"
    assert _enforce_whitelist(zen, "big-pickle", "reasoning") == "big-pickle"


def test_guardrail_survives_catalog_failure(monkeypatch):
    import core.inference.model_catalog as mc
    monkeypatch.setattr(mc, "select_model",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    zen = PROVIDERS["opencode_zen"]
    got = _model_for_provider(zen, "gpt-5.5", "coding")
    assert got in zen.models          # clamps to default_model, never paid


def test_unlocked_provider_not_clamped():
    groq = PROVIDERS["groq"]
    # groq is not locked — any cloud model name passes (provider 404s handle junk)
    assert _enforce_whitelist(groq, "whatever-model", "fast") == "whatever-model"


if __name__ == "__main__":
    # real test, no mocks
    ok = _model_for_provider(PROVIDERS["opencode_zen"], "gpt-5.5", "coding") in \
        PROVIDERS["opencode_zen"].models
    print("✅ test_provider_selection OK" if ok else "❌ FAILED")
