"""
Model Pool — logical model names mapped to ordered (provider, model_id) backends.

When a logical model is requested and one provider hits its rate limit, VECTOR
automatically continues with the same model on the next configured provider.

Usage:
    from core.inference.model_pool import is_logical_model, get_backends, mark_cooldown

    if is_logical_model("kimi-k2.7-code"):
        for slug, model_id in get_backends("kimi-k2.7-code"):
            ...  # try each in priority order
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timedelta, timezone
from loguru import logger

# Ordered (provider_slug, provider_model_id) per logical model.
# Priority: free/cheapest first; local Ollama last (large models are slow locally).
MODEL_POOL: dict[str, list[tuple[str, str]]] = {

    # ── Kimi K2 (Moonshot) ─────────────────────────────────────────────────────
    "kimi-k2.7-code": [
        ("cloudflare", "@cf/moonshotai/kimi-k2.7-code"),    # FREE Cloudflare-hosted
        ("nvidia",     "moonshotai/kimi-k2.6"),              # free NIM credits
        ("openrouter", "moonshot/kimi-k2.7-code"),
    ],
    "kimi-k2.6": [
        ("cloudflare", "@cf/moonshotai/kimi-k2.6"),
        ("nvidia",     "moonshotai/kimi-k2.6"),
        ("openrouter", "moonshot/kimi-k2.6"),
    ],

    # ── GLM (ZhipuAI / ZAI) ────────────────────────────────────────────────────
    "glm-5.2": [
        ("cloudflare", "@cf/zai/glm-5.2"),                   # FREE Cloudflare-hosted
        ("zai",        "glm-4.7-flash"),                     # Z.ai free signup
        ("nvidia",     "zai/glm-5.1"),                       # free NIM credits
        ("openrouter", "zai/glm-5.2"),
        ("llm7",       "glm-4"),                             # anonymous fallback
    ],

    # ── DeepSeek V4 ────────────────────────────────────────────────────────────
    "deepseek-v4-pro": [
        ("nvidia",     "deepseek/deepseek-v4-pro"),           # free NIM credits
        ("deepseek",   "deepseek-v4-pro"),
        ("cloudflare", "@cf/deepseek/deepseek-v4-pro"),
        ("openrouter", "deepseek/deepseek-v4-pro"),
    ],
    "deepseek-v4-flash": [
        ("nvidia",     "deepseek/deepseek-v4-flash"),
        ("deepseek",   "deepseek-v4-flash"),
        ("cloudflare", "@cf/deepseek/deepseek-v4-flash"),
        ("openrouter", "deepseek/deepseek-v4-flash"),
    ],

    # ── Llama 3.3 70B ──────────────────────────────────────────────────────────
    "llama-3.3-70b": [
        ("groq",       "llama-3.3-70b-versatile"),            # free quota, fastest
        ("cerebras",   "llama3.3-70b"),                       # very fast
        ("cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
        ("nvidia",     "meta/llama-3.3-70b-instruct"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
        ("ollama",     "llama3.3:70b"),                       # local last resort
    ],

    # ── DeepSeek R1 — 671B distill, chain-of-thought reasoning ──────────────
    "deepseek-r1": [
        ("openrouter", "deepseek/deepseek-r1:free"),          # FREE on OpenRouter
        ("deepseek",   "deepseek-reasoner"),                  # cheap paid fallback
        ("groq",       "deepseek-r1-distill-llama-70b"),      # fast distilled variant
        ("nvidia",     "deepseek/deepseek-r1"),
        ("ollama",     "deepseek-r1:14b"),                    # local small variant
    ],

    # ── DeepSeek V3 — 685B, best general open model ───────────────────────────
    "deepseek-v3": [
        ("openrouter", "deepseek/deepseek-v3:free"),          # FREE on OpenRouter
        ("deepseek",   "deepseek-chat"),                      # direct API fallback
        ("nvidia",     "deepseek/deepseek-v3"),
        ("cloudflare", "@cf/deepseek/deepseek-v3"),
    ],

    # ── Qwen3 235B MoE — huge but only 22B active ────────────────────────────
    "qwen3-235b": [
        ("openrouter", "qwen/qwen3-235b-a22b:free"),          # FREE on OpenRouter
        ("nvidia",     "qwen/qwen3-235b-a22b"),
    ],

    # ── Nemotron 3 Ultra — NVIDIA's 550B MoE, 1M context ─────────────────────
    "nemotron-3-ultra": [
        ("openrouter", "nvidia/nemotron-3-ultra-550b"),       # FREE on OpenRouter
        ("nvidia",     "nvidia/nemotron-3-ultra-550b"),       # free NIM credits
        ("cloudflare", "@cf/nvidia/nemotron-3-ultra"),
    ],

    # ── Nex-N2-Pro — Qwen3.5-based 397B MoE, agentic ─────────────────────────
    "nex-n2-pro": [
        ("openrouter", "nex-agi/nex-n2-pro"),                 # FREE on OpenRouter
    ],

    # ── Cohere North Mini Code — 30B MoE, 256K, coding ────────────────────────
    "north-mini-code": [
        ("openrouter", "cohere/north-mini-code"),             # FREE on OpenRouter
        ("openrouter", "cohere/north-mini-code-1-0"),         # versioned alias
    ],

    # ── Nemotron Safety — 4B guardrail / content safety ───────────────────────
    "nemotron-safety": [
        ("openrouter", "nvidia/nemotron-3.5-content-safety"), # FREE on OpenRouter
        ("nvidia",     "nvidia/nemotron-3.5-content-safety"),
    ],

    # ── Nemotron Rerank VL — multimodal reranking for visual RAG ──────────────
    "nemotron-rerank-vl": [
        ("openrouter", "nvidia/llama-nemotron-rerank-vl-1b-v2"),  # FREE on OpenRouter
        ("nvidia",     "nvidia/llama-nemotron-rerank-vl-1b-v2"),
    ],

    # ── Qwen3 30B ──────────────────────────────────────────────────────────────
    "qwen3-30b": [
        ("cloudflare", "@cf/qwen/qwen3-30b-a3b-fp8"),         # FREE Cloudflare-hosted
        ("nvidia",     "qwen/qwen3-30b-a3b"),
        ("openrouter", "qwen/qwen3-30b-a3b"),
        ("ollama",     "qwen3:30b-a3b"),
    ],

    # ── Gemma 4 ────────────────────────────────────────────────────────────────
    "gemma-4-27b": [
        ("cloudflare", "@cf/google/gemma-4-26b-a4b-it"),      # FREE Cloudflare-hosted
        ("nvidia",     "google/gemma-4-27b"),
        ("ollama",     "gemma4:e2b"),
    ],

    # ── MiniMax M3 ─────────────────────────────────────────────────────────────
    "minimax-m3": [
        ("cloudflare", "@cf/minimax/m3"),
        ("nvidia",     "minimax/minimax-m3"),
    ],

    # ── GPT OSS 120B ───────────────────────────────────────────────────────────
    "gpt-oss-120b": [
        ("cloudflare", "@cf/openai/gpt-oss-120b"),
        ("nvidia",     "openai/gpt-oss-120b"),
        ("openrouter", "openai/gpt-oss-120b"),
    ],

    # ── Mistral Medium ─────────────────────────────────────────────────────────
    "mistral-medium": [
        ("nvidia",     "mistralai/mistral-medium-3"),
        ("mistral",    "mistral-medium-latest"),
        ("openrouter", "mistralai/mistral-medium"),
    ],
}

# ── Provider cooldown tracker ──────────────────────────────────────────────────
# Maps provider_slug -> datetime when cooldown expires (UTC)
_COOLDOWNS: dict[str, datetime] = {}


def is_logical_model(name: str) -> bool:
    """True if `name` is a logical alias in MODEL_POOL (not a raw model ID)."""
    return name in MODEL_POOL


def mark_cooldown(provider_slug: str, seconds: int = 120) -> None:
    """Mark a provider as rate-limited for `seconds` seconds."""
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    _COOLDOWNS[provider_slug] = until
    logger.warning(
        "[VECTOR][model_pool] {} rate-limited — cooling down {}s",
        provider_slug, seconds,
    )


def _is_cooling_down(provider_slug: str) -> bool:
    until = _COOLDOWNS.get(provider_slug)
    if until is None:
        return False
    if datetime.now(timezone.utc) >= until:
        _COOLDOWNS.pop(provider_slug, None)
        return False
    return True


def get_backends(
    logical_name: str,
    configured_only: bool = True,
) -> list[tuple[str, str]]:
    """
    Return ordered (provider_slug, model_id) pairs for a logical model name.
    Skips providers that are in cooldown or (when configured_only=True) lack API keys.
    """
    from core.inference.llm_providers import get_provider

    result = []
    for slug, model_id in MODEL_POOL.get(logical_name, []):
        if _is_cooling_down(slug):
            logger.debug("[VECTOR][model_pool] {} in cooldown, skipping for {}", slug, logical_name)
            continue
        if configured_only:
            prov = get_provider(slug)
            if prov is None or not prov.is_configured:
                continue
        result.append((slug, model_id))
    return result


def cooldown_status() -> dict[str, str]:
    """Return remaining cooldown seconds per provider (for diagnostics)."""
    now = datetime.now(timezone.utc)
    return {
        slug: f"{int((until - now).total_seconds())}s remaining"
        for slug, until in list(_COOLDOWNS.items())
        if until > now
    }


if __name__ == "__main__":
    # Verify pool structure and cooldown logic
    assert is_logical_model("kimi-k2.7-code"), "kimi-k2.7-code must be in pool"
    assert is_logical_model("nemotron-3-ultra"), "nemotron-3-ultra must be in pool"
    assert not is_logical_model("gpt-4o"), "raw model IDs are not logical names"
    assert len(MODEL_POOL) >= 10

    # Cooldown test
    mark_cooldown("nvidia", seconds=30)
    assert _is_cooling_down("nvidia"), "nvidia should be in cooldown"
    backends_no_nvidia = get_backends("kimi-k2.7-code", configured_only=False)
    assert not any(s == "nvidia" for s, _ in backends_no_nvidia), "cooled-down provider not filtered"

    # Status
    status = cooldown_status()
    assert "nvidia" in status

    print(f"OK model_pool.py -- {len(MODEL_POOL)} logical models registered")
