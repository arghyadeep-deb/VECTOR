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
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from loguru import logger

from core.config import CONFIG
from core.inference.llm_providers import (
    LLMProvider, PROVIDERS, TIER_ROUTING,
    get_provider, configured_providers, route_for_tier,
)


# â”€â”€ Concurrency bound (async side) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Async twin of the threading.Semaphore in core/inference/ollama_safe.py.
# _call_openai_compat() is the path this file uses to reach Ollama (the
# "ollama" provider's driver is "openai_compat" — see ProviderClient._call());
# it's a plain async coroutine using httpx.AsyncClient, so an asyncio.Semaphore
# is the correct primitive (a threading.Semaphore would block the whole event
# loop thread on .acquire(), stalling every other coroutine, not just Ollama
# callers). This is intentionally a SEPARATE instance from ollama_safe's
# semaphore rather than one shared lock: a threading.Semaphore and an
# asyncio.Semaphore cannot be unified without either blocking the event loop
# (using the threading one from async code) or requiring sync callers to run
# inside the event loop (using the asyncio one from a plain thread) — both
# are real deadlock/stall risks for a codebase where the same process runs
# both sync agent code and the async district/API layer concurrently. Both
# semaphores are sized off the same CONFIG["ollama_max_concurrent"] value, so
# worst case total in-flight Ollama requests from this process is bounded at
# 2x that number (sync path + async path each capped independently) — still
# a >20x cut from the 90-connection blowup this fix responds to, without the
# complexity/deadlock surface of forcing one primitive across two runtimes.
_OLLAMA_ASYNC_SEMAPHORE = asyncio.Semaphore(CONFIG["ollama_max_concurrent"])

# CLAUDE.md Rule 10 — "Free-tier only at runtime — no paid Anthropic/OpenAI
# keys at runtime" (owner decision 2026-07-08). Enforced in ProviderClient._call().
_PAID_ANTHROPIC_OPENAI_SLUGS = frozenset({"anthropic", "openai"})


@asynccontextmanager
async def _ollama_async_bound(prov: "LLMProvider"):
    """No-op for every provider except "ollama" — cloud APIs don't share
    Ollama's single-resident-model constraint (OLLAMA_MAX_LOADED_MODELS=1)
    and already have their own key-pool/rate-limit/circuit-breaker gating.
    Held for the full request/response round-trip; _call_openai_compat()
    always sends stream=False, so there is no long-lived streaming hold to
    reason about here (unlike ollama_safe.chat_stream())."""
    if getattr(prov, "slug", None) != "ollama":
        yield
        return
    async with _OLLAMA_ASYNC_SEMAPHORE:
        yield


class Rule10PolicyRefusal(RuntimeError):
    """CLAUDE.md Rule 10 ("free-tier only at runtime") blocked this call.

    A dedicated type (not a plain RuntimeError matched by message
    substring) so _call_with_retry() can recognize it unambiguously,
    before any of the generic is_key_err/is_rl/is_non_retryable string
    heuristics -- which, for a plain string match like "403", collide
    with unrelated key-rotation logic (see _call()'s own comment on this).
    """


_LEAKED_REASONING_RE = re.compile(
    r"^\s*(We need to|We must|We should|I need to|I should|I'll (?:first|now)|"
    r"Let'?s (?:think|check|figure|see)|Let me (?:think|check|see)|"
    r"Okay,? let'?s|The user (?:wants|is asking|asked|says)|"
    r"The owner (?:wants|is asking|asked|says)|Owner asks:|First,? I need)",
    re.IGNORECASE,
)


def _looks_like_leaked_reasoning(text: str) -> bool:
    """Detect raw chain-of-thought / analysis-channel narration leaking into
    the 'content' field instead of a real final answer.

    2026-08-04 DeepEval full-suite run: some reasoning-style models (observed
    on gpt-oss-class models reachable via the cloud fallback chain) return
    their internal analysis-channel prose as ordinary `content` when they run
    out of `max_tokens` mid-reasoning, before ever producing final-channel
    output — e.g. "We need to respond as VECTOR, concise JARVIS-style
    assistant, answer directly. Need to check what's likely on my plate
    today..." ending mid-sentence. This is a close cousin of the empty-content
    dud case just above (same underlying cause: a reasoning model burning its
    token budget on hidden thinking) but the content isn't empty, so that
    check doesn't catch it. No provider-side 'reasoning_content vs content'
    separation is available/reliable across all 27 providers here, so this is
    a deterministic backstop over the leaked text itself — same
    "deterministic backstop over LLM judgment" pattern used elsewhere in this
    codebase for safety/policy-critical output. False-positive risk is low:
    a real final answer to the owner essentially never opens by narrating the
    request in the third person ("the user/owner asks...") or announcing
    internal deliberation ("we need to...") — VECTOR's own system prompts
    address the owner directly instead.
    """
    head = (text or "").strip()[:120]
    return bool(_LEAKED_REASONING_RE.match(head))


def _is_local_model_name(model: str) -> bool:
    """True for Ollama-local model names (vector-* customs, ollama tag syntax,
    or anything registered in CONFIG['models']). Cloud providers 404 on these —
    they must use their own default_model instead."""
    if not model:
        return False
    if model.startswith("vector-"):
        return True
    try:
        from core.config import CONFIG
        if model in set(CONFIG.get("models", {}).values()):
            return True
    except Exception:
        pass
    return ":" in model and "/" not in model  # ollama tag, e.g. qwen3:14b


def _model_for_provider(prov, model: str | None, tier: str = "agentic") -> str:
    """Model this provider should serve for this call.

    Order: (1) requested cloud-servable model passes through verbatim;
    (2) local name / no model → the provider's best catalog model FOR THIS
    TIER (e.g. coding + cloudflare → kimi-k2.7-code, not the generic default);
    (3) default_model. The result always goes through the whitelist clamp —
    locked providers (opencode_zen, zai) can never emit a paid model."""
    candidate: str | None = None
    if model and (prov.slug == "ollama" or not _is_local_model_name(model)):
        candidate = model
    if candidate is None and prov.slug != "ollama":
        try:
            from core.inference.model_catalog import select_model
            candidate = select_model(prov.slug, tier)
        except Exception:
            candidate = None
    if candidate is None:
        candidate = model if (model and prov.slug == "ollama") else prov.default_model
    return _enforce_whitelist(prov, candidate, tier)


def _enforce_whitelist(prov, model_id: str, tier: str = "agentic") -> str:
    """HARD guardrail: locked providers never emit a non-whitelisted model —
    the opencode_zen/zai keys can reach PAID models and the owner's card is
    on file. Clamp to the catalog's best-for-tier (whitelisted by
    construction) or default_model, and warn loudly."""
    if not getattr(prov, "locked_models", False) or model_id in prov.models:
        return model_id
    try:
        from core.inference.model_catalog import select_model
        clamped = select_model(prov.slug, tier) or prov.default_model
    except Exception:
        clamped = prov.default_model
    if clamped not in prov.models:      # belt and suspenders
        clamped = prov.default_model
    logger.warning("[VECTOR][provider_client] {} model '{}' not in whitelist — clamped to '{}'",
                   prov.slug, model_id, clamped)
    return clamped


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

    def __init__(self, timeout: int = 60) -> None:
        # 2026-07-23 (JARVIS-parity latency pass): was 120s. That's the
        # per-HTTP-attempt ceiling for EVERY provider in a fallback chain —
        # a single slow-but-not-erroring provider (no exception, just a
        # genuine hang) could eat up to 120s before its own retry/backoff
        # even kicks in, and callers with no outer asyncio.wait_for of their
        # own (e.g. governor.py's _answer_conversationally(), fixed
        # separately this pass) had nothing bounding the total. 60s is still
        # generous for a real cold-model load (the documented worst case
        # elsewhere in this codebase is "90+ seconds" for a cold Ollama
        # swap, but Ollama is deliberately last in every fallback chain —
        # by the time a call reaches it, cloud options ahead of it in the
        # chain have already been tried) while capping the worst-case
        # single-attempt wait for the free-tier cloud providers that make up
        # the front of most chains, where a healthy response is normally
        # single-digit seconds.
        self._timeout = timeout

    async def complete(
        self,
        prompt: str | None = None,
        system: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        tier: str = "agentic",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        messages: list[dict] | None = None,
        **kwargs,
    ) -> CompletionResult:
        """Single-turn completion. Extra kwargs (caller_id, district,
        sensitive, ...) pass through to chat().

        Pass either `prompt` (optionally with `system`) or ready-made chat `messages`, not both. The `messages` form is
        accepted because seven callers (the /command registry, four marketing agents, the subconscious loop) were
        written against it and every call raised "missing 1 required positional argument: 'prompt'", so those agents
        never produced an answer (found by the 2026-09-26 loop watch).
        """
        if messages is not None:
            if prompt is not None:
                raise TypeError("complete() takes either prompt or messages, not both")
            messages = list(messages)
        else:
            if prompt is None:
                raise TypeError("complete() needs a prompt (or messages=)")
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, provider=provider, model=model,
                               tier=tier, temperature=temperature,
                               max_tokens=max_tokens, **kwargs)

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
        # -- Observability: start timer for end-to-end latency ----------------
        _obs_started = time.perf_counter()
        _obs_providers_tried = 0

        # -- Context budget compaction ------------------------------------------
        # Headroom-inspired: oversized messages get compacted to a head/tail
        # preview + retrieval handle before they ever reach a provider. No-op
        # for normal-sized messages (compact_text's own length gate).
        try:
            from districts.memory_curator.context_budget import get_context_budget_manager
            messages, _budget_handles = get_context_budget_manager().compact_messages(messages, persist=True)
            if _budget_handles:
                logger.info(
                    "[VECTOR][provider_client] context budget compacted {} message(s) caller={}",
                    len(_budget_handles), caller_id,
                )
        except Exception as _cbe:
            logger.warning("[VECTOR][provider_client] context budget compaction failed: {}", _cbe)

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
                messages = _personality_layer.inject(
                    messages,
                    user_text=_user_text_for_validation,
                    person_id=person_id,
                )
                _sentiment_result = _personality_layer.analyze_sentiment(_user_text_for_validation)
                _sentiment_for_validation = _sentiment_result.emotion
            except Exception as _pe:
                logger.warning("[VECTOR][provider_client] personality injection failed: {}", _pe)

        # -- Rate limit check --------------------------------------------------
        try:
            from core.metering.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            rl_result = rl.check(caller_id, "llm_message")
            if not rl_result:
                wait_ms = getattr(rl_result, "retry_after_secs", 0.0) * 1000.0
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

        # ── Cloud budget gate (C1) ─────────────────────────────────────────────
        # After route_policy decides providers, verify the cloud ones are within budget.
        # On budget exhaustion the route falls back to Ollama-only.
        if _route_order and any(p != "ollama" for p in _route_order):
            try:
                from core.inference.cloud_router import budget_gate as _bg
                _cloud_ok, _cloud_reason = _bg(_route_order)
                if not _cloud_ok:
                    logger.warning(
                        "[VECTOR][provider_client] cloud budget gate blocked → local only ({})",
                        _cloud_reason,
                    )
                    _route_order = ["ollama"]
            except Exception as _bg_err:
                logger.debug("[VECTOR][provider_client] cloud budget gate skipped: {}", _bg_err)

        # ── Model routing via ModelRouter â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
        # ── Build (provider, model_string) pairs ──────────────────────────────
        # When `model` is a logical alias (e.g. "kimi-k2.7-code"), model_pool
        # expands it to ordered (provider, actual_model_id) pairs across all
        # configured backends. When a provider rate-limits (429), it is marked in
        # cooldown and the next backend for that model is tried automatically.
        _mark_cooldown = None
        try:
            from core.inference.model_pool import (
                is_logical_model as _is_logical,
                get_backends as _get_backends,
                mark_cooldown as _mark_cooldown,
            )
            # Domain chains register into model_pool lazily on first catalog
            # load — ensure that happened before the is_logical check, so the
            # very first "domain:<name>" call in a process expands correctly.
            if model and model.startswith("domain:"):
                try:
                    from core.inference.model_catalog import get_catalog
                    get_catalog()
                except Exception:
                    pass
            if model and _is_logical(model):
                # Whitelist clamp applies to pool-expanded pairs too — a pool
                # entry must never route a paid model to a locked provider.
                _pairs: list[tuple] = [
                    (get_provider(slug), _enforce_whitelist(get_provider(slug), model_id, tier))
                    for slug, model_id in _get_backends(model)
                    if get_provider(slug) is not None
                ]
                if not _pairs:
                    # All backends cooled-down or unconfigured — fall through to standard list
                    _pairs = [(prov, _model_for_provider(prov, model, tier)) for prov in providers_to_try]
            else:
                _pairs = [(prov, _model_for_provider(prov, model, tier)) for prov in providers_to_try]
        except ImportError:
            _pairs = [(prov, _model_for_provider(prov, model, tier)) for prov in providers_to_try]

        # Cooldown rotation — a provider that just 429'd is marked via
        # mark_cooldown(), but that was ONLY honoured for logical-model routing
        # (get_backends filters it). Every tier-based call (tier="fast" — i.e.
        # voice + command bar) rebuilt its list straight from providers_to_try
        # and retried the cooled provider immediately: cohere-rag 429'd at
        # 02:12:17, :21 AND :33, burning ~2s per call each time (2026-07-17).
        # Deprioritize rather than drop, so a fully-cooled chain still runs.
        try:
            from core.inference.model_pool import _is_cooling_down
            _hot = [p for p in _pairs if not _is_cooling_down(getattr(p[0], "slug", ""))]
            _cold = [p for p in _pairs if _is_cooling_down(getattr(p[0], "slug", ""))]
            if _cold and _hot:
                logger.debug("[VECTOR][provider_client] cooling down, moved last: {}",
                             [getattr(p[0], "slug", "?") for p in _cold])
                _pairs = _hot + _cold
        except Exception as _ce:
            logger.debug("[VECTOR][provider_client] cooldown check unavailable: {}", _ce)

        # Soft quota rotation — pairs past ~90% of their free-tier limits move
        # after fresh cloud pairs (ollama stays terminal). Never drops/blocks.
        try:
            from core.inference.quota_ledger import get_quota_ledger
            _pairs = get_quota_ledger().reorder(_pairs)
        except Exception as _qe:
            logger.debug("[VECTOR][provider_client] quota ledger unavailable: {}", _qe)

        last_error = ""
        _last_error_kind = ""
        for _prov, target_model in _pairs:
            _obs_providers_tried += 1
            if _prov is None:
                continue
            try:
                from core.inference.provider_health import get_provider_health

                _health = get_provider_health()
                if not await _health.can_try(_prov.slug, target_model):
                    logger.warning(
                        "[VECTOR][provider_client] {}:{} skipped by provider health circuit",
                        _prov.slug,
                        target_model,
                    )
                    continue
            except Exception as _health_err:
                _health = None
                logger.debug("[VECTOR][provider_client] provider health unavailable: {}", _health_err)
            try:
                logger.debug(
                    "[VECTOR][provider_client] {} -> {} ({})",
                    tier, target_model, _prov.slug,
                )
                _started = time.perf_counter()
                result = await self._call_with_retry(
                    _prov, target_model, messages, temperature, max_tokens, tools
                )
                if _health is not None:
                    await _health.record_success(
                        _prov.slug,
                        target_model,
                        latency_ms=(time.perf_counter() - _started) * 1000,
                    )
                # Quota ledger — record BEFORE the empty-content dud check:
                # empty responses still burned tokens/requests upstream.
                try:
                    from core.inference.quota_ledger import get_quota_ledger
                    if _prov.slug not in ("ollama", "lmstudio", "vllm"):
                        _est = (result.input_tokens + result.output_tokens) or (
                            sum(len(m.get("content") or "") for m in messages) // 4
                            + len(result.content or "") // 4)
                        get_quota_ledger().record(_prov.slug, target_model, tokens=_est)
                except Exception:
                    pass
                # Empty content without tool calls = a dud (reasoning models
                # that burn max_tokens on hidden thinking: cerebras gpt-oss,
                # ollama thinking models). Treat as failure → next provider.
                if not (result.content or "").strip() and not tools:
                    last_error = f"{_prov.slug}:{target_model} returned empty content"
                    logger.warning("[VECTOR][provider_client] {} — trying next provider", last_error)
                    continue
                # Non-empty but leaked reasoning/analysis text instead of a
                # real final answer — same dud category as above, see
                # _looks_like_leaked_reasoning() docstring for the 2026-08-04
                # DeepEval finding that motivated this.
                if not tools and _looks_like_leaked_reasoning(result.content):
                    last_error = (f"{_prov.slug}:{target_model} returned leaked "
                                   f"reasoning/analysis text instead of a final answer")
                    logger.warning("[VECTOR][provider_client] {} — trying next provider", last_error)
                    continue
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
                # -- Observability: record successful call -------------------------
                try:
                    from core.metering.inference_observability import get_inference_observability, extract_domain, is_autonomous_caller
                    _obs_latency = (time.perf_counter() - _obs_started) * 1000
                    # Every driver (_call_openai_compat/_call_anthropic/_call_gemini)
                    # populates input_tokens/output_tokens straight from the
                    # provider's own usage field in its API response — these are
                    # always exact when non-zero. A provider that omits usage
                    # entirely (rare; some self-hosted OpenAI-compat backends)
                    # leaves both at their CompletionResult default of 0, which
                    # this flag also correctly reports as "not exact" (no
                    # estimate is substituted here — the row simply carries 0).
                    _obs_retries_from_pool = getattr(result, "_retry_attempts", None)
                    get_inference_observability().record(
                        caller_id=caller_id,
                        district=district or "",
                        domain=extract_domain(caller_id, model),
                        tier=tier,
                        provider=result.provider,
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        latency_ms=_obs_latency,
                        providers_tried=_obs_providers_tried,
                        is_ollama=(result.provider == "ollama"),
                        is_autonomous=is_autonomous_caller(caller_id),
                        sensitive=sensitive,
                        status="ok",
                        metadata={
                            "token_exact": bool(result.input_tokens or result.output_tokens),
                            **({"retry_attempts": _obs_retries_from_pool}
                               if _obs_retries_from_pool is not None else {}),
                        },
                    )
                except Exception:
                    pass  # observability must never break the call path
                return result
            except Exception as e:
                # RR-3.7C (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                # RR3_7C_FINAL_INGRESS_AUTHORIZATION_FREEZE_REPORT.md):
                # _call_gemini() above builds a request URL of the form
                # ".../generateContent?key=<real_key>" (Gemini's own REST
                # auth mechanism); httpx.HTTPStatusError.__str__() includes
                # the full request URL, so an unsanitized str(e) here would
                # carry the real key into both the warning below and the
                # "All providers failed" RuntimeError raised further down --
                # both consume `last_error`, so sanitizing once at this
                # single capture point closes both. See
                # core/inference/error_sanitize.py for the full trace.
                from core.inference.error_sanitize import sanitize_provider_error
                last_error = sanitize_provider_error(str(e))
                _err_low = last_error.lower()
                if _health is not None:
                    _kind = _health.classify_error(e)
                    _last_error_kind = getattr(_kind, "value", str(_kind))
                    await _health.record_failure(_prov.slug, target_model, kind=_kind, error=last_error)
                if _mark_cooldown and (
                    "429" in last_error
                    or "rate limit" in _err_low
                    or "quota exceeded" in _err_low
                    or "too many requests" in _err_low
                ):
                    # Gemini free tier uses sliding windows that can block for ~10 min
                    cooldown_secs = 600 if _prov.slug == "gemini" else 120
                    _mark_cooldown(_prov.slug, seconds=cooldown_secs)
                logger.warning(
                    "[VECTOR][provider_client] {} failed: {}. Trying next...",
                    _prov.slug, str(e)[:80],
                )
                continue

        # -- Observability: record all-providers-failed -----------------------
        try:
            from core.metering.inference_observability import get_inference_observability, extract_domain, is_autonomous_caller
            _obs_latency = (time.perf_counter() - _obs_started) * 1000
            get_inference_observability().record(
                caller_id=caller_id,
                district=district or "",
                domain=extract_domain(caller_id, model),
                tier=tier,
                provider="",
                model=model or "",
                input_tokens=0,
                output_tokens=0,
                latency_ms=_obs_latency,
                providers_tried=_obs_providers_tried,
                is_ollama=False,
                is_autonomous=is_autonomous_caller(caller_id),
                sensitive=sensitive,
                status="error",
                error_kind=_last_error_kind or "unknown",
            )
        except Exception:
            pass  # observability must never break the call path

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
                result = await self._call(prov, model, messages, temperature, max_tokens, tools, api_key=key)
                # Observability only — `attempt` is this loop's own counter,
                # already computed for logging below; stamping it onto the
                # result (same pattern as the existing _tool_calls attribute)
                # exposes "how many within-provider attempts did this call
                # take" without changing what is returned, retried, or timed.
                # attempt=0 means it succeeded on the first try (no retries).
                result._retry_attempts = attempt  # type: ignore[attr-defined]
                return result
            except Rule10PolicyRefusal:
                # A deterministic policy block, never retryable, and never
                # a key/rate-limit problem -- fail over to the next
                # provider immediately, unconditionally, before any of the
                # generic string-matching heuristics below even see it.
                raise
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

                # Rate-limit/quota fast-failover: backing off on a dead key just
                # burns wall-clock time — neither a rate window nor an unpaid
                # balance (402) refills in seconds.
                is_rl = (
                    "429" in err
                    or "402" in err
                    or "rate limit" in low
                    or "insufficient balance" in low
                    or "too many requests" in low
                    or (use_reliable and is_rate_limited(err))
                )
                if is_rl:
                    pool_size = getattr(pool, "size", 1)
                    if pool_size <= 1:
                        # No spare key to rotate to -- hand off to the outer chat()
                        # loop immediately so it can fail over to the next provider,
                        # instead of sleeping through a multi-attempt backoff first.
                        logger.warning(
                            "[VECTOR][provider_client] {} rate-limited, no spare key -- failing over immediately",
                            prov.slug,
                        )
                        raise
                    if attempt == max_retries - 1:
                        raise
                    # Multi-key pool: rotate to a fresh key with ~0 wait instead of backoff.
                    logger.debug(
                        "[VECTOR][provider_client] {} rate-limited -- rotating key (attempt {}/{})",
                        prov.slug, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(0.05)
                    continue

                # A host name that does not resolve will not resolve in 1-2s either
                # (github_models' old base URL, 2026-09): fail over now, don't back off.
                if (
                    "getaddrinfo failed" in low
                    or "name or service not known" in low
                    or "name resolution" in low
                ):
                    logger.warning(
                        "[VECTOR][provider_client] {} host does not resolve -- failing over immediately",
                        prov.slug,
                    )
                    raise

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
        # CLAUDE.md Rule 10 ("Free-tier only at runtime — no paid Anthropic/
        # OpenAI keys at runtime", owner decision 2026-07-08) had no runtime
        # enforcement — only a soft, filtered-out-if-unconfigured mention in
        # route_policy.py's _PREMIUM_HEAVY list and llm_providers.py's
        # `locked_models` whitelist clamp (which only applies to
        # opencode_zen/zai). If the owner (or anything else) ever set a real
        # ANTHROPIC_API_KEY/OPENAI_API_KEY, this call would have gone through
        # as a genuine paid request with zero code-level gate. This is now a
        # hard, explicit-opt-in-only block, matching the rule's own language.
        if prov.slug in _PAID_ANTHROPIC_OPENAI_SLUGS and os.environ.get("VECTOR_ALLOW_PAID_ANTHROPIC_OPENAI") != "1":
            # 2026-09-23 (medium-priority follow-up, decided directly per
            # owner's "plan based on efficiency... do the work" instruction
            # rather than blocking on a design-question round-trip):
            # Keep the opt-in override -- matches this codebase's own
            # convention for owner-controlled policy escape hatches
            # (VECTOR_YELLOW_AUTO_CONFIRM, VECTOR_TRUST_TEST). It requires
            # an actual env var change on the owner's machine; no LLM call
            # inside VECTOR's own runtime can set it.
            #
            # 2026-09-23 round 2 (independent review correction): an
            # earlier version of this fix put "403" in the message so
            # reliable_provider.is_non_retryable() would treat this as
            # non-retryable and fail over immediately instead of retrying a
            # deterministic policy block 3x with backoff. That collided
            # with _call_with_retry()'s OWN "403" check for is_key_err --
            # which, on a multi-key pool (pool.size > 1), deliberately
            # SUPPRESSES the non-retryable raise so it can rotate to
            # another key. A policy refusal has nothing to do with which
            # key was used, so it got retried against every configured key
            # anyway -- the exact waste this fix was supposed to remove. A
            # dedicated exception type sidesteps string-matching entirely:
            # _call_with_retry() below checks for this type FIRST, before
            # any of the generic is_key_err/is_rl/is_non_retryable string
            # heuristics even run.
            raise Rule10PolicyRefusal(
                f"[VECTOR][rule10] refusing paid provider '{prov.slug}' at "
                "runtime -- CLAUDE.md Rule 10: free-tier only at runtime, no "
                "paid Anthropic/OpenAI keys. Set "
                "VECTOR_ALLOW_PAID_ANTHROPIC_OPENAI=1 to explicitly override."
            )
        match prov.driver:
            case "anthropic":
                return await self._call_anthropic(prov, model, messages, temperature, max_tokens, api_key=api_key)
            case "gemini":
                return await self._call_gemini(prov, model, messages, temperature, max_tokens, api_key=api_key)
            case "openai_compat" | "ollama":
                return await self._call_openai_compat(prov, model, messages, temperature, max_tokens, tools, api_key=api_key)
            case _:
                raise ValueError(f"Unknown driver: {prov.driver}")

    def _ssrf_check(self, url: str) -> None:
        """Block SSRF attacks before any outbound HTTP request. Allows private IPs so Ollama (localhost) works."""
        try:
            from core.security.ssrf_guard import SSRFGuard
            result = SSRFGuard(allow_private=True).check_url(url)
            if not result:
                raise RuntimeError(f"[VECTOR][ssrf] blocked provider URL: {result.reason}")
        except ImportError:
            __import__("logging").getLogger(__name__).warning("optional dep import failed", exc_info=True)
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
        self._ssrf_check(url)

        async with _ollama_async_bound(prov):
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

        self._ssrf_check(f"{prov.base_url}/messages")
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

        # gemini-2.5-flash uses a thinking budget; without this, thinking tokens
        # consume maxOutputTokens before any output is generated.
        gen_config: dict = {
            "temperature": temperature,
            "maxOutputTokens": max(max_tokens, 512),  # floor to avoid 0-output on thinking models
        }
        if "2.5" in model:
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}

        payload: dict = {
            "contents": contents,
            "generationConfig": gen_config,
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        url = f"{prov.base_url}/models/{model}:generateContent?key={api_key if api_key is not None else prov.api_key}"
        self._ssrf_check(url)

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
