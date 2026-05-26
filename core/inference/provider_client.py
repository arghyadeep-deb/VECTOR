"""
VECTOR Unified Provider Client -- routes LLM calls to any of the 27 providers.

Replaces the Ollama-only constraint with a priority-based routing system:
  1. Ollama first (local, free, private)
  2. API key providers as fallback or explicit override

Usage:
    client = ProviderClient()

    # Auto-route (Ollama first, then fallbacks)
    result = await client.complete("Explain transformers", tier="coding")

    # Explicit provider
    result = await client.complete("Write a poem", provider="gemini")

    # With messages
    result = await client.chat([
        {"role": "user", "content": "What is Python?"}
    ], provider="groq")

Ported from the agent OS runtime LLM drivers (anthropic.rs, gemini.rs, openai.rs).
"""
from __future__ import annotations

__all__ = [
    "CompletionResult",
    "get_client",
    "ProviderClient",
]


import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from core.inference.llm_providers import (
    LLMProvider, PROVIDERS, TIER_ROUTING,
    get_provider, configured_providers, route_for_tier,
)


@dataclass
class CompletionResult:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"


class ProviderClient:
    """
    Async LLM client that routes to the right provider.

    Routing logic:
      1. If provider= explicitly given, use that
      2. If tier= given, use TIER_ROUTING table (Ollama first)
      3. Default: Ollama
    """

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        tier: str = "agentic",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Single-turn completion."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, provider=provider, model=model,
                               tier=tier, temperature=temperature, max_tokens=max_tokens)

    async def chat(
        self,
        messages: list[dict],
        provider: str | None = None,
        model: str | None = None,
        tier: str = "agentic",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        caller_id: str = "system",
        inject_personality: bool = False,
        sensitive: bool = False,
        district: str | None = None,
        person_id: str | None = None,
    ) -> CompletionResult:
        """
        Multi-turn chat with automatic provider routing and fallback.

        Pipeline:
          0. (optional) Personality injection -- sentiment-aware system prompt
          1. Rate-limit check (GCRA, 500 tokens/min per caller)
          2. ModelRouter resolves tier -> model
          3. ReliableProvider wraps call with retry + backoff
          4. Tries providers in order until one succeeds
          5. (optional) Consistency enforcement -- rewrite off-character responses
        """
        # -- Personality injection ---------------------------------------------
        _personality_layer = None
        _user_text_for_validation = ""
        _sentiment_for_validation = "neutral"
        if inject_personality:
            try:
                from core.personality.middleware import get_personality_layer
                _personality_layer = get_personality_layer()
                for m in reversed(messages):
                    if m.get("role") == "user":
                        _user_text_for_validation = m.get("content", "")
                        break
                messages = _personality_layer.inject(messages, user_text=_user_text_for_validation)
                _sentiment_result = _personality_layer.analyze_sentiment(_user_text_for_validation)
                _sentiment_for_validation = _sentiment_result.emotion
            except Exception as _pe:
                logger.warning("[VECTOR][provider_client] personality injection failed: {}", _pe)

        # -- Rate limit check --------------------------------------------------
        try:
            from core.metering.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            allowed, wait_ms = rl.check(caller_id, "llm_message")
            if not allowed:
                logger.warning(
                    "[VECTOR][provider_client] rate limit hit caller={} wait={:.0f}ms",
                    caller_id, wait_ms,
                )
                if wait_ms > 5000:
                    raise RuntimeError(f"Rate limit exceeded -- retry in {wait_ms/1000:.1f}s")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        # ── Sensitivity + complexity routing (local-vs-cloud) ────────────────
        # Sets tier + provider order: security/RED/secret → local Ollama only;
        # simple → pooled cloud keys; heavy → cloud premium then local fallback.
        _route_order: list[str] | None = None
        if not provider:
            try:
                from core.inference.route_policy import decide_route
                _prompt = " ".join(
                    m.get("content", "") for m in messages if m.get("role") == "user"
                )
                _plan = decide_route(_prompt, district=district, sensitive=sensitive)
                _route_order = _plan.providers
                tier = _plan.tier
                logger.debug(
                    "[VECTOR][provider_client] route: {} tier={} ({})",
                    _plan.providers, _plan.tier, _plan.reason,
                )
            except Exception as _re:
                logger.debug("[VECTOR][provider_client] route_policy unavailable: {}", _re)

        # â"€â"€ Model routing via ModelRouter â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        if not model:
            try:
                from core.engine.providers.model_router import ModelRouter
                _router = ModelRouter()
                route = _router.resolve(tier)
                model = route.model
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        # â"€â"€ Provider selection â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        if provider:
            prov_obj = get_provider(provider)
            if not prov_obj:
                raise ValueError(f"Unknown provider: {provider}")
            providers_to_try = [prov_obj]
        else:
            order = _route_order if _route_order is not None else TIER_ROUTING.get(tier, ["ollama"])
            providers_to_try = []
            for slug in order:
                p = get_provider(slug)
                if p and p.is_configured:
                    providers_to_try.append(p)
            if not providers_to_try:
                providers_to_try = [PROVIDERS["ollama"]]

        # â"€â"€ ReliableProvider retry loop â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        last_error = ""
        for prov in providers_to_try:
            target_model = model or prov.default_model
            try:
                logger.debug(
                    "[VECTOR][provider_client] {} -> {} ({})",
                    tier, target_model, prov.slug,
                )
                result = await self._call_with_retry(
                    prov, target_model, messages, temperature, max_tokens, tools
                )
                # -- Consistency enforcement -----------------------------------
                if _personality_layer is not None and result.content:
                    try:
                        final_content, _val = _personality_layer.validate(
                            result.content,
                            user_text=_user_text_for_validation,
                            sentiment=_sentiment_for_validation,
                        )
                        result = CompletionResult(
                            content=final_content,
                            model=result.model,
                            provider=result.provider,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            finish_reason=result.finish_reason,
                        )
                    except Exception as _ve:
                        logger.warning("[VECTOR][provider_client] consistency check failed: {}", _ve)
                return result
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "[VECTOR][provider_client] {} failed: {}. Trying next...",
                    prov.slug, str(e)[:80],
                )
                continue

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def _call_with_retry(
        self,
        prov,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None,
        max_retries: int = 3,
    ):
        """Wrap _call() with ReliableProvider retry + exponential backoff."""
        import asyncio
        try:
            from core.engine.providers.reliable_provider import (
                is_non_retryable, is_rate_limited, parse_retry_after_ms
            )
            use_reliable = True
        except ImportError:
            use_reliable = False

        from core.inference.key_pool import get_pool
        pool = get_pool(prov.api_key_env)
        backoff = 1.0
        for attempt in range(max_retries):
            key = pool.next_key()
            try:
                return await self._call(prov, model, messages, temperature, max_tokens, tools, api_key=key)
            except Exception as e:
                err = str(e)
                low = err.lower()
                is_key_err = (
                    "401" in err or "403" in err or "429" in err
                    or "invalid api key" in low or "unauthorized" in low
                    or (use_reliable and is_rate_limited(err))
                )
                if key and is_key_err:
                    pool.mark_failed(key)  # bench this key; next attempt rotates to another
                # auth error on a multi-key pool → try the next key instead of bailing
                if use_reliable and is_non_retryable(err) and not (is_key_err and pool.size > 1):
                    raise
                if attempt == max_retries - 1:
                    raise
                wait = backoff
                if use_reliable:
                    retry_after = parse_retry_after_ms(err)
                    if retry_after:
                        wait = retry_after / 1000
                    elif is_rate_limited(err):
                        wait = backoff * 2
                logger.warning(
                    "[VECTOR][provider_client] attempt {}/{} failed -- retrying in {:.1f}s",
                    attempt + 1, max_retries, wait,
                )
                await asyncio.sleep(wait)
                backoff = min(backoff * 2, 30.0)

    async def _call(
        self,
        prov: LLMProvider,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None,
        api_key: str | None = None,
    ) -> CompletionResult:
        """Route to the right driver based on provider.driver."""
        match prov.driver:
            case "anthropic":
                return await self._call_anthropic(prov, model, messages, temperature, max_tokens, api_key=api_key)
            case "gemini":
                return await self._call_gemini(prov, model, messages, temperature, max_tokens, api_key=api_key)
            case "openai_compat" | "ollama":
                return await self._call_openai_compat(prov, model, messages, temperature, max_tokens, tools, api_key=api_key)
            case _:
                raise ValueError(f"Unknown driver: {prov.driver}")

    async def _call_openai_compat(
        self,
        prov: LLMProvider,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: list[dict] | None,
        api_key: str | None = None,
    ) -> CompletionResult:
        """Call any OpenAI-compatible /v1/chat/completions endpoint."""
        try:
            import httpx
        except ImportError:
            raise ImportError("Run: pip install httpx")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        key = api_key if api_key is not None else prov.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"

        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        base_url = prov.effective_base_url
        url = f"{base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        usage = data.get("usage", {})

        # â"€â"€ ToolDispatcher: parse structured tool_calls from response â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        # NativeDispatcher handles OpenAI/Ollama tool_call format;
        # falls back to XmlDispatcher for <tool_call> tags in raw text.
        tool_calls_parsed: list = []
        if tools:
            try:
                from core.engine.tools.dispatcher import NativeDispatcher
                _dispatcher = NativeDispatcher()
                clean_text, tool_calls_parsed = _dispatcher.parse_response(content, raw_response=data)
                if tool_calls_parsed:
                    content = clean_text
                    logger.debug(
                        "[VECTOR][provider_client] tool_dispatcher parsed {} call(s): {}",
                        len(tool_calls_parsed),
                        [tc.name for tc in tool_calls_parsed],
                    )
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        result = CompletionResult(
            content=content,
            model=model,
            provider=prov.slug,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )
        # Attach parsed tool calls for callers that need them
        if tool_calls_parsed:
            result._tool_calls = tool_calls_parsed  # type: ignore[attr-defined]
        return result

    async def _call_anthropic(
        self,
        prov: LLMProvider,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        api_key: str | None = None,
    ) -> CompletionResult:
        """Call Anthropic Claude API (native messages format)."""
        try:
            import httpx
        except ImportError:
            raise ImportError("Run: pip install httpx")

        # Separate system from messages
        system = ""
        filtered = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                filtered.append(m)

        payload: dict = {
            "model": model,
            "messages": filtered,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key if api_key is not None else prov.api_key,
            "anthropic-version": "2023-06-01",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{prov.base_url}/messages",
                json=payload, headers=headers,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Anthropic HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        content = "".join(
            b.get("text", "") for b in data.get("content", [])
            if b.get("type") == "text"
        )
        usage = data.get("usage", {})

        return CompletionResult(
            content=content,
            model=model,
            provider=prov.slug,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason", "stop"),
        )

    async def _call_gemini(
        self,
        prov: LLMProvider,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        api_key: str | None = None,
    ) -> CompletionResult:
        """Call Google Gemini API (generateContent format)."""
        try:
            import httpx
        except ImportError:
            raise ImportError("Run: pip install httpx")

        # Convert OpenAI messages to Gemini format
        contents = []
        system_instruction = None
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({"role": gemini_role, "parts": [{"text": content}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        url = f"{prov.base_url}/models/{model}:generateContent?key={api_key if api_key is not None else prov.api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload,
                                     headers={"Content-Type": "application/json"})

        if resp.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})

        return CompletionResult(
            content=content,
            model=model,
            provider=prov.slug,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            finish_reason=candidates[0].get("finishReason", "STOP").lower(),
        )

    def complete_sync(self, prompt: str, **kwargs) -> CompletionResult:
        """Synchronous wrapper for environments without running event loop."""
        return asyncio.run(self.complete(prompt, **kwargs))


# Singleton
_client: ProviderClient | None = None


def get_client() -> ProviderClient:
    global _client
    if _client is None:
        _client = ProviderClient()
    return _client


if __name__ == "__main__":
    # Verify routing logic (no actual API calls in test)
    client = ProviderClient()

    # Tier routing returns something
    agentic_prov = route_for_tier("agentic")
    assert agentic_prov is not None

    # Ollama is always available
    ollama = get_provider("ollama")
    assert ollama and ollama.free

    # Provider count
    assert len(PROVIDERS) >= 27

    # All configured providers have base_url
    for p in configured_providers():
        assert p.base_url or p.effective_base_url

    print(f"OK provider_client.py -- {len(PROVIDERS)} providers, routing verified")
    print("Note: Set API keys in .env to activate cloud providers")
