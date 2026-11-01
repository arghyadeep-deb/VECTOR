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
    "achat",
    "chat_stream",
    "get_session_usage",
    "ProviderName",
    "TokenUsage",
]


import asyncio
import os
import sys
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
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
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
                  response: str, latency_ms: float, success: bool,
                  *, caller_id: str = "vc_llm_legacy_chain") -> None:
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
    # Inference observability — only for providers that never touch
    # ProviderClient or ollama_safe.chat() (gemini/anthropic/openrouter
    # legacy direct calls). Ollama is excluded here because _try_ollama()
    # delegates to ollama_safe.chat(), which already records this call —
    # recording again here would double-count it in inference_calls.
    if provider != "ollama":
        try:
            from core.metering.inference_observability import (
                get_inference_observability, extract_domain, is_autonomous_caller,
            )
            get_inference_observability().record(
                caller_id=caller_id,
                domain=extract_domain(caller_id, model),
                tier="",
                provider=provider,
                model=model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                is_ollama=False,
                is_autonomous=is_autonomous_caller(caller_id),
                status="ok" if success else "error",
                # _estimate_tokens() is always a char-count heuristic (~4
                # chars/token) — this legacy chain has no access to any
                # provider's real usage field, so every row from here is
                # explicitly marked non-exact for report-time distinction.
                metadata={"token_exact": False},
            )
        except Exception:
            pass  # observability must never break the call path


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
    except Exception as e:
        logger.warning("[VECTOR][key_pool] key fetch failed for {}, using fallback: {}", env_var, e)
        pass
    return fallback


def _try_gemini(model_hint: str, messages: list[dict], timeout: float, temperature: float = 0.7) -> str:
    """Tier 1 — Gemini free API. Uses google-generativeai SDK or httpx fallback.

    Free tier: 15 req/min, 1M tokens/day for Flash models.
    Model selection: if model_hint looks local (vector-*), maps to gemini-2.5-flash (gemini-2.0-* return 404 on the owner key; probed 2026-07-03 and again 2026-09-27).
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
        # RR-3.7C: the request URL above embeds the real Gemini key as
        # `?key=<value>` (the Gemini REST API's own auth mechanism -- no
        # header-based alternative here); httpx's HTTPStatusError.__str__()
        # includes the full request URL, so a raw f"{e}" put the real key
        # straight into this log line. Sanitized at the point of logging --
        # see core/inference/error_sanitize.py for the full root-cause trace.
        from core.inference.error_sanitize import sanitize_provider_error
        logger.warning(f"[VECTOR][vc_llm] Gemini failed: {sanitize_provider_error(str(e))}")
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


def _try_openrouter(model_hint: str, messages: list[dict], timeout: float, temperature: float = 0.7) -> str:
    """Tier 2 — OpenRouter (300+ models via one API). Free (:free) models only -- see the gate below."""
    if _is_rate_limited("openrouter"):
        return ""
    api_key = _pool_key("OPENROUTER_API_KEY", str(CONFIG["api_keys"]["openrouter_key"]))
    if not api_key:
        return ""

    # OpenRouter uses OpenAI-compatible API
    or_model = _map_to_openrouter_model(model_hint)
    # Owner rule (2026-07-08): free-tier only at runtime. The map below still names paid Claude/DeepSeek models; without
    # this gate the only thing stopping a real charge was the account having no credit (57 HTTP 402s per session).
    if not or_model.endswith(":free"):
        logger.debug(f"[VECTOR][vc_llm] openrouter skipped: {or_model} is not a :free model (free-tier-only rule)")
        return ""
    t0 = time.perf_counter()
    try:
        import httpx
        resp = _sync_cb_call("openrouter", lambda: httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "HTTP-Referer": "https://github.com/arghyadeep-deb/VECTOR",
                     "X-Title": "VECTOR AI"},
            json={"model": or_model, "messages": messages, "max_tokens": 4096, "temperature": temperature},
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

# Map Ollama custom model names to provider-specific model IDs
_GEMINI_MAP = {
    "vector-focus":        "gemini-2.5-flash",
    "vector-coder":        "gemini-2.5-flash",
    "vector-reasoning":    "gemini-2.5-flash",
    "vector-r1":           "gemini-2.5-flash",
    "vector-ambient":      "gemini-2.5-flash",
    "vector-multilingual": "gemini-2.5-flash",
}

# Map custom model names to TIER_ROUTING tiers for ProviderClient delegation.
# This ensures vector-reasoning gets Groq/LLM7/GitHub reasoning models,
# vector-coder gets GitHub/LLM7 coding models, etc.
_MODEL_TO_TIER: dict[str, str] = {
    "vector-reasoning":    "reasoning",
    "vector-r1":           "reasoning",
    "vector-coder":        "coding",
    "qwen3:14b":           "coding",
    "deepseek-r1:14b":     "reasoning",
    "vector-focus":        "conversation",
    "vector-ambient":      "fast",
    "vector-multilingual": "multilingual",
}


def _model_to_tier(model: str) -> str:
    """Map an Ollama custom model name to a TIER_ROUTING key."""
    return _MODEL_TO_TIER.get(model, "fast")


# Local role → default work domain (Step 8, owner request 2026-07-02).
# Agents that don't pass an explicit domain= still get domain-aligned cloud
# routing based on which local model they asked for.
_ROLE_TO_DOMAIN = {
    "vector-coder":        "coding.generation",
    "vector-reasoning":    "orchestration",
    "vector-r1":           "orchestration",
    "vector-focus":        "agentic.loop",
    "vector-ambient":      "agentic.loop",
    "vector-multilingual": "multilingual.indic",
}


def _resolve_domain(model: str, domain: str) -> str:
    """Explicit domain wins; else map the requested local role to its default
    domain. Empty string when no mapping (caller keeps plain tier routing)."""
    if domain:
        return domain
    return _ROLE_TO_DOMAIN.get(model, "")

_CLAUDE_MAP = {
    "vector-focus":     "claude-haiku-4-5",
    "vector-coder":     "claude-sonnet-4-6",
    "vector-reasoning": "claude-sonnet-4-6",
    "vector-r1":        "claude-sonnet-4-6",
    "vector-ambient":   "claude-haiku-4-5",
}

_OPENROUTER_MAP = {
    "vector-reasoning": "anthropic/claude-sonnet-4-6",
    "vector-coder":     "deepseek/deepseek-coder-v2",
    "vector-focus":     "meta-llama/llama-3.1-8b-instruct:free",
    "vector-r1":        "deepseek/deepseek-r1:free",
}


def _map_to_gemini_model(model_hint: str) -> str:
    return _GEMINI_MAP.get(model_hint, "gemini-2.5-flash")


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


# â”€â”€ Running-event-loop guard (KNOWN_ISSUES #0 Part 2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#
# chat() is a plain sync function. Called with no `await`/`asyncio.to_thread`
# from a thread that owns a RUNNING asyncio event loop — the exact shape of
# every district agent's async run() method — it blocks that loop for up to
# `timeout + vc_llm_thread_grace_sec` seconds (fccdeb91f). ~112 files do this
# today (`grep -rl "vectorcode_llm import.*chat"`, 2026-08-06). This section
# makes that antipattern loud instead of silently fixing all 112 call sites,
# which is a far bigger change than this bug warrants and could itself take
# VECTOR down. See achat() below for the correct async-native replacement.

_LOOP_WARNING_LAST: dict[str, float] = {}
_LOOP_WARNING_LOCK = threading.Lock()


def _caller_site() -> str:
    """Identify the frame that called into chat() from outside this module.

    Walks raw frame objects (f_back / f_code attributes only) rather than
    `inspect.stack()` or `traceback.extract_stack()` — both of those read
    and cache source lines for every frame by default, which is wasted work
    on a path that may run on every single one of ~112 call sites. Frame
    attribute access is effectively free by comparison.
    """
    try:
        _this_file = os.path.abspath(__file__)
        frame = sys._getframe(2)  # skip this function + _warn_if_running_loop
        while frame is not None:
            if os.path.abspath(frame.f_code.co_filename) != _this_file:
                return f"{frame.f_code.co_filename}:{frame.f_lineno} (in {frame.f_code.co_name})"
            frame = frame.f_back
    except Exception:
        pass
    return "<unknown caller>"


def _warn_if_running_loop(model: str) -> None:
    """Warn (or, in strict mode, raise) when chat() is called synchronously
    from a thread that already has a running asyncio event loop.

    Silent and free when there is no running loop on this thread (the normal,
    unchanged case for every existing caller and for the whole sync test
    suite) — `asyncio.get_running_loop()` raising RuntimeError is the
    standard, documented way to detect this.

    Deliberately does NOT raise by default: those ~112 call sites are live in
    production; turning them all into exceptions overnight is a much bigger
    change than this bug warrants and risks taking VECTOR down. Instead this
    is LOUD — it names the exact calling file/line so offenders are
    enumerable from the logs and can be migrated to `achat()` incrementally.
    Rate-limited PER CALL SITE (CONFIG["vc_llm_loop_guard_cooldown_sec"], not
    globally) so an already-known hot offender doesn't drown the logs while a
    brand-new one is still always caught on its first hit.

    Opt-in strict mode — CONFIG["vc_llm_loop_guard_strict"] / env
    VC_LLM_LOOP_GUARD_STRICT=1 — raises instead of warning, unconditionally
    (never rate-limited: a test asserting this behaves the same way every
    run). Intended for tests/CI so the antipattern can't grow silently;
    deliberately not the production default (flipping it there would turn a
    warning into a simultaneous outage across all ~112 sites at once).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # normal case: no running loop on this thread — nothing to warn about

    site = _caller_site()
    message = (
        f"[VECTOR][vc_llm] BLOCKING CALL: chat(model={model!r}) called "
        f"synchronously from {site} while a RUNNING asyncio event loop owns "
        f"this thread — this call will block that loop for up to "
        f"timeout+grace seconds (KNOWN_ISSUES #0). Migrate this call site to "
        f"`await achat(...)`."
    )
    if CONFIG.get("vc_llm_loop_guard_strict", False):
        raise RuntimeError(message)

    cooldown = float(CONFIG.get("vc_llm_loop_guard_cooldown_sec", 300.0))
    now = time.time()
    with _LOOP_WARNING_LOCK:
        last = _LOOP_WARNING_LAST.get(site, 0.0)
        if cooldown > 0 and (now - last) < cooldown:
            return
        _LOOP_WARNING_LAST[site] = now
    logger.warning(message)


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
    permission_tier: str | None = None,
    temperature: float = 0.7,
    domain: str = "",
) -> str:
    """Unified LLM call with multi-provider fallback.

    Same signature as ollama_safe.chat() - drop-in replacement.

    Args:
        model:       Ollama model tag OR cloud model ID (e.g. "claude-sonnet-4-6")
        messages:    Standard chat messages list
        timeout:     Per-provider HTTP timeout
        provider:    Force specific provider. "auto" = try local first, cloud as fallback
        allow_cloud: Set False to stay strictly local (same as ollama_safe.chat)
        temperature: Sampling temperature passed to every provider (default 0.7)

    Returns:
        Response text, or empty string on total failure (never raises).
    """
    if not messages:
        return ""

    _warn_if_running_loop(model)

    # Ponytail minimal-code ladder — injected once here so all ~25 coding agents build
    # lean (no-op for non-coding domains; degrades to no-op if the plugin is absent).
    try:
        from core.inference.ponytail_guard import inject as _ponytail_inject
        messages = _ponytail_inject(messages, domain=domain, model=model)
    except Exception:
        pass

    # ── Sensitivity check (local-only override) ─────────────────────────────
    local_only = False
    try:
        from core.inference.route_policy import decide_route
        _prompt = _messages_to_text(messages)
        _plan = decide_route(
            _prompt, district=district,
            permission_tier=permission_tier, sensitive=sensitive,
        )
        local_only = _plan.local_only
        logger.debug("[VECTOR][vc_llm] route: local_only={} ({})", local_only, _plan.reason)
    except Exception as e:
        logger.warning(
            "[VECTOR][vc_llm] route_policy unavailable; failing local-only: {}", e
        )
        local_only = True

    domain_local_only = False
    if domain:
        try:
            from core.inference.model_catalog import domain_local_only as _domain_local_only
            domain_local_only = _domain_local_only(domain)
        except Exception as e:
            logger.debug("[VECTOR][vc_llm] domain policy unavailable: {}", e)

    if local_only or domain_local_only or not allow_cloud:
        result = _try_ollama(model, messages, timeout, temperature)
        if not result and not local_only:
            logger.warning(f"[VECTOR][vc_llm] local failed for {model}, cloud disabled")
        return result

    if provider == "gemini":
        return _try_gemini(model, messages, timeout, temperature)
    if provider == "anthropic":
        return _try_anthropic(model, messages, timeout, temperature)
    if provider == "openrouter":
        return _try_openrouter(model, messages, timeout, temperature)
    if provider == "ollama":
        return _try_ollama(model, messages, timeout, temperature)

    # ── Domain alignment (Step 8) — best model per work domain + 3-4 cloud
    # fallbacks + ollama terminal. Registered as model_pool "domain:<name>"
    # logical models, so provider_client expands the full chain. Kill-switch
    # VECTOR_DOMAIN_ROUTING=0 and pytest both fall back to plain tier routing.
    _domain = ""
    if os.environ.get("VECTOR_DOMAIN_ROUTING") != "0" and "pytest" not in sys.modules:
        _domain = _resolve_domain(model, domain)
        if _domain:
            try:
                from core.inference.model_catalog import domain_local_only
                if domain_local_only(_domain):
                    _domain = ""   # e.g. security → stay on the local path below
            except Exception:
                pass

    # ── Primary: delegate to ProviderClient for full TIER_ROUTING ───────────
    # This activates Groq (500+ tok/s free), LLM7 (5M tok/day — kimi/qwen3-235b),
    # Cerebras (wafer-scale free), GitHub Models (DeepSeek-R1/o3/gpt-5 free),
    # Gemini, OpenRouter, NVIDIA, and finally Ollama as last resort.
    tier = _model_to_tier(model)
    _pc_model = f"domain:{_domain}" if _domain else None   # logical model → chain
    try:
        import concurrent.futures as _cf
        import asyncio as _asyncio
        from core.inference.provider_client import ProviderClient as _PC

        async def _async_call():
            r = await _PC().chat(
                messages=messages,
                model=_pc_model,          # domain chain when set, else tier picks
                tier=tier,
                temperature=temperature,
                max_tokens=4096,
                caller_id=f"vc_llm_{(_domain or model)[:24]}",
            )
            return r.content

        # 2026-08-06 (loop-stall root-cause fix, KNOWN_ISSUES #0): this used to
        # be `with _cf.ThreadPoolExecutor(max_workers=1) as _pool:` — a plain
        # context manager. That made the `.result(timeout=...)` below a FAKE
        # bound: Future.result(timeout=) does stop THIS thread from waiting
        # and raises concurrent.futures.TimeoutError on schedule, but leaving
        # the `with` block (whether via that exception or normally) runs
        # ThreadPoolExecutor.__exit__ -> shutdown(wait=True), which blocks
        # this same thread again — this time with NO timeout — until the
        # background asyncio.run(_async_call()) call actually finishes.
        # chat() is a plain sync function called directly (no `await`, no
        # `asyncio.to_thread`) from inside ~112 district agents' async run()
        # methods, so "this thread" is routinely the single autonomous-loop
        # event-loop thread. ProviderClient's own retry/fallback chain across
        # multiple providers can legitimately run for minutes under
        # rate-limit/cooldown conditions, so the old code could silently
        # re-block the loop thread for far longer than `timeout + grace`
        # implied, with the eventual TimeoutError never even reaching the
        # `except Exception as _pc_err:` below — exactly the "0% CPU, no
        # exception logged, heartbeat frozen" signature this issue describes.
        # Fix: don't use the executor as a context manager. shutdown(wait=False)
        # lets the orphaned worker thread finish on its own time in the
        # background instead of blocking the caller; its result (if any) is
        # simply discarded.
        _grace = CONFIG.get("vc_llm_thread_grace_sec", 15.0)
        _pool = _cf.ThreadPoolExecutor(max_workers=1)
        try:
            result = _pool.submit(_asyncio.run, _async_call()).result(timeout=timeout + _grace)
        finally:
            _pool.shutdown(wait=False)
        if result:
            logger.debug("[VECTOR][vc_llm] ProviderClient responded via {} ({} chars)",
                         _pc_model or tier, len(result))
            return result
    except Exception as _pc_err:
        logger.warning(f"[VECTOR][vc_llm] ProviderClient failed ({_pc_model or tier}): {_pc_err} — trying legacy chain")

    # ── Fallback: legacy direct-provider chain (Gemini → OpenRouter → Ollama) ─
    for _slug, _fn in [
        ("gemini",      _try_gemini),
        ("openrouter",  _try_openrouter),
        ("ollama",      _try_ollama),
    ]:
        result = _fn(model, messages, timeout, temperature)
        if result:
            return result

    logger.warning(f"[VECTOR][vc_llm] all providers failed for {model}")
    return ""


# ── Async-native twin of chat() (KNOWN_ISSUES #0 Part 2) ────────────────────

async def achat(
    model: str,
    messages: list[dict],
    timeout: float = 30.0,
    *,
    provider: ProviderName = "auto",
    allow_cloud: bool = True,
    district: str | None = None,
    sensitive: bool = False,
    permission_tier: str | None = None,
    temperature: float = 0.7,
    domain: str = "",
) -> str:
    """Async-native replacement for chat() — call this from inside an async
    district agent's run() method instead.

    chat()'s primary path already does the real work asynchronously
    (`ProviderClient.chat()` is a coroutine); the sync chat() only exists to
    call that from non-async code, and to do so it round-trips through a
    ThreadPoolExecutor + a second nested `asyncio.run()` just to come back
    and block the CALLING thread's own event loop for up to
    `timeout + vc_llm_thread_grace_sec` seconds (see fccdeb91f and
    `_warn_if_running_loop()` above). achat() removes that round-trip
    entirely: it `await`s the same coroutine directly on the caller's own
    running event loop — no second thread, no second loop, nothing to block.

    The synchronous legacy fallback chain (only reached if ProviderClient's
    own multi-provider chain raises) still shells out to blocking SDK/httpx
    calls, so those run via `asyncio.to_thread` here — this function never
    blocks the caller's loop at any point, at any stage of the chain.

    Same signature, same behaviour, and the same never-raises / returns ""
    on total failure contract as chat() — just reachable with `await`
    instead of a thread hop. Prefer this in every async run() method; chat()
    should only be called from genuinely synchronous code that owns no
    event loop of its own.
    """
    if not messages:
        return ""

    # Ponytail minimal-code ladder — same injection chat() does.
    try:
        from core.inference.ponytail_guard import inject as _ponytail_inject
        messages = _ponytail_inject(messages, domain=domain, model=model)
    except Exception:
        pass

    # ── Sensitivity check (local-only override) ─────────────────────────────
    local_only = False
    try:
        from core.inference.route_policy import decide_route
        _prompt = _messages_to_text(messages)
        _plan = await asyncio.to_thread(
            decide_route, _prompt, district=district,
            permission_tier=permission_tier, sensitive=sensitive,
        )
        local_only = _plan.local_only
        logger.debug("[VECTOR][vc_llm] route: local_only={} ({})", local_only, _plan.reason)
    except Exception as e:
        logger.warning(
            "[VECTOR][vc_llm] route_policy unavailable; failing local-only: {}", e
        )
        local_only = True

    domain_local_only = False
    if domain:
        try:
            from core.inference.model_catalog import domain_local_only as _domain_local_only
            domain_local_only = _domain_local_only(domain)
        except Exception as e:
            logger.debug("[VECTOR][vc_llm] domain policy unavailable: {}", e)

    if local_only or domain_local_only or not allow_cloud:
        result = await asyncio.to_thread(_try_ollama, model, messages, timeout, temperature)
        if not result and not local_only:
            logger.warning(f"[VECTOR][vc_llm] local failed for {model}, cloud disabled")
        return result

    if provider == "gemini":
        return await asyncio.to_thread(_try_gemini, model, messages, timeout, temperature)
    if provider == "anthropic":
        return await asyncio.to_thread(_try_anthropic, model, messages, timeout, temperature)
    if provider == "openrouter":
        return await asyncio.to_thread(_try_openrouter, model, messages, timeout, temperature)
    if provider == "ollama":
        return await asyncio.to_thread(_try_ollama, model, messages, timeout, temperature)

    # ── Domain alignment (Step 8) — same resolution chat() does.
    _domain = ""
    if os.environ.get("VECTOR_DOMAIN_ROUTING") != "0" and "pytest" not in sys.modules:
        _domain = _resolve_domain(model, domain)
        if _domain:
            try:
                from core.inference.model_catalog import domain_local_only
                if domain_local_only(_domain):
                    _domain = ""   # e.g. security → stay on the local path below
            except Exception:
                pass

    # ── Primary: await ProviderClient directly — no thread, no nested loop ──
    tier = _model_to_tier(model)
    _pc_model = f"domain:{_domain}" if _domain else None
    try:
        from core.inference.provider_client import ProviderClient as _PC
        r = await _PC().chat(
            messages=messages,
            model=_pc_model,
            tier=tier,
            temperature=temperature,
            max_tokens=4096,
            caller_id=f"vc_llm_{(_domain or model)[:24]}",
        )
        result = r.content
        if result:
            logger.debug("[VECTOR][vc_llm] ProviderClient responded via {} ({} chars)",
                         _pc_model or tier, len(result))
            return result
    except Exception as _pc_err:
        logger.warning(f"[VECTOR][vc_llm] ProviderClient failed ({_pc_model or tier}): {_pc_err} — trying legacy chain")

    # ── Fallback: legacy direct-provider chain, off the loop via to_thread ──
    for _slug, _fn in [
        ("gemini",      _try_gemini),
        ("openrouter",  _try_openrouter),
        ("ollama",      _try_ollama),
    ]:
        result = await asyncio.to_thread(_fn, model, messages, timeout, temperature)
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
