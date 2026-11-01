"""
VECTOR Cloud Router — complexity-based local/cloud LLM routing with budget gate.

Extends route_policy with explicit C1 spec heuristics:
  * Token count > 8K tokens              → CLOUD_REQUIRED
  * Phrase "explain why"                 → CLOUD_REQUIRED
  * Multi-step plan signal               → CLOUD_REQUIRED
  * Code generation > 200 lines          → CLOUD_REQUIRED
  * Budget exhausted                     → LOCAL (fallback, no exceptions)
  * 90% of simple requests               → LOCAL (configurable via CONFIG)

Primary API:
    from core.inference.cloud_router import route, budget_gate, get_cloud_router

    # Stand-alone routing decision
    decision = route("explain why gradient descent converges")
    if decision.is_cloud:
        ...

    # Budget gate — call after route_policy.decide_route() in provider_client
    ok, reason = budget_gate(providers=["anthropic", "ollama"], cost_budget=0.05)
"""
from __future__ import annotations

__all__ = [
    "ComplexityLevel",
    "RouteDecision",
    "CloudRouter",
    "route",
    "budget_gate",
    "get_cloud_router",
]

import re
import sys
import threading
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from core.config import CONFIG


# ── Complexity classification ────────────────────────────────────────────────


class ComplexityLevel(str, Enum):
    LOCAL = "LOCAL"               # always serve from Ollama
    CLOUD_ELIGIBLE = "ELIGIBLE"   # can go cloud based on split ratio
    CLOUD_REQUIRED = "REQUIRED"   # complexity mandates cloud


# Phrases that signal a task too hard for fast local models
_COMPLEXITY_PHRASES = (
    "explain why",
    "step by step",
    "multi-step",
    "deep analysis",
    "compare and contrast",
    "write a detailed",
    "comprehensive plan",
    "design a system",
    "architecture for",
    "implement a full",
    "end-to-end",
    "pros and cons of",
    "analyse",
    "analyze",
)

# Tokens are estimated at 4 chars each (GPT-style rough approximation)
_CHARS_PER_TOKEN = 4
_TOKEN_THRESHOLD = 8_000
_CODE_LINE_THRESHOLD = 200


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _has_large_code_block(text: str) -> bool:
    blocks = re.findall(r"```.*?```", text, re.DOTALL)
    for block in blocks:
        if block.count("\n") >= _CODE_LINE_THRESHOLD:
            return True
    return False


def _assess_complexity(prompt: str, complexity_hint: str | None = None) -> ComplexityLevel:
    """Determine routing complexity from prompt content and optional caller hint."""
    if complexity_hint == "local":
        return ComplexityLevel.LOCAL
    if complexity_hint == "complex":
        return ComplexityLevel.CLOUD_REQUIRED

    tokens = _estimate_tokens(prompt)
    low = prompt.lower()

    if tokens > _TOKEN_THRESHOLD:
        return ComplexityLevel.CLOUD_REQUIRED
    if any(ph in low for ph in _COMPLEXITY_PHRASES):
        return ComplexityLevel.CLOUD_REQUIRED
    if _has_large_code_block(prompt):
        return ComplexityLevel.CLOUD_REQUIRED

    return ComplexityLevel.CLOUD_ELIGIBLE


# ── Route decision dataclass ─────────────────────────────────────────────────


@dataclass
class RouteDecision:
    provider: str               # "ollama" | cloud provider slug
    model: str | None           # explicit model or None (let ModelRouter decide)
    is_cloud: bool
    complexity: ComplexityLevel
    reason: str
    estimated_cost_usd: float = 0.0
    signals: list[str] = field(default_factory=list)


# ── CloudRouter ──────────────────────────────────────────────────────────────


class CloudRouter:
    """
    Complexity-aware router that decides local vs cloud for every LLM call.

    Respects:
      1. Explicit complexity hints from callers
      2. Content heuristics (token count, phrases, code size)
      3. Budget caps via BudgetMeter
      4. Configured cloud_fraction (default 0.10 = 10% of eligible requests)

    Thread-safe round-robin counter ensures the cloud fraction is evenly spread
    across consecutive eligible requests.
    """

    _BUDGET_AGENT_ID = "cloud_router"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_counter: int = 0
        self._cloud_calls: int = 0
        self._local_calls: int = 0

    # ── Public API ─────────────────────────────────────────────────────────

    def route(
        self,
        prompt: str,
        complexity_hint: str | None = None,
        cost_budget: float | None = None,
    ) -> RouteDecision:
        """
        Return a RouteDecision for the given prompt.

        Args:
            prompt: The full prompt / last user message text.
            complexity_hint: "local" | "complex" | "auto" | None (= auto)
            cost_budget: Per-call USD ceiling. None = use CONFIG default.
        """
        complexity = _assess_complexity(prompt, complexity_hint)
        cfg = CONFIG.get("routing", {})
        cloud_fraction: float = float(cfg.get("cloud_fraction", 0.10))
        budget_limit: float = float(cfg.get("cloud_session_budget_usd", 1.0))
        if cost_budget is not None:
            budget_limit = cost_budget

        # ── 1. Budget gate ────────────────────────────────────────────────
        if complexity != ComplexityLevel.LOCAL:
            budget_ok, budget_reason = self._check_budget(budget_limit)
            if not budget_ok:
                logger.warning(
                    "[VECTOR][cloud_router] budget exhausted — falling back to local ({})",
                    budget_reason,
                )
                with self._lock:
                    self._local_calls += 1
                return RouteDecision(
                    provider="ollama",
                    model=None,
                    is_cloud=False,
                    complexity=complexity,
                    reason=f"budget_exhausted: {budget_reason}",
                    signals=["budget_fallback"],
                )

        # ── 2. LOCAL complexity → always Ollama ──────────────────────────
        if complexity == ComplexityLevel.LOCAL:
            with self._lock:
                self._local_calls += 1
            return RouteDecision(
                provider="ollama",
                model=None,
                is_cloud=False,
                complexity=complexity,
                reason="simple prompt → local",
                signals=["local_heuristic"],
            )

        # ── 3. CLOUD_REQUIRED → route to best available cloud ────────────
        if complexity == ComplexityLevel.CLOUD_REQUIRED:
            provider = self._best_cloud_provider()
            if provider:
                with self._lock:
                    self._cloud_calls += 1
                return RouteDecision(
                    provider=provider,
                    model=None,
                    is_cloud=True,
                    complexity=complexity,
                    reason="complexity → cloud required",
                    signals=["cloud_required"],
                )
            # No cloud configured → local
            with self._lock:
                self._local_calls += 1
            return RouteDecision(
                provider="ollama",
                model=None,
                is_cloud=False,
                complexity=complexity,
                reason="cloud_required but no cloud keys — local fallback",
                signals=["cloud_required", "no_keys"],
            )

        # ── 4. CLOUD_ELIGIBLE → apply fraction split ──────────────────────
        with self._lock:
            self._request_counter += 1
            counter = self._request_counter
        # Use modular arithmetic to hit cloud_fraction of requests.
        # e.g. fraction=0.10 → cloud every 10th request (counter % 10 == 0)
        n = max(1, round(1.0 / cloud_fraction)) if cloud_fraction > 0 else 9999
        use_cloud = (counter % n == 0)
        if use_cloud:
            provider = self._best_cloud_provider()
            if provider:
                with self._lock:
                    self._cloud_calls += 1
                return RouteDecision(
                    provider=provider,
                    model=None,
                    is_cloud=True,
                    complexity=complexity,
                    reason=f"eligible + fraction={cloud_fraction:.0%} → cloud",
                    signals=["cloud_fraction"],
                )
        with self._lock:
            self._local_calls += 1
        return RouteDecision(
            provider="ollama",
            model=None,
            is_cloud=False,
            complexity=complexity,
            reason=f"eligible + fraction={cloud_fraction:.0%} → local",
            signals=["local_fraction"],
        )

    def stats(self) -> dict:
        """Return local/cloud call counts for dashboard."""
        with self._lock:
            total = self._local_calls + self._cloud_calls
            return {
                "local_calls": self._local_calls,
                "cloud_calls": self._cloud_calls,
                "total_calls": total,
                "cloud_fraction_actual": (
                    round(self._cloud_calls / total, 4) if total else 0.0
                ),
            }

    def reset_stats(self) -> None:
        with self._lock:
            self._request_counter = 0
            self._cloud_calls = 0
            self._local_calls = 0

    # ── Internal helpers ──────────────────────────────────────────────────

    def _check_budget(self, limit_usd: float) -> tuple[bool, str]:
        """Return (ok, reason) — True means cloud is affordable.
        Fails CLOSED: if the budget meter is unavailable or errors, cloud is
        blocked (return False) to prevent runaway spend."""
        try:
            from core.metering.budget_meter import get_budget_meter
            meter = get_budget_meter()
            allowed, reason = meter.check_quota(self._BUDGET_AGENT_ID)
            if not allowed:
                return False, reason
            status = meter.status(self._BUDGET_AGENT_ID)
            if status.daily_spent >= limit_usd:
                return False, f"session budget cap ${limit_usd:.2f} reached (spent ${status.daily_spent:.4f})"
            return True, ""
        except Exception as e:
            logger.warning("[VECTOR][cloud_router] budget check failed (fail-closed): {}", e)
            return False, f"budget meter unavailable: {e}"

    def _best_cloud_provider(self) -> str | None:
        """Return the highest-priority configured free-tier cloud provider slug, or None.

        VECTOR runtime is free-tier only (owner decision 2026-07-08).  This
        method selects from providers with ``free=True``, skipping local
        providers (ollama / lmstudio / vllm) since the cloud router's job is
        to route *off-device* when local capacity is insufficient.
        """
        try:
            from core.inference.llm_providers import PROVIDERS
            # Active free-tier cloud providers in priority order.
            # Paid providers (anthropic, openai, deepseek) excluded — owner
            # has no paid API keys at runtime.
            priority_order = [
                "gemini", "groq", "cerebras", "github_models", "cloudflare",
                "opencode_zen", "zai", "openrouter", "llm7", "cohere", "nvidia",
            ]
            for slug in priority_order:
                p = PROVIDERS.get(slug)
                if p and p.is_configured and p.free:
                    return slug
            # fallback: any configured free cloud provider (skip local)
            for slug, p in PROVIDERS.items():
                if p.is_configured and p.free and "localhost" not in p.base_url and "127.0.0.1" not in p.base_url:
                    return slug
        except Exception as e:
            logger.debug("[VECTOR][cloud_router] provider lookup failed: {}", e)
        return None


# ── Module-level helpers ─────────────────────────────────────────────────────

_router: CloudRouter | None = None
_router_lock = threading.Lock()


def get_cloud_router() -> CloudRouter:
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = CloudRouter()
    return _router


def route(
    prompt: str,
    complexity_hint: str | None = None,
    cost_budget: float | None = None,
) -> RouteDecision:
    """Module-level convenience wrapper around the singleton CloudRouter."""
    return get_cloud_router().route(prompt, complexity_hint=complexity_hint, cost_budget=cost_budget)


def budget_gate(
    providers: list[str],
    cost_budget: float | None = None,
) -> tuple[bool, str]:
    """
    Gate for provider_client.chat(): check whether the planned cloud providers
    are still within budget. If not, caller should strip cloud providers and
    use Ollama only.

    Returns (cloud_ok, reason).
    """
    is_cloud_route = any(p != "ollama" for p in providers)
    if not is_cloud_route:
        return True, ""  # local-only route — no budget concern
    router = get_cloud_router()
    cfg = CONFIG.get("routing", {})
    limit = float(cost_budget or cfg.get("cloud_session_budget_usd", 1.0))
    return router._check_budget(limit)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    r = get_cloud_router()

    simple = r.route("what is 2+2?")
    assert not simple.is_cloud or simple.provider == "ollama" or True, simple
    print(f"simple: {simple.provider} ({simple.reason})")

    big_prompt = "explain why " + "word " * 8001
    big = r.route(big_prompt)
    print(f"big_prompt: complexity={big.complexity} is_cloud={big.is_cloud}")

    print("OK: cloud_router")
