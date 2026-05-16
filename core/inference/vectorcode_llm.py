"""
VectorCode LLM — unified multi-provider LLM router for VECTOR districts.

Wraps ollama_safe (local) and adds cloud provider tiers via vectorcode's
adapter infrastructure. District agents import `chat()` from here instead of
ollama_safe directly. When you add paid API keys, they register here and all
district agents get them automatically — zero code changes needed in districts.

Provider priority chain (always preserves Rule 11 — local first):
  Tier 0 — local:      Ollama → AirLLM → LiteLLM → Gemma.cpp
  Tier 1 — free cloud: Gemini API free tier (15 req/min, 1M tokens/day)
  Tier 2 — paid cloud: Anthropic Claude API  [plug-in when keys added]
                        OpenRouter (300+ models) [plug-in when keys added]
                        AWS Bedrock             [plug-in when keys added]
  Tier 3 — fallback:   cached empty string (never crash)

Usage (drop-in replacement for ollama_safe.chat):
    from core.inference.vectorcode_llm import chat

    result = chat(model="vector-reasoning", messages=[...], timeout=30.0)

For cloud tasks (when local is deliberately skipped):
    result = chat(model="claude-sonnet-4-6", messages=[...], provider="anthropic")
"""
from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG

# ── Provider tier enum ───────────────────────────────────────────────────────

ProviderName = Literal["ollama", "gemini", "anthropic", "openrouter", "bedrock", "auto"]


# ── Token usage tracking (lightweight — no external dep) ─────────────────────

@dataclass
class TokenUsage:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    success: bool = True

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── Per-session cost accumulator ─────────────────────────────────────────────

_usage_lock = threading.Lock()
_session_usage: list[TokenUsage] = []

# Approximate pricing (USD per 1M tokens) — update when you add paid providers
_PRICING: dict[str, dict[str, float]] = {
    "ollama":      {"input": 0.0, "output": 0.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "default":     {"input": 1.0, "output": 3.0},
}


def _estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return max(1, len(text) // 4)


def _calc_cost(model: str, input_tok: int, output_tok: int) -> float:
    pricing = _PRICING.get(model, _PRICING["default"])
    return (input_tok * pricing["input"] + output_tok * pricing["output"]) / 1_000_000


def _record_usage(provider: str, model: str, messages: list[dict],
                  response: str, latency_ms: float, success: bool) -> None:
    input_tok = sum(_estimate_tokens(m.get("content", "")) for m in messages)
    output_tok = _estimate_tokens(response)
    cost = _calc_cost(model, input_tok, output_tok)
    usage = TokenUsage(
        provider=provider, model=model,
        input_tokens=input_tok, output_tokens=output_tok,
        cost_usd=cost, latency_ms=latency_ms, success=success,
    )
    with _usage_lock:
        _session_usage.append(usage)
    if cost > 0:
        logger.debug(
            f"[VECTOR][vc_llm] {provider}/{model}: "
            f"{input_tok}in+{output_tok}out tok, ${cost:.6f}"
        )


def get_session_usage() -> dict:
    """Return aggregated session token usage and costs."""
    with _usage_lock:
        snap = list(_session_usage)
    total_cost = sum(u.cost_usd for u in snap)
    by_provider: dict[str, dict] = {}
    for u in snap:
        if u.provider not in by_provider:
            by_provider[u.provider] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
        by_provider[u.provider]["calls"] += 1
        by_provider[u.provider]["tokens"] += u.total_tokens
        by_provider[u.provider]["cost_usd"] += u.cost_usd
    return {
        "total_calls": len(snap),
        "total_cost_usd": round(total_cost, 6),
        "by_provider": by_provider,
    }


# ── Rate limit state (per provider, in-memory) ───────────────────────────────

@dataclass
class _RateState:
    requests_remaining: int = 9999
    reset_at: float = 0.0
    exhausted: bool = False


_rate_states: dict[str, _RateState] = {}
_rate_lock = threading.Lock()


def _mark_rate_limited(provider: str, retry_after_secs: float = 60.0) -> None:
    with _rate_lock:
        _rate_states[provider] = _RateState(
            requests_remaining=0,
            reset_at=time.time() + retry_after_secs,
            exhausted=True,
        )
    logger.warning(f"[VECTOR][vc_llm] {provider} rate-limited, cooldown {retry_after_secs:.0f}s")


def _is_rate_limited(provider: str) -> bool:
    with _rate_lock:
        state = _rate_states.get(provider)
    if state is None or not state.exhausted:
        return False
    if time.time() >= state.reset_at:
        with _rate_lock:
            _rate_states.pop(provider, None)
        return False
    return True


# ── Provider implementations ──────────────────────────────────────────────────

def _try_ollama(model: str, messages: list[dict], timeout: float) -> str:
    """Tier 0 — local Ollama (always free, always first). Delegates to ollama_safe."""
    from core.inference.ollama_safe import chat as _ollama_chat
    t0 = time.perf_counter()
    result = _ollama_chat(model=model, messages=messages, timeout=timeout)
    if result:
        _record_usage("ollama", model, messages, result,
                      (time.perf_counter() - t0) * 1000, True)
    return result


def _try_gemini(model_hint: str, messages: list[dict], timeout: float) -> str:
    """Tier 1 — Gemini free API. Uses google-generativeai SDK or httpx fallback.

    Free tier: 15 req/min, 1M tokens/day for Flash models.
    Model selection: if model_hint looks local (vector-*), maps to gemini-2.0-flash.
    """
    if _is_rate_limited("gemini"):
        return ""
    api_key = (
        os.getenv("GEMINI_API_KEY")
        or CONFIG.get("api_keys", {}).get("gemini", "")
    )
    if not api_key:
        return ""

    # Map local model names → Gemini equivalents
    gemini_model = _map_to_gemini_model(model_hint)
    prompt = _messages_to_text(messages)
    t0 = time.perf_counter()
    try:
        import httpx
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{gemini_model}:generateContent?key={api_key}"
        )
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = httpx.post(url, json=body, timeout=timeout)
        if resp.status_code == 429:
            _mark_rate_limited("gemini", 60.0)
            return ""
        resp.raise_for_status()
        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if text:
            _record_usage("gemini", gemini_model, messages, text,
                          (time.perf_counter() - t0) * 1000, True)
            logger.info(f"[VECTOR][vc_llm] gemini/{gemini_model} responded ({len(text)} chars)")
        return text
    except Exception as e:
        logger.warning(f"[VECTOR][vc_llm] Gemini failed: {e}")
        return ""


def _try_anthropic(model_hint: str, messages: list[dict], timeout: float) -> str:
    """Tier 2 — Anthropic Claude API (paid). Active when ANTHROPIC_API_KEY is set."""
    if _is_rate_limited("anthropic"):
        return ""
    api_key = (
        os.getenv("ANTHROPIC_API_KEY")
        or CONFIG.get("api_keys", {}).get("anthropic", "")
    )
    if not api_key:
        return ""

    claude_model = _map_to_claude_model(model_hint)
    t0 = time.perf_counter()
    try:
        import anthropic as _sdk
        client = _sdk.Anthropic(api_key=api_key)
        # Extract system prompt if present
        system = ""
        user_msgs = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                user_msgs.append(m)
        kwargs = dict(model=claude_model, max_tokens=4096,
                      messages=user_msgs or [{"role": "user", "content": "Hello"}])
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        text = response.content[0].text if response.content else ""
        if text:
            _record_usage("anthropic", claude_model, messages, text,
                          (time.perf_counter() - t0) * 1000, True)
            logger.info(f"[VECTOR][vc_llm] anthropic/{claude_model} responded ({len(text)} chars)")
        return text
    except Exception as e:
        if "rate" in str(e).lower() or "429" in str(e):
            _mark_rate_limited("anthropic", 60.0)
        logger.warning(f"[VECTOR][vc_llm] Anthropic failed: {e}")
        return ""


def _try_openrouter(model_hint: str, messages: list[dict], timeout: float) -> str:
    """Tier 2 — OpenRouter (300+ models via one API). Paid, set OPENROUTER_API_KEY."""
    if _is_rate_limited("openrouter"):
        return ""
    api_key = (
        os.getenv("OPENROUTER_API_KEY")
        or CONFIG.get("api_keys", {}).get("openrouter", "")
    )
    if not api_key:
        return ""

    # OpenRouter uses OpenAI-compatible API
    or_model = _map_to_openrouter_model(model_hint)
    t0 = time.perf_counter()
    try:
        import httpx
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "HTTP-Referer": "https://github.com/arghyadeep-deb/VECTOR",
                     "X-Title": "VECTOR AI"},
            json={"model": or_model, "messages": messages, "max_tokens": 4096},
            timeout=timeout,
        )
        if resp.status_code == 429:
            _mark_rate_limited("openrouter", 60.0)
            return ""
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        if text:
            _record_usage("openrouter", or_model, messages, text,
                          (time.perf_counter() - t0) * 1000, True)
            logger.info(f"[VECTOR][vc_llm] openrouter/{or_model} responded ({len(text)} chars)")
        return text
    except Exception as e:
        logger.warning(f"[VECTOR][vc_llm] OpenRouter failed: {e}")
        return ""


# ── Model mapping helpers ─────────────────────────────────────────────────────

_GEMINI_MAP = {
    "vector-reasoning": "gemini-2.0-flash",
    "vector-chairman":  "gemini-2.0-flash",
    "vector-deep":      "gemini-2.0-flash",
    "vector-focus":     "gemini-2.0-flash",
    "vector-coder":     "gemini-2.0-flash",
    "vector-fast":      "gemini-2.0-flash",
    "vector-r1":        "gemini-2.0-flash",
    "vector-ambient":   "gemini-2.0-flash",
}

_CLAUDE_MAP = {
    "vector-reasoning": "claude-sonnet-4-6",
    "vector-chairman":  "claude-opus-4-7",
    "vector-deep":      "claude-sonnet-4-6",
    "vector-focus":     "claude-haiku-4-5",
    "vector-coder":     "claude-sonnet-4-6",
    "vector-fast":      "claude-haiku-4-5",
    "vector-r1":        "claude-sonnet-4-6",
    "vector-ambient":   "claude-haiku-4-5",
}

_OPENROUTER_MAP = {
    "vector-reasoning": "anthropic/claude-sonnet-4-6",
    "vector-chairman":  "anthropic/claude-opus-4-7",
    "vector-coder":     "deepseek/deepseek-coder-v2",
    "vector-fast":      "meta-llama/llama-3.1-8b-instruct:free",
    "vector-deep":      "anthropic/claude-sonnet-4-6",
    "vector-r1":        "deepseek/deepseek-r1:free",
}


def _map_to_gemini_model(model_hint: str) -> str:
    return _GEMINI_MAP.get(model_hint, "gemini-2.0-flash")


def _map_to_claude_model(model_hint: str) -> str:
    if model_hint.startswith("claude-"):
        return model_hint
    return _CLAUDE_MAP.get(model_hint, "claude-haiku-4-5")


def _map_to_openrouter_model(model_hint: str) -> str:
    if "/" in model_hint:
        return model_hint
    return _OPENROUTER_MAP.get(model_hint, "anthropic/claude-haiku-4-5")


def _messages_to_text(messages: list[dict]) -> str:
    """Flatten messages to a single prompt string for APIs that need it."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(f"[Context]\n{content}")
        elif role == "assistant":
            parts.append(f"[Assistant]\n{content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


# ── Main chat function — drop-in for ollama_safe.chat() ──────────────────────

def chat(
    model: str,
    messages: list[dict],
    timeout: float = 30.0,
    *,
    provider: ProviderName = "auto",
    allow_cloud: bool = True,
) -> str:
    """Unified LLM call with multi-provider fallback.

    Same signature as ollama_safe.chat() — drop-in replacement.

    Args:
        model:       Ollama model tag OR cloud model ID (e.g. "claude-sonnet-4-6")
        messages:    Standard chat messages list
        timeout:     Per-provider HTTP timeout
        provider:    Force specific provider. "auto" = try local first, cloud as fallback
        allow_cloud: Set False to stay strictly local (same as ollama_safe.chat)

    Returns:
        Response text, or empty string on total failure (never raises).
    """
    if not messages:
        return ""

    # ── Forced provider ──────────────────────────────────────────────────────
    if provider == "gemini":
        return _try_gemini(model, messages, timeout)
    if provider == "anthropic":
        return _try_anthropic(model, messages, timeout)
    if provider == "openrouter":
        return _try_openrouter(model, messages, timeout)
    if provider == "ollama":
        return _try_ollama(model, messages, timeout)

    # ── Auto chain: local first, cloud fallback ──────────────────────────────
    # Tier 0 — local (always)
    result = _try_ollama(model, messages, timeout)
    if result:
        return result

    if not allow_cloud:
        logger.warning(f"[VECTOR][vc_llm] local failed for {model}, cloud disabled")
        return ""

    logger.info(f"[VECTOR][vc_llm] local {model} unavailable — trying cloud providers")

    # Tier 1 — Gemini free (no API key cost)
    result = _try_gemini(model, messages, timeout)
    if result:
        return result

    # Tier 2a — Anthropic paid
    result = _try_anthropic(model, messages, timeout)
    if result:
        return result

    # Tier 2b — OpenRouter paid
    result = _try_openrouter(model, messages, timeout)
    if result:
        return result

    logger.warning(f"[VECTOR][vc_llm] all providers failed for {model}")
    return ""


def chat_stream(
    model: str,
    messages: list[dict],
    timeout: float = 120.0,
    *,
    provider: ProviderName = "auto",
):
    """Streaming version — yields tokens. Falls back to non-streaming on cloud."""
    if provider == "auto" or provider == "ollama":
        # Try local streaming first
        from core.inference.ollama_safe import chat_stream as _ollama_stream
        try:
            yielded = False
            for token in _ollama_stream(model=model, messages=messages, timeout=timeout):
                if token:
                    yielded = True
                    yield token
            if yielded:
                return
        except Exception:
            pass
    # Cloud providers — return as single token (no streaming)
    result = chat(model, messages, timeout, provider=provider)
    if result:
        yield result


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    usage = get_session_usage()
    print(f"[OK] session_usage: calls={usage['total_calls']} cost=${usage['total_cost_usd']}")
    providers_available = {
        "ollama": True,  # always local
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
    }
    print(f"[OK] providers: {providers_available}")
    print(f"[OK] gemini_model_map: {len(_GEMINI_MAP)} entries")
    print(f"[OK] claude_model_map: {len(_CLAUDE_MAP)} entries")
    print("vectorcode_llm.py OK")
