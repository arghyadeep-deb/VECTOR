"""
VECTOR Model Router — hint-based tier routing.

Ported from vector's providers/router.rs.

Maps abstract task tiers to the right local Ollama model.
Integrates with VECTOR's existing model routing in models.md.

Tiers (VECTOR-specific, Ollama-first):
  reasoning     → deepseek-r1:14b  (chain-of-thought)
  agentic       → vector-focus     (real-time default)
  coding        → vector-coder     (code specialist)
  summarization → vector-focus (fast, low-latency)
  multilingual  → vector-multilingual (HI/BN/AS/JA/EN)
  deep          → qwen3:14b       (overnight/long context)
  council       → vector-reasoning  (high-stakes decisions)
"""
from __future__ import annotations

__all__ = [
    "get_router",
    "ModelRouter",
    "ModelTier",
    "Route",
    "route",
]


from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from core.config import CONFIG


class ModelTier(str, Enum):
    REASONING     = "reasoning"
    AGENTIC       = "agentic"
    CODING        = "coding"
    SUMMARIZATION = "summarization"
    MULTILINGUAL  = "multilingual"
    DEEP          = "deep"
    COUNCIL       = "council"
    FAST          = "fast"


# VECTOR model routing table (mirrors models.md)
_DEFAULT_ROUTES: dict[ModelTier, str] = {
    ModelTier.REASONING:     "deepseek-r1:14b",
    ModelTier.AGENTIC:       "vector-focus",
    ModelTier.CODING:        "vector-coder",
    ModelTier.SUMMARIZATION: "vector-focus",
    ModelTier.MULTILINGUAL:  "vector-multilingual",
    ModelTier.DEEP:          "qwen3:14b",
    ModelTier.COUNCIL:       "vector-reasoning",
    ModelTier.FAST:          "gemma4:e4b",
}

# Abstract tier name aliases (vector compatibility)
_TIER_ALIASES: dict[str, ModelTier] = {
    "reasoning-v1":       ModelTier.REASONING,
    "reasoning-quick-v1": ModelTier.FAST,
    "agentic-v1":         ModelTier.AGENTIC,
    "coding-v1":          ModelTier.CODING,
    "summarization-v1":   ModelTier.SUMMARIZATION,
    # VECTOR-native aliases
    "think":    ModelTier.REASONING,
    "code":     ModelTier.CODING,
    "summarize": ModelTier.SUMMARIZATION,
    "fast":     ModelTier.FAST,
    "deep":     ModelTier.DEEP,
    "council":  ModelTier.COUNCIL,
}


@dataclass
class Route:
    model: str
    base_url: str = "http://localhost:11434/v1"
    tier: ModelTier | None = None


class ModelRouter:
    """
    Routes task requests to the appropriate Ollama model.

    Resolution order (mirrors vector router.rs):
      1. hint:<tier>  — direct tier lookup (e.g. "hint:coding")
      2. Abstract tier names (e.g. "coding-v1" → coding tier)
      3. Exact model name passthrough (e.g. "qwen3:14b")
      4. Default (agentic tier)

    Usage:
        router = ModelRouter()
        route = router.resolve("coding-v1")
        # → Route(model="vector-coder", tier=ModelTier.CODING)

        route = router.resolve("hint:reasoning")
        # → Route(model="deepseek-r1:14b", tier=ModelTier.REASONING)

        router.override(ModelTier.CODING, "qwen3:14b")  # swap model
    """

    def __init__(
        self,
        routes: dict[ModelTier, str] | None = None,
        default_tier: ModelTier = ModelTier.AGENTIC,
        base_url: str = "http://localhost:11434/v1",
    ) -> None:
        self._routes: dict[ModelTier, str] = _active_default_routes()
        if routes:
            self._routes.update(routes)
        self._default_tier = default_tier
        self._base_url = base_url

    def resolve(self, model_or_hint: str) -> Route:
        """Resolve a model name / hint / tier alias to a Route."""
        spec = model_or_hint.strip()

        # 1. hint:<tier> syntax
        if spec.startswith("hint:"):
            tier_name = spec[5:]
            try:
                tier = ModelTier(tier_name)
                return self._route_for_tier(tier)
            except ValueError:
                logger.warning("[VECTOR][model_router] unknown hint tier: {}", tier_name)

        # 2. Abstract tier alias
        if spec in _TIER_ALIASES:
            tier = _TIER_ALIASES[spec]
            return self._route_for_tier(tier)

        # 3. Direct ModelTier enum value
        try:
            tier = ModelTier(spec)
            return self._route_for_tier(tier)
        except ValueError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        # 4. Exact model passthrough (known Ollama model)
        if ":" in spec or "/" in spec or spec in self._routes.values():
            return Route(model=spec, base_url=self._base_url)

        # 5. Default
        logger.debug("[VECTOR][model_router] passthrough model: {}", spec)
        return Route(model=spec, base_url=self._base_url)

    def _route_for_tier(self, tier: ModelTier) -> Route:
        model = self._routes.get(tier, self._routes[self._default_tier])
        logger.debug("[VECTOR][model_router] tier={} → model={}", tier.value, model)
        return Route(model=model, base_url=self._base_url, tier=tier)

    def override(self, tier: ModelTier, model: str) -> None:
        """Override the model for a specific tier."""
        self._routes[tier] = model
        logger.info("[VECTOR][model_router] override: {} → {}", tier.value, model)

    def model_for(self, tier: ModelTier) -> str:
        return self._routes.get(tier, self._routes[self._default_tier])

    def all_routes(self) -> dict[str, str]:
        return {tier.value: model for tier, model in self._routes.items()}


# Singleton
_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def _active_default_routes() -> dict[ModelTier, str]:
    """Return local routes from CONFIG without changing production defaults."""
    routes = dict(_DEFAULT_ROUTES)
    try:
        models = CONFIG["models"]
        if CONFIG.get("model_profile") == "uncensored":
            routes.update(
                {
                    ModelTier.REASONING: models["r1"],
                    ModelTier.AGENTIC: models["focus"],
                    ModelTier.CODING: models["coder"],
                    ModelTier.SUMMARIZATION: models["focus"],
                    ModelTier.MULTILINGUAL: models["multilingual"],
                    ModelTier.DEEP: models["reasoning"],
                    ModelTier.COUNCIL: models["reasoning"],
                    ModelTier.FAST: models["focus"],
                }
            )
    except Exception as exc:
        logger.debug("[VECTOR][model_router] active profile unavailable: {}", exc)
    return routes


def route(model_or_hint: str) -> Route:
    """Convenience: resolve via singleton router."""
    return get_router().resolve(model_or_hint)


if __name__ == "__main__":
    r = ModelRouter()

    # hint syntax
    assert r.resolve("hint:coding").model == "vector-coder"
    assert r.resolve("hint:reasoning").model == "deepseek-r1:14b"

    # abstract tier alias
    assert r.resolve("coding-v1").model == "vector-coder"
    assert r.resolve("reasoning-v1").model == "deepseek-r1:14b"
    assert r.resolve("agentic-v1").model == "vector-focus"

    # passthrough
    assert r.resolve("qwen3:14b").model == "qwen3:14b"

    # override
    r.override(ModelTier.CODING, "qwen3:14b")
    assert r.resolve("hint:coding").model == "qwen3:14b"

    routes = r.all_routes()
    assert len(routes) == len(ModelTier)

    print(f"OK model_router.py — {len(routes)} tiers, all routes verified")
