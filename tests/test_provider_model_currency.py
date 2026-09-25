"""Groq / Cerebras model names must be ones the providers still serve.

Found 2026-09-25 (real calls + each provider's live /models list):
  * Cerebras now serves only `gpt-oss-120b` and `qwen-3.8-27b`
    ("zai-glm-4.7 is archived and unavailable" -> HTTP 404).
  * Groq now serves `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
    `qwen/qwen3.8-27b` (llama-3.3-70b-versatile -> "does not exist" 404).
Every content/research/orchestration call tried the dead names first, paying a
failed HTTP round-trip before reaching a working provider.
"""
import pytest

from core.inference import model_catalog as mc
from core.inference.llm_providers import PROVIDERS
from core.inference.model_pool import MODEL_POOL

LIVE = {
    "cerebras": {"gpt-oss-120b", "qwen-3.8-27b"},
    "groq": {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"},
}
RETIRED = {
    "cerebras": {"zai-glm-4.7", "gemma-4-31b"},
    "groq": {"llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768",
             "gemma2-9b-it", "deepseek-r1-distill-llama-70b", "qwen/qwen3-32b",
             "meta-llama/llama-4-scout-17b-16e-instruct"},
}


@pytest.fixture(autouse=True)
def _fresh_catalog():
    mc.reload_catalog()
    yield
    mc.reload_catalog()


@pytest.mark.parametrize("slug", ["cerebras", "groq"])
def test_provider_definition_uses_live_models(slug):
    p = PROVIDERS[slug]
    assert p.default_model in LIVE[slug]
    assert set(p.models) <= LIVE[slug]


@pytest.mark.parametrize("slug", ["cerebras", "groq"])
def test_yaml_catalog_only_lists_live_models(slug):
    assert set(mc.get_catalog()[slug].models) <= LIVE[slug]


@pytest.mark.parametrize("slug", ["cerebras", "groq"])
def test_fallback_catalog_only_lists_live_models(slug):
    providers, _ = mc._load_fallback()
    assert set(providers[slug].models) <= LIVE[slug]


def test_domain_chains_never_name_a_retired_or_unknown_model():
    catalog = mc.get_catalog()
    for name, dom in mc.get_domains().items():
        for slug, model in dom.chain:
            if slug in RETIRED:
                assert model not in RETIRED[slug], f"domain {name} still uses retired {slug}:{model}"
                assert model in catalog[slug].models, f"domain {name}: {slug}:{model} not in catalog"


def test_model_pool_never_names_a_retired_model():
    for logical, backends in MODEL_POOL.items():
        for slug, model in backends:
            if slug in RETIRED:
                assert model not in RETIRED[slug], f"pool '{logical}' still uses retired {slug}:{model}"


@pytest.mark.parametrize("slug,tier", [
    ("cerebras", "heavy"), ("cerebras", "reasoning"), ("cerebras", "council"),
    ("cerebras", "fast"), ("groq", "fast"), ("groq", "agentic"),
    ("groq", "reasoning"), ("groq", "heavy"), ("groq", "council"),
])
def test_tiers_the_retired_models_served_still_resolve(slug, tier):
    assert mc.select_model(slug, tier) in LIVE[slug]
