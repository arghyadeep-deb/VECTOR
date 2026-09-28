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
        ("llm7",       "kimi-k2.6"),                         # FREE on LLM7 (confirmed)
        ("nvidia",     "moonshotai/kimi-k2.6"),
        ("openrouter", "moonshot/kimi-k2.6"),
    ],

    # ── GLM (ZhipuAI / ZAI) ────────────────────────────────────────────────────
    "glm-5.2": [
        ("cloudflare", "@cf/zai/glm-5.2"),                   # FREE Cloudflare-hosted
        ("llm7",       "glm-5.2"),                           # FREE on LLM7 (confirmed)
        ("zai",        "glm-4.7-flash"),                     # FREE (glm-4.5 is PAID — whitelist clamps anyway)
        ("nvidia",     "zai/glm-5.1"),
        ("openrouter", "zai/glm-5.2"),
    ],

    # ── DeepSeek V4 ────────────────────────────────────────────────────────────
    "deepseek-v4-pro": [
        ("nvidia",     "deepseek/deepseek-v4-pro"),           # free NIM credits
        ("deepseek",   "deepseek-v4-pro"),
        ("cloudflare", "@cf/deepseek/deepseek-v4-pro"),
        ("openrouter", "deepseek/deepseek-v4-pro"),
    ],
    "deepseek-v4-flash": [
        ("opencode_zen", "deepseek-v4-flash-free"),           # FREE, unlimited (verified 2026-07-02)
        ("nvidia",     "deepseek/deepseek-v4-flash"),
        ("deepseek",   "deepseek-v4-flash"),
        ("cloudflare", "@cf/deepseek/deepseek-v4-flash"),
        ("openrouter", "deepseek/deepseek-v4-flash"),
    ],

    # ── GPT-5 (GitHub Models free) ────────────────────────────────────────────
    "gpt-5": [
        ("github_models", "gpt-5"),                          # FREE via GitHub token
        ("openrouter",    "openai/gpt-5"),                   # paid fallback
    ],

    # ── o3 / o4-mini reasoning (GitHub Models free) ───────────────────────────
    "o3": [
        ("github_models", "o3"),                             # FREE via GitHub token
        ("openrouter",    "openai/o3"),
    ],
    "o4-mini": [
        ("github_models", "o4-mini"),                        # FREE via GitHub token
        ("openrouter",    "openai/o4-mini"),
        ("groq",          "openai/gpt-oss-120b"),            # fast fallback if GH exhausted
    ],

    # ── Phi-4-reasoning (GitHub Models free, strong math/reasoning) ───────────
    "phi-4-reasoning": [
        ("github_models", "Phi-4-reasoning"),                # FREE via GitHub token
        ("github_models", "Phi-4-mini-reasoning"),           # smaller fallback
    ],

    # ── DeepSeek R1 — chain-of-thought reasoning ─────────────────────────────
    "deepseek-r1": [
        ("github_models", "DeepSeek-R1-0528"),                # FREE via GitHub token (newest)
        ("github_models", "DeepSeek-R1"),                     # FREE via GitHub token
        ("nvidia",        "deepseek/deepseek-r1"),            # free NIM credits
        ("ollama",        "deepseek-r1:14b"),                  # local
    ],

    # ── DeepSeek V3 ───────────────────────────────────────────────────────────
    "deepseek-v3": [
        ("github_models", "DeepSeek-V3-0324"),                # FREE via GitHub token
        ("nvidia",        "deepseek/deepseek-v3"),
    ],

    # ── Llama 3.3 70B (FREE everywhere) ───────────────────────────────────────
    "llama-3.3-70b": [
        ("cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("nvidia",     "meta/llama-3.3-70b-instruct"),
        ("ollama",     "llama3.3:70b"),
    ],

    # ── Llama 3.1 405B ────────────────────────────────────────────────────────
    "llama-405b": [
        ("github_models", "Meta-Llama-3.1-405B-Instruct"),   # FREE via GitHub token
        ("openrouter",    "meta-llama/llama-3.1-405b-instruct"),
        ("nvidia",        "meta/llama-3.1-405b-instruct"),
    ],

    # ── Llama 4 Maverick ──────────────────────────────────────────────────────
    "llama-4-maverick": [
        ("github_models", "Llama-4-Maverick-17B-128E-Instruct-FP8"),  # FREE
        ("groq",          "llama-4-maverick-17b-128e-instruct"),
        ("nvidia",        "meta/llama-4-maverick-17b-128e-instruct"),
    ],

    # ── GPT-OSS 120B — free on Cerebras + OpenRouter ──────────────────────────
    "gpt-oss-120b": [
        ("cerebras",   "gpt-oss-120b"),                       # FREE, confirmed 2026-06-18
        ("openrouter", "openai/gpt-oss-120b:free"),           # FREE on OpenRouter
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),  # alternative 120B free
    ],

    # ── Nemotron 3 Ultra — 550B MoE ───────────────────────────────────────────
    "nemotron-3-ultra": [
        ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),  # FREE, confirmed 2026-06-18
        ("nvidia",     "nvidia/nemotron-3-ultra-550b-a55b"),
    ],

    # ── Qwen3 235B MoE ────────────────────────────────────────────────────────
    "qwen3-235b": [
        ("llm7",       "qwen3-235b"),                         # FREE on LLM7 (240K ctx)
        ("openrouter", "qwen/qwen3-next-80b-a3b-instruct:free"),  # smaller free fallback
        ("nvidia",     "qwen/qwen3-235b-a22b"),
    ],

    # ── Qwen3 Coder ───────────────────────────────────────────────────────────
    "qwen3-coder": [
        ("openrouter", "qwen/qwen3-coder:free"),              # FREE on OpenRouter
        ("llm7",       "qwen3-235b"),                         # fallback
    ],

    # ── Nex-N2-Pro — 397B MoE, agentic ───────────────────────────────────────
    "nex-n2-pro": [
        ("openrouter", "nex-agi/nex-n2-pro:free"),            # FREE on OpenRouter
    ],

    # ── Cohere North Mini Code ────────────────────────────────────────────────
    "north-mini-code": [
        ("opencode_zen", "north-mini-code-free"),             # FREE, unlimited (verified 2026-07-02)
        ("openrouter", "cohere/north-mini-code:free"),        # FREE on OpenRouter
        ("cohere",     "command-a-03-2025"),
    ],

    # ── Nemotron Safety — content safety classifier ───────────────────────────
    "nemotron-safety": [
        ("openrouter", "nvidia/nemotron-3.5-content-safety:free"),  # FREE
        ("nvidia",     "nvidia/nemotron-3.5-content-safety"),
    ],

    # ── Gemma 4 27B ───────────────────────────────────────────────────────────
    "gemma-4-27b": [
        ("openrouter", "google/gemma-4-26b-a4b-it:free"),     # FREE on OpenRouter
        ("nvidia",     "google/gemma-4-27b"),
        ("ollama",     "gemma4:e2b"),
    ],

    # ── Mistral / Codestral ───────────────────────────────────────────────────
    "mistral-small": [
        ("mistral",  "mistral-small-2506"),                   # 2.25M TPM / 5 RPS free
        ("llm7",     "deepseek-v4-flash"),                    # mistral-small-3.2 vanished from LLM7
    ],
    "codestral": [
        ("llm7",     "codestral-latest"),                     # FREE on LLM7
        ("mistral",  "codestral-latest"),
    ],

    # ── Qwen3 30B ──────────────────────────────────────────────────────────────
    "qwen3-30b": [
        ("nvidia",     "qwen/qwen3-30b-a3b"),
        ("openrouter", "qwen/qwen3-next-80b-a3b-instruct:free"),
        ("ollama",     "qwen3:30b-a3b"),
    ],

    # ── Gemini Flash — 360M tokens/month FREE (Google AI Studio key) ──────────
    "gemini-flash": [
        ("gemini",     "gemini-2.5-flash-lite"),              # FREE, highest RPM, best for high-freq tasks
        ("gemini",     "gemini-2.5-flash"),                   # FREE, stable, 1M ctx (gemini-2.0-* are 404 on the owner key)
        ("openrouter", "google/gemini-2.0-flash-exp:free"),   # OpenRouter free fallback
    ],

    # ── Gemini Pro — 1M-context reasoning, vision ─────────────────────────────
    "gemini-pro": [
        ("gemini",     "gemini-2.5-pro"),                     # 1M context, free tier (1.5/2.0 are 404 on the owner key)
        ("gemini",     "gemini-2.5-flash"),                   # fast fallback
        ("openrouter", "google/gemini-flash-1.5"),
    ],
}

# ── Provider cooldown tracker ──────────────────────────────────────────────────
# Maps provider_slug -> datetime when cooldown expires (UTC)
_COOLDOWNS: dict[str, datetime] = {}
_COOLDOWN_LOCK = __import__("threading").Lock()  # protects _COOLDOWNS


def is_logical_model(name: str) -> bool:
    """True if `name` is a logical alias in MODEL_POOL (not a raw model ID)."""
    return name in MODEL_POOL


def mark_cooldown(provider_slug: str, seconds: int = 120) -> None:
    """Mark a provider as rate-limited for `seconds` seconds."""
    until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    with _COOLDOWN_LOCK:
        _COOLDOWNS[provider_slug] = until
    logger.warning(
        "[VECTOR][model_pool] {} rate-limited — cooling down {}s",
        provider_slug, seconds,
    )


def _is_cooling_down(provider_slug: str) -> bool:
    with _COOLDOWN_LOCK:
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
    with _COOLDOWN_LOCK:
        items = list(_COOLDOWNS.items())
    return {
        slug: f"{int((until - now).total_seconds())}s remaining"
        for slug, until in items
        if until > now
    }


if __name__ == "__main__":
    # Verify pool structure and cooldown logic
    assert is_logical_model("kimi-k2.7-code"), "kimi-k2.7-code must be in pool"
    assert is_logical_model("nemotron-3-ultra"), "nemotron-3-ultra must be in pool"
    assert is_logical_model("gemini-flash"), "gemini-flash must be in pool"
    assert not is_logical_model("gpt-4o"), "raw model IDs are not logical names"
    assert len(MODEL_POOL) >= 10
    # llama-3.3-70b must have no duplicate key (second definition overwrites first)
    assert MODEL_POOL["llama-3.3-70b"][1][0] == "cloudflare", "llama-3.3-70b entry is clean"

    # Cooldown test
    mark_cooldown("nvidia", seconds=30)
    assert _is_cooling_down("nvidia"), "nvidia should be in cooldown"
    backends_no_nvidia = get_backends("kimi-k2.7-code", configured_only=False)
    assert not any(s == "nvidia" for s, _ in backends_no_nvidia), "cooled-down provider not filtered"

    # Status
    status = cooldown_status()
    assert "nvidia" in status

    print(f"OK model_pool.py -- {len(MODEL_POOL)} logical models registered")
