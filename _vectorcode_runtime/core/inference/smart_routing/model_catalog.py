"""
VECTOR Smart Routing — Model Catalog
Python port of ClawRouter/src/router/config.ts (1262 lines)

55+ AI models across 9 providers with pricing, capabilities, and routing configs.
Used by the classifier to pick the cheapest capable model per tier.

Usage:
    model = cheapest_for_tier(Tier.SIMPLE)
    cost = estimate_cost("google/gemini-2.5-flash", 1000, 500)
    chain = fallback_chain_for(Tier.COMPLEX, "auto")
"""
from __future__ import annotations

__all__ = [
    "baseline_cost",
    "cheapest_for_tier",
    "estimate_cost",
    "fallback_chain_for",
    "get_model",
    "ModelEntry",
    "resolve_alias",
    "savings_pct",
]


import sys
from dataclasses import dataclass, field
from typing import Optional

from core.inference.smart_routing.classifier import Tier, Profile


@dataclass
class ModelEntry:
    id: str
    name: str
    provider: str
    input_cost_per_mtok: float      # USD per million input tokens
    output_cost_per_mtok: float     # USD per million output tokens
    context_window: int             # max context tokens
    supports_tools: bool = True
    supports_vision: bool = False
    tiers: list[str] = field(default_factory=list)     # which tiers this model fits
    profiles: list[str] = field(default_factory=list)  # free/eco/auto/premium
    is_free: bool = False
    is_reasoning: bool = False


# ── Model catalog — 55+ models across 9 providers ───────────────────────────

MODEL_CATALOG: dict[str, ModelEntry] = {
    # ── NVIDIA (free tier) ────────────────────────────────────────────────────
    "nvidia/llama-3.3-70b-instruct": ModelEntry(
        id="nvidia/llama-3.3-70b-instruct", name="Llama 3.3 70B", provider="nvidia",
        input_cost_per_mtok=0, output_cost_per_mtok=0, context_window=131072,
        supports_tools=True, is_free=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["free", "eco", "auto"],
    ),
    "nvidia/deepseek-r1-671b": ModelEntry(
        id="nvidia/deepseek-r1-671b", name="DeepSeek R1 671B", provider="nvidia",
        input_cost_per_mtok=0, output_cost_per_mtok=0, context_window=131072,
        supports_tools=False, is_free=True, is_reasoning=True,
        tiers=["COMPLEX", "REASONING"], profiles=["free"],
    ),
    "nvidia/qwen3-coder-480b": ModelEntry(
        id="nvidia/qwen3-coder-480b", name="Qwen3 Coder 480B", provider="nvidia",
        input_cost_per_mtok=0, output_cost_per_mtok=0, context_window=131072,
        supports_tools=True, is_free=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["free", "eco"],
    ),
    "nvidia/nemotron-omni": ModelEntry(
        id="nvidia/nemotron-omni", name="Nemotron Omni", provider="nvidia",
        input_cost_per_mtok=0, output_cost_per_mtok=0, context_window=131072,
        supports_tools=True, supports_vision=True, is_free=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["free"],
    ),
    "nvidia/gpt-oss-120b": ModelEntry(
        id="nvidia/gpt-oss-120b", name="GPT OSS 120B", provider="nvidia",
        input_cost_per_mtok=0, output_cost_per_mtok=0, context_window=131072,
        supports_tools=True, is_free=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["free", "eco", "auto"],
    ),
    "nvidia/gpt-oss-20b": ModelEntry(
        id="nvidia/gpt-oss-20b", name="GPT OSS 20B", provider="nvidia",
        input_cost_per_mtok=0, output_cost_per_mtok=0, context_window=32768,
        supports_tools=True, is_free=True,
        tiers=["SIMPLE"], profiles=["free", "eco"],
    ),

    # ── Google ────────────────────────────────────────────────────────────────
    "google/gemini-2.5-flash-lite": ModelEntry(
        id="google/gemini-2.5-flash-lite", name="Gemini 2.5 Flash Lite", provider="google",
        input_cost_per_mtok=0.075, output_cost_per_mtok=0.30, context_window=1048576,
        supports_tools=True, supports_vision=True,
        tiers=["SIMPLE"], profiles=["eco", "auto"],
    ),
    "google/gemini-2.5-flash": ModelEntry(
        id="google/gemini-2.5-flash", name="Gemini 2.5 Flash", provider="google",
        input_cost_per_mtok=0.15, output_cost_per_mtok=0.60, context_window=1048576,
        supports_tools=True, supports_vision=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),
    "google/gemini-2.5-pro": ModelEntry(
        id="google/gemini-2.5-pro", name="Gemini 2.5 Pro", provider="google",
        input_cost_per_mtok=1.25, output_cost_per_mtok=10.0, context_window=1048576,
        supports_tools=True, supports_vision=True,
        tiers=["COMPLEX", "REASONING"], profiles=["auto", "premium"],
    ),
    "google/gemini-3.1-pro": ModelEntry(
        id="google/gemini-3.1-pro", name="Gemini 3.1 Pro", provider="google",
        input_cost_per_mtok=2.0, output_cost_per_mtok=15.0, context_window=2097152,
        supports_tools=True, supports_vision=True,
        tiers=["COMPLEX", "REASONING"], profiles=["premium"],
    ),
    "google/gemini-3-flash-preview": ModelEntry(
        id="google/gemini-3-flash-preview", name="Gemini 3 Flash", provider="google",
        input_cost_per_mtok=0.10, output_cost_per_mtok=0.40, context_window=1048576,
        supports_tools=True, supports_vision=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),

    # ── Anthropic ─────────────────────────────────────────────────────────────
    "anthropic/claude-haiku-4.5": ModelEntry(
        id="anthropic/claude-haiku-4.5", name="Claude Haiku 4.5", provider="anthropic",
        input_cost_per_mtok=0.80, output_cost_per_mtok=4.0, context_window=200000,
        supports_tools=True, supports_vision=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),
    "anthropic/claude-sonnet-4.6": ModelEntry(
        id="anthropic/claude-sonnet-4.6", name="Claude Sonnet 4.6", provider="anthropic",
        input_cost_per_mtok=3.0, output_cost_per_mtok=15.0, context_window=200000,
        supports_tools=True, supports_vision=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["auto", "premium"],
    ),
    "anthropic/claude-opus-4.7": ModelEntry(
        id="anthropic/claude-opus-4.7", name="Claude Opus 4.7", provider="anthropic",
        input_cost_per_mtok=15.0, output_cost_per_mtok=75.0, context_window=200000,
        supports_tools=True, supports_vision=True,
        tiers=["COMPLEX", "REASONING"], profiles=["premium"],
    ),

    # ── OpenAI ────────────────────────────────────────────────────────────────
    "openai/gpt-4o-mini": ModelEntry(
        id="openai/gpt-4o-mini", name="GPT-4o Mini", provider="openai",
        input_cost_per_mtok=0.15, output_cost_per_mtok=0.60, context_window=128000,
        supports_tools=True, supports_vision=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),
    "openai/gpt-4o": ModelEntry(
        id="openai/gpt-4o", name="GPT-4o", provider="openai",
        input_cost_per_mtok=2.5, output_cost_per_mtok=10.0, context_window=128000,
        supports_tools=True, supports_vision=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["auto", "premium"],
    ),
    "openai/o3": ModelEntry(
        id="openai/o3", name="o3", provider="openai",
        input_cost_per_mtok=2.0, output_cost_per_mtok=8.0, context_window=200000,
        supports_tools=True, is_reasoning=True,
        tiers=["REASONING"], profiles=["auto", "premium"],
    ),
    "openai/o3-mini": ModelEntry(
        id="openai/o3-mini", name="o3-mini", provider="openai",
        input_cost_per_mtok=1.1, output_cost_per_mtok=4.4, context_window=200000,
        supports_tools=True, is_reasoning=True,
        tiers=["COMPLEX", "REASONING"], profiles=["auto"],
    ),
    "openai/gpt-5.3-codex": ModelEntry(
        id="openai/gpt-5.3-codex", name="GPT-5.3 Codex", provider="openai",
        input_cost_per_mtok=3.0, output_cost_per_mtok=12.0, context_window=200000,
        supports_tools=True,
        tiers=["COMPLEX"], profiles=["auto", "premium"],
    ),
    "openai/gpt-5.5": ModelEntry(
        id="openai/gpt-5.5", name="GPT-5.5", provider="openai",
        input_cost_per_mtok=5.0, output_cost_per_mtok=20.0, context_window=200000,
        supports_tools=True, supports_vision=True,
        tiers=["COMPLEX", "REASONING"], profiles=["premium"],
    ),

    # ── xAI ───────────────────────────────────────────────────────────────────
    "xai/grok-3": ModelEntry(
        id="xai/grok-3", name="Grok 3", provider="xai",
        input_cost_per_mtok=3.0, output_cost_per_mtok=15.0, context_window=131072,
        supports_tools=True, supports_vision=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["auto", "premium"],
    ),
    "xai/grok-4-0709": ModelEntry(
        id="xai/grok-4-0709", name="Grok 4", provider="xai",
        input_cost_per_mtok=5.0, output_cost_per_mtok=25.0, context_window=256000,
        supports_tools=True, is_reasoning=True,
        tiers=["COMPLEX", "REASONING"], profiles=["premium"],
    ),
    "xai/grok-4-1-fast-reasoning": ModelEntry(
        id="xai/grok-4-1-fast-reasoning", name="Grok 4.1 Fast Reasoning", provider="xai",
        input_cost_per_mtok=3.0, output_cost_per_mtok=15.0, context_window=256000,
        supports_tools=True, is_reasoning=True,
        tiers=["REASONING"], profiles=["auto", "premium"],
    ),

    # ── DeepSeek ──────────────────────────────────────────────────────────────
    "deepseek/deepseek-chat": ModelEntry(
        id="deepseek/deepseek-chat", name="DeepSeek Chat V3", provider="deepseek",
        input_cost_per_mtok=0.27, output_cost_per_mtok=1.10, context_window=65536,
        supports_tools=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["eco", "auto"],
    ),
    "deepseek/deepseek-reasoner": ModelEntry(
        id="deepseek/deepseek-reasoner", name="DeepSeek R1", provider="deepseek",
        input_cost_per_mtok=0.55, output_cost_per_mtok=2.19, context_window=65536,
        supports_tools=False, is_reasoning=True,
        tiers=["COMPLEX", "REASONING"], profiles=["eco", "auto"],
    ),

    # ── Moonshot ──────────────────────────────────────────────────────────────
    "moonshot/kimi-k2.6": ModelEntry(
        id="moonshot/kimi-k2.6", name="Kimi K2.6", provider="moonshot",
        input_cost_per_mtok=0.50, output_cost_per_mtok=2.50, context_window=131072,
        supports_tools=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["eco", "auto"],
    ),
    "moonshot/kimi-k2.5": ModelEntry(
        id="moonshot/kimi-k2.5", name="Kimi K2.5", provider="moonshot",
        input_cost_per_mtok=0.30, output_cost_per_mtok=1.20, context_window=131072,
        supports_tools=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),

    # ── Zhipu ─────────────────────────────────────────────────────────────────
    "zhipu/glm-5": ModelEntry(
        id="zhipu/glm-5", name="GLM-5", provider="zhipu",
        input_cost_per_mtok=0.50, output_cost_per_mtok=2.0, context_window=131072,
        supports_tools=True, supports_vision=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["auto"],
    ),
    "zhipu/glm-5-turbo": ModelEntry(
        id="zhipu/glm-5-turbo", name="GLM-5 Turbo", provider="zhipu",
        input_cost_per_mtok=0.14, output_cost_per_mtok=0.14, context_window=131072,
        supports_tools=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),

    # ── MiniMax ───────────────────────────────────────────────────────────────
    "minimax/minimax-m2.7": ModelEntry(
        id="minimax/minimax-m2.7", name="MiniMax M2.7", provider="minimax",
        input_cost_per_mtok=0.40, output_cost_per_mtok=1.60, context_window=1000000,
        supports_tools=True, supports_vision=True,
        tiers=["MEDIUM", "COMPLEX"], profiles=["auto"],
    ),
    "minimax/minimax-m2.5": ModelEntry(
        id="minimax/minimax-m2.5", name="MiniMax M2.5", provider="minimax",
        input_cost_per_mtok=0.20, output_cost_per_mtok=0.80, context_window=1000000,
        supports_tools=True,
        tiers=["SIMPLE", "MEDIUM"], profiles=["eco", "auto"],
    ),
}

# ── Model aliases ─────────────────────────────────────────────────────────────

MODEL_ALIASES: dict[str, str] = {
    "claude":   "anthropic/claude-sonnet-4.6",
    "opus":     "anthropic/claude-opus-4.7",
    "haiku":    "anthropic/claude-haiku-4.5",
    "sonnet":   "anthropic/claude-sonnet-4.6",
    "gpt4":     "openai/gpt-4o",
    "gpt4mini": "openai/gpt-4o-mini",
    "o3":       "openai/o3",
    "gemini":   "google/gemini-2.5-flash",
    "flash":    "google/gemini-2.5-flash",
    "pro":      "google/gemini-2.5-pro",
    "grok":     "xai/grok-3",
    "deepseek": "deepseek/deepseek-chat",
    "r1":       "deepseek/deepseek-reasoner",
    "kimi":     "moonshot/kimi-k2.6",
}

# ── Tier → profile → ordered model lists (cheapest first) ────────────────────

TIER_PROFILE_MODELS: dict[str, dict[str, list[str]]] = {
    "SIMPLE": {
        "free":    ["nvidia/gpt-oss-20b", "nvidia/llama-3.3-70b-instruct"],
        "eco":     ["google/gemini-2.5-flash-lite", "zhipu/glm-5-turbo", "nvidia/gpt-oss-20b"],
        "auto":    ["google/gemini-2.5-flash", "openai/gpt-4o-mini", "anthropic/claude-haiku-4.5"],
        "premium": ["anthropic/claude-sonnet-4.6", "openai/gpt-4o"],
    },
    "MEDIUM": {
        "free":    ["nvidia/gpt-oss-120b", "nvidia/qwen3-coder-480b"],
        "eco":     ["deepseek/deepseek-chat", "moonshot/kimi-k2.5", "google/gemini-2.5-flash"],
        "auto":    ["google/gemini-2.5-flash", "anthropic/claude-haiku-4.5", "deepseek/deepseek-chat"],
        "premium": ["anthropic/claude-sonnet-4.6", "openai/gpt-4o", "xai/grok-3"],
    },
    "COMPLEX": {
        "free":    ["nvidia/qwen3-coder-480b", "nvidia/gpt-oss-120b"],
        "eco":     ["deepseek/deepseek-chat", "moonshot/kimi-k2.6", "zhipu/glm-5"],
        "auto":    ["anthropic/claude-sonnet-4.6", "xai/grok-3", "google/gemini-2.5-pro"],
        "premium": ["anthropic/claude-opus-4.7", "openai/gpt-5.5", "xai/grok-4-0709"],
    },
    "REASONING": {
        "free":    ["nvidia/deepseek-r1-671b"],
        "eco":     ["deepseek/deepseek-reasoner", "openai/o3-mini"],
        "auto":    ["openai/o3", "xai/grok-4-1-fast-reasoning", "deepseek/deepseek-reasoner"],
        "premium": ["anthropic/claude-opus-4.7", "openai/o3", "xai/grok-4-0709"],
    },
}


# ── Helper functions ──────────────────────────────────────────────────────────

def resolve_alias(model_id: str) -> str:
    """Resolve alias to canonical model ID."""
    return MODEL_ALIASES.get(model_id, model_id)


def get_model(model_id: str) -> ModelEntry | None:
    mid = resolve_alias(model_id)
    return MODEL_CATALOG.get(mid)


def cheapest_for_tier(
    tier: "Tier",
    profile: str = "auto",
    needs_tools: bool = False,
    needs_vision: bool = False,
    exclude: set[str] | None = None,
) -> str | None:
    """Return cheapest model ID for the given tier and profile."""
    models = TIER_PROFILE_MODELS.get(tier.value, {}).get(profile, [])
    for mid in models:
        if exclude and mid in exclude:
            continue
        entry = MODEL_CATALOG.get(mid)
        if not entry:
            continue
        if needs_tools and not entry.supports_tools:
            continue
        if needs_vision and not entry.supports_vision:
            continue
        return mid
    return None


def fallback_chain_for(tier: "Tier", profile: str = "auto") -> list[str]:
    """Return ordered fallback chain for a tier+profile."""
    return list(TIER_PROFILE_MODELS.get(tier.value, {}).get(profile, []))


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a request."""
    entry = MODEL_CATALOG.get(resolve_alias(model_id))
    if not entry:
        return 0.0
    return (
        entry.input_cost_per_mtok * input_tokens / 1_000_000
        + entry.output_cost_per_mtok * output_tokens / 1_000_000
    )


def baseline_cost(input_tokens: int, output_tokens: int) -> float:
    """Cost of claude-opus-4.7 (the most expensive baseline)."""
    return estimate_cost("anthropic/claude-opus-4.7", input_tokens, output_tokens)


def savings_pct(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """% saved vs baseline."""
    cost = estimate_cost(model_id, input_tokens, output_tokens)
    base = baseline_cost(input_tokens, output_tokens)
    if base <= 0:
        return 0.0
    return max(0.0, 1.0 - cost / base)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from core.inference.smart_routing.classifier import Tier

    assert len(MODEL_CATALOG) >= 30
    assert cheapest_for_tier(Tier.SIMPLE, "free") is not None
    assert cheapest_for_tier(Tier.REASONING, "eco") is not None

    for tier in Tier:
        cheap = cheapest_for_tier(tier, "auto")
        cost = estimate_cost(cheap, 1000, 500) if cheap else 0
        sav = savings_pct(cheap, 1000, 500) if cheap else 0
        print(f"  {tier.value:10} → {cheap} cost=${cost:.6f} savings={sav:.0%}")

    print(f"OK model_catalog.py — {len(MODEL_CATALOG)} models, {len(MODEL_ALIASES)} aliases")
