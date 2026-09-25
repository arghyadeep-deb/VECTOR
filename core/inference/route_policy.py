"""
VECTOR routing policy — decide local-vs-cloud per task.

Owner's policy:
  * Security / privacy / RED-tier / secret-bearing tasks  -> Ollama LOCAL only
    (never leaves the device).
  * Simple/medium, non-sensitive tasks                    -> pooled cloud keys,
    load-balanced across configured cloud providers (fastest reply).
  * Heavy (COMPLEX/REASONING), non-sensitive tasks        -> cloud premium first
    (anthropic/openai/deepseek), local gemma4:26b as fallback.
    Flip with CONFIG['routing']['prefer_local_for_heavy'] = True.

Reuses the dormant 15-dim complexity classifier in
core/inference/smart_routing/classifier.py instead of a new heuristic.
"""
from __future__ import annotations

__all__ = ["RoutePlan", "decide_route"]

import itertools
import sys
from dataclasses import dataclass, field

from loguru import logger

from core.config import CONFIG
from core.inference.llm_providers import PROVIDERS


_SENSITIVE_DISTRICTS = {"security", "privacy"}
# Best-quality providers for heavy/complex work, FREE-first (owner has no paid
# OpenAI/Anthropic keys): GitHub Models serves gpt-5/o3 free via GITHUB_TOKEN;
# Cerebras serves gpt-oss-120b free. Unconfigured/paid ones are filtered
# out downstream, so keeping anthropic/openai/deepseek here is harmless (they
# activate only if the owner ever adds those keys/balance).
_PREMIUM_HEAVY = ["github_models", "cerebras", "anthropic", "openai", "deepseek"]
# Substrings that mean "do not send this to a third party"
_SECRET_MARKERS = (
    "password", "api key", "api_key", "secret key", "private key",
    "-----begin", "ssh-rsa", "client_secret", "bearer ", "credit card",
    "cvv", "aadhaar", "passport number",
)

# Rotating offset so concurrent simple tasks spread across cloud providers
_rr = itertools.count()


@dataclass
class RoutePlan:
    tier: str                       # maps to model via existing ModelRouter/TIER_ROUTING
    providers: list[str]            # ordered provider slugs to try
    local_only: bool = False
    reason: str = ""
    signals: list[str] = field(default_factory=list)


def _is_local(slug: str) -> bool:
    p = PROVIDERS.get(slug)
    if not p:
        return False
    return p.free or "localhost" in p.base_url or "127.0.0.1" in p.base_url


def _configured_cloud() -> list[str]:
    return [slug for slug, p in PROVIDERS.items() if not _is_local(slug) and p.is_configured]


def _looks_secret(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _SECRET_MARKERS)


def _classify_tier(prompt: str) -> str:
    """Return SIMPLE | MEDIUM | COMPLEX | REASONING (falls back to MEDIUM)."""
    try:
        from core.inference.smart_routing.classifier import classify
        d = classify(prompt)
        if d.tier is not None:
            return d.tier.value
    except Exception as e:
        logger.debug("[VECTOR][route_policy] classifier unavailable: {}", e)
    # heuristic fallback: long prompts lean heavy
    return "COMPLEX" if len(prompt.split()) > 200 else "MEDIUM"


def decide_route(
    prompt: str,
    *,
    district: str | None = None,
    permission_tier: str | None = None,
    sensitive: bool = False,
) -> RoutePlan:
    """Pick local-vs-cloud + provider order for a task."""
    routing_cfg = CONFIG.get("routing", {})
    prefer_local_heavy = bool(routing_cfg.get("prefer_local_for_heavy", False))
    distribute = bool(routing_cfg.get("distribute_simple", True))

    # ── 1. Sensitivity gate → local only ───────────────────────────────────
    is_sensitive = (
        sensitive
        or (district or "").lower() in _SENSITIVE_DISTRICTS
        or (permission_tier or "").upper() == "RED"
        or _looks_secret(prompt)
    )
    if is_sensitive:
        return RoutePlan(
            tier="reasoning",
            providers=["ollama"],
            local_only=True,
            reason=f"sensitive (district={district}, tier={permission_tier}) → local only",
            signals=["sensitive"],
        )

    cloud = _configured_cloud()

    # ── 2. No cloud keys configured → local ────────────────────────────────
    if not cloud:
        return RoutePlan(tier="agentic", providers=["ollama"],
                         reason="no cloud keys configured → local", signals=["offline"])

    tier_class = _classify_tier(prompt)

    # ── 3. Heavy (non-sensitive) → cloud premium first, local fallback ─────
    if tier_class in ("COMPLEX", "REASONING"):
        premium = [s for s in _PREMIUM_HEAVY if s in cloud]
        rest = [s for s in cloud if s not in premium]
        order = premium + rest
        if prefer_local_heavy:
            providers = ["ollama"] + order
        else:
            providers = order + ["ollama"]
        return RoutePlan(tier="reasoning", providers=providers,
                         reason=f"{tier_class} → {'local-first' if prefer_local_heavy else 'cloud-premium'}",
                         signals=[tier_class])

    # ── 4. Simple/medium → load-balanced pooled cloud keys, local fallback ─
    order = list(cloud)
    if distribute and len(order) > 1:
        off = next(_rr) % len(order)
        order = order[off:] + order[:off]   # rotate start for even spread
    return RoutePlan(tier="fast", providers=order + ["ollama"],
                     reason=f"{tier_class} → cloud distribute", signals=[tier_class])


if __name__ == "__main__":
    import os
    sys.stdout.reconfigure(encoding="utf-8")

    # Ensure at least one cloud provider looks configured for the test
    os.environ.setdefault("GEMINI_API_KEY", "test-key")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    from core.inference.key_pool import reset_pools
    reset_pools()

    sec = decide_route("scan this binary for malware", district="security")
    assert sec.local_only and sec.providers == ["ollama"], sec

    secret = decide_route("here is my password: hunter2, store it")
    assert secret.local_only, secret

    simple = decide_route("what is the capital of France?")
    assert not simple.local_only and simple.providers[-1] == "ollama", simple
    assert simple.tier == "fast", simple

    heavy = decide_route("Prove step by step that there are infinitely many primes, "
                         "with a formal chain of thought and rigorous reasoning")
    assert not heavy.local_only and heavy.tier == "reasoning", heavy

    print("OK route_policy.py — sensitive→local, secret→local, simple→cloud, heavy→reasoning")
