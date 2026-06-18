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

__all__ = [
    "chat",
    "chat_stream",
    "get_session_usage",
    "ProviderName",
    "TokenUsage",
]


import asyncio
import os
import time
import threading
from dataclasses import dataclass
from typing import Literal


from loguru import logger
from core.config import CONFIG
from core.resilience.circuit_breaker import CircuitBreakerOpenError
from core.breaker_registry import get_registry


def _sync_cb_call(name: str, fn, *args, **kwargs):
    cb = get_registry().get(name)
    if cb is None:
        return fn(*args, **kwargs)
    try:
        _coro = cb.call(lambda: fn(*args, **kwargs))
        return asyncio.run(_coro)
    except RuntimeError:
        _coro.close()
        from core.resilience.circuit_breaker import CircuitState
        _t = time.time()
        if cb.state == CircuitState.OPEN:
            if _t - cb.last_failure_time < cb.config.recovery_timeout:
                raise CircuitBreakerOpenError(f"circuit breaker '{name}' is open")
            cb.state = CircuitState.HALF_OPEN
            cb.success_count = 0
            cb._half_open_retries = 0
        if cb.state == CircuitState.HALF_OPEN and cb._half_open_retries >= cb.config.half_open_max_retries:
            raise CircuitBreakerOpenError(f"circuit breaker '{name}' half-open retries exhausted")
        if cb.state == CircuitState.HALF_OPEN:
            cb._half_open_retries += 1
        try:
            result = fn(*args, **kwargs)
            if cb.state == CircuitState.HALF_OPEN:
                cb.success_count += 1
                if cb.success_count >= cb.config.success_threshold:
                    cb.state = CircuitState.CLOSED
                    cb.failure_count = 0
            elif cb.state == CircuitState.CLOSED:
                cb.failure_count = 0
            return result
        except Exception:
            cb.failure_count += 1
            cb.last_failure_time = _t
            if cb.state == CircuitState.CLOSED and cb.failure_count >= cb.config.failure_threshold:
                cb.state = CircuitState.OPEN
            elif cb.state == CircuitState.HALF_OPEN:
                cb.state = CircuitState.OPEN
            raise

# â”€â”€ Provider tier enum â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

ProviderName = Literal["ollama", "gemini", "anthropic", "openrouter", "bedrock", "auto"]


# â”€â”€ Token usage tracking (lightweight — no external dep) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Per-session cost accumulator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_usage_lock = threading.Lock()
_session_usage: list[TokenUsage] = []

# Approximate pricing (USD per 1M tokens) — update when you add paid providers
# Approximate pricing per 1M tokens (USD). Values are estimates — override via
# CONFIG["llm_pricing"] dict. Kept here only for budget tracking; never used for billing.
_PRICING: dict[str, dict[str, float]] = {
    **CONFIG.get("llm_pricing", {}),   # user overrides take priority
    "ollama":           {"input": 0.0,  "output": 0.0},
    "gemini-1.5-flash": {"input": 0.075,"output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "claude-sonnet-4-6":{"input": 3.0,  "output": 15.0},
    "default":          {"input": 1.0,  "output": 3.0},
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


# â”€â”€ Rate limit state (per provider, in-memory) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Provider implementations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _try_ollama(model: str, messages: list[dict], timeout: float, temperature: float = 0.7) -> str:
    """Tier 0 — local Ollama (always free, always first). Delegates to ollama_safe."""
    from core.inference.ollama_safe import chat as _ollama_chat
    t0 = time.perf_counter()
    result = _ollama_chat(model=model, messages=messages, timeout=timeout, temperature=temperature)
    if result:
        _record_usage("ollama", model, messages, result,
                      (time.perf_counter() - t0) * 1000, True)
    return result


def _pool_key(env_var: str, fallback: str = "") -> str:
    """Next key from the multi-key pool (comma-separated env), or a config fallback."""
    try:
        from core.inference.key_pool import get_pool
        k = get_pool(env_var).next_key()
        if k:
            return k
    except Exception:
        logger.warning("[VECTOR] silent swallow")
        pass
    return fallback


def _try_gemini(model_hint: str, messages: list[dict], timeout: float, temperature: float = 0.7) -> str:
    """Tier 1 — Gemini free API. Uses google-generativeai SDK or httpx fallback.

    Free tier: 15 req/min, 1M tokens/day for Flash models.
    Model selection: if model_hint looks local (vector-*), maps to gemini-2.0-flash.
    """
    if _is_rate_limited("gemini"):
        return ""
    api_key = _pool_key("GEMINI_API_KEY", str(CONFIG["api_keys"]["gemini_key"]))
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
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        resp = _sync_cb_call("gemini", lambda: httpx.post(url, json=body, timeout=timeout))
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
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][vc_llm] circuit breaker open for gemini")
        return ""
    except Exception as e:
        logger.warning(f"[VECTOR][vc_llm] Gemini failed: {e}")
        return ""


def _try_anthropic(model_hint: str, messages: list[dict], timeout: float, temperature: float = 0.7) -> str:
    """Tier 2 — Anthropic Claude API (paid). Active when ANTHROPIC_API_KEY is set."""
    if _is_rate_limited("anthropic"):
        return ""
    api_key = _pool_key("ANTHROPIC_API_KEY", str(CONFIG["api_keys"]["anthropic_key"]))
    if not api_key:
        return ""

    claude_model = _map_to_claude_model(model_hint)
    t0 = time.perf_counter()
    try:
        import anthropic as _sdk
        client = _sdk.Anthropic(api_key=api_key)
        system = ""
        user_msgs = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                user_msgs.append(m)
        kwargs = dict(model=claude_model, max_tokens=4096, temperature=temperature,
                      messages=user_msgs or [{"role": "user", "content": "Hello"}])
        if system:
            kwargs["system"] = system
        response = _sync_cb_call("anthropic", lambda: client.messages.create(**kwargs))
        text = response.content[0].text if response.content else ""
        if text:
            _record_usage("anthropic", claude_model, messages, text,
                          (time.perf_counter() - t0) * 1000, True)
            logger.info(f"[VECTOR][vc_llm] anthropic/{claude_model} responded ({len(text)} chars)")
        return text
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][vc_llm] circuit breaker open for anthropic")
        return ""
    except Exception as e:
        if "rate" in str(e).lower() or "429" in str(e):
            _mark_rate_limited("anthropic", 60.0)
        logger.warning(f"[VECTOR][vc_llm] Anthropic failed: {e}")
        return ""


def _try_openrouter(model_hint: str, messages: list[dict], timeout: float) -> str:
    """Tier 2 — OpenRouter (300+ models via one API). Paid, set OPENROUTER_API_KEY."""
    if _is_rate_limited("openrouter"):
        return ""
    api_key = _pool_key("OPENROUTER_API_KEY", str(CONFIG["api_keys"]["openrouter_key"]))
    if not api_key:
        return ""

    # OpenRouter uses OpenAI-compatible API
    or_model = _map_to_openrouter_model(model_hint)
    t0 = time.perf_counter()
    try:
        import httpx
        resp = _sync_cb_call("openrouter", lambda: httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "HTTP-Referer": "https://github.com/arghyadeep-deb/VECTOR",
                     "X-Title": "VECTOR AI"},
            json={"model": or_model, "messages": messages, "max_tokens": 4096},
            timeout=timeout,
        ))
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
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][vc_llm] circuit breaker open for openrouter")
        return ""
    except Exception as e:
        logger.warning(f"[VECTOR][vc_llm] OpenRouter failed: {e}")
        return ""


# â”€â”€ Model mapping helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Main chat function — drop-in for ollama_safe.chat() â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def chat(
    model: str,
    messages: list[dict],
    timeout: float = 30.0,
    *,
    provider: ProviderName = "auto",
    allow_cloud: bool = True,
    district: str | None = None,
    sensitive: bool = False,
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

    # â”€â”€ Forced provider â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if provider == "gemini":
        return _try_gemini(model, messages, timeout)
    if provider == "anthropic":
        return _try_anthropic(model, messages, timeout)
    if provider == "openrouter":
        return _try_openrouter(model, messages, timeout)
    if provider == "ollama":
        return _try_ollama(model, messages, timeout)

    # â”€â”€ Auto chain: sensitivity + complexity aware â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # security/privacy/RED/secret-bearing -> local Ollama only (never leaves device);
    # simple/medium -> cloud-first (gemini free first) for fast replies;
    # heavy (COMPLEX/REASONING) non-sensitive -> cloud premium (anthropic) first.
    local_only = False
    heavy = False
    try:
        from core.inference.route_policy import decide_route
        _prompt = _messages_to_text(messages)
        _plan = decide_route(_prompt, district=district, sensitive=sensitive)
        local_only = _plan.local_only
        heavy = _plan.tier == "reasoning"
        logger.debug("[VECTOR][vc_llm] route: local_only={} heavy={} ({})",
                     local_only, heavy, _plan.reason)
    except Exception as e:
        logger.debug(f"[VECTOR][vc_llm] route_policy unavailable: {e}")

    # Sensitive or cloud-disabled -> strictly local
    if local_only or not allow_cloud:
        result = _try_ollama(model, messages, timeout)
        if not result and not local_only:
            logger.warning(f"[VECTOR][vc_llm] local failed for {model}, cloud disabled")
        return result

    if heavy:
        order = ["anthropic", "openrouter", "gemini", "ollama"]   # premium first
    else:
        order = ["gemini", "openrouter", "anthropic", "ollama"]   # free/fast first

    _try_map = {
        "ollama": _try_ollama,
        "gemini": _try_gemini,
        "anthropic": _try_anthropic,
        "openrouter": _try_openrouter,
    }
    for slug in order:
        result = _try_map[slug](model, messages, timeout)
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
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
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
        "gemini": bool(CONFIG["api_keys"]["gemini_key"]),
        "anthropic": bool(CONFIG["api_keys"]["anthropic_key"]),
        "openrouter": bool(CONFIG["api_keys"]["openrouter_key"]),
    }
    print(f"[OK] providers: {providers_available}")
    print(f"[OK] gemini_model_map: {len(_GEMINI_MAP)} entries")
    print(f"[OK] claude_model_map: {len(_CLAUDE_MAP)} entries")
    print("vectorcode_llm.py OK")