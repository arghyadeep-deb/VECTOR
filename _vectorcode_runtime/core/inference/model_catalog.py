"""Model catalog — data-driven per-provider model selection + domain chains.

Loads `model_catalog.yaml` (owner-editable, same pattern as
core/engine/oauth/providers.py: YAML → dataclasses → hardcoded fallback).

Three consumers:
  1. provider_client._model_for_provider → select_model(slug, tier): the best
     model THIS provider offers for THIS tier (rank 1 = best), replacing the
     old single-default behavior.
  2. provider_client._enforce_whitelist → is_model_allowed(slug, model_id):
     HARD guardrail for locked providers (opencode_zen, zai — keys that can
     reach paid models) and pattern-gated ones (openrouter ":free$").
  3. vectorcode_llm domain routing → chain_for_domain(name): ordered
     (provider, model) fallback chains, registered into model_pool as
     logical models "domain:<name>" so the existing expansion/cooldown
     machinery does all the work.

Design rules: no imports from llm_providers/provider_client (no cycles),
zero network at import, and the no-YAML fallback keeps the locked-provider
whitelists — the paid-model guardrail must not depend on PyYAML.
"""

import sys
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

_YAML_PATH = Path(__file__).parent / "model_catalog.yaml"

# "heavy" is a capability tag, not a routing tier — resolve under "reasoning".
_TIER_ALIASES = {"heavy": "reasoning"}


@dataclass
class ModelLimits:
    requests_per_day: int | None = None
    requests_per_min: float | None = None
    tokens_per_day: int | None = None
    tokens_per_min: int | None = None
    neurons_per_day: int | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "ModelLimits | None":
        if not d:
            return None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CatalogModel:
    model_id: str
    tiers: dict[str, int] = field(default_factory=dict)   # tier -> rank (1=best)
    limits: ModelLimits | None = None


@dataclass
class ProviderCatalog:
    slug: str
    quota_unit: str = "requests"          # requests | tokens | neurons
    per_model_quota: bool = False
    locked: bool = False                  # hard whitelist
    allow_pattern: str = ""               # regex the model id must match
    limits: ModelLimits | None = None     # provider-wide
    models: dict[str, CatalogModel] = field(default_factory=dict)

    def best_for_tier(self, tier: str) -> str | None:
        """Model id with the lowest rank for this tier (aliases resolved)."""
        tier = _TIER_ALIASES.get(tier, tier)
        best_id, best_rank = None, None
        for mid, m in self.models.items():
            ranks = [r for t, r in m.tiers.items()
                     if _TIER_ALIASES.get(t, t) == tier]
            if not ranks:
                continue
            r = min(ranks)
            if best_rank is None or r < best_rank:
                best_id, best_rank = mid, r
        return best_id

    def is_allowed(self, model_id: str) -> bool:
        if self.locked:
            return model_id in self.models
        if self.allow_pattern:
            return bool(re.search(self.allow_pattern, model_id))
        return True


@dataclass
class DomainChain:
    name: str
    chain: list[tuple[str, str]] = field(default_factory=list)  # (provider, model)
    local_only: bool = False


# ── loading ──────────────────────────────────────────────────────────────────

def _parse(raw: dict) -> tuple[dict[str, ProviderCatalog], dict[str, DomainChain]]:
    providers: dict[str, ProviderCatalog] = {}
    for slug, pdata in (raw.get("providers") or {}).items():
        pdata = pdata or {}
        models = {}
        for mid, mdata in (pdata.get("models") or {}).items():
            mdata = mdata or {}
            models[str(mid)] = CatalogModel(
                model_id=str(mid),
                tiers={str(t): int(r) for t, r in (mdata.get("tiers") or {}).items()},
                limits=ModelLimits.from_dict(mdata.get("limits")),
            )
        providers[slug] = ProviderCatalog(
            slug=slug,
            quota_unit=pdata.get("quota_unit", "requests"),
            per_model_quota=bool(pdata.get("per_model_quota", False)),
            locked=bool(pdata.get("locked", False)),
            allow_pattern=pdata.get("allow_pattern", "") or "",
            limits=ModelLimits.from_dict(pdata.get("limits")),
            models=models,
        )
    domains: dict[str, DomainChain] = {}
    for name, ddata in (raw.get("domains") or {}).items():
        ddata = ddata or {}
        chain = [(str(p), str(m)) for p, m in (ddata.get("chain") or [])]
        domains[name] = DomainChain(
            name=name, chain=chain,
            local_only=bool(ddata.get("local_only", False)),
        )
    return providers, domains


def _load_from_yaml() -> tuple[dict[str, ProviderCatalog], dict[str, DomainChain]]:
    import yaml
    with open(_YAML_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _parse(raw)


def _load_fallback() -> tuple[dict[str, ProviderCatalog], dict[str, DomainChain]]:
    """Minimal catalog when PyYAML/file is unavailable. MUST keep the locked
    whitelists — the paid-model guardrail cannot depend on YAML — plus the
    top pick per major tier for the biggest providers."""
    zen_models = ["deepseek-v4-flash-free", "big-pickle", "mimo-v2.5-free",
                  "north-mini-code-free", "nemotron-3-ultra-free"]
    providers = {
        "opencode_zen": ProviderCatalog(
            slug="opencode_zen", locked=True,
            models={m: CatalogModel(model_id=m) for m in zen_models}),
        "zai": ProviderCatalog(
            slug="zai", locked=True,
            models={m: CatalogModel(model_id=m) for m in
                    ["glm-4.7-flash", "glm-4.5-flash", "glm-4.6V-flash"]}),
        "openrouter": ProviderCatalog(slug="openrouter", allow_pattern=":free$"),
        "groq": ProviderCatalog(slug="groq", quota_unit="requests", models={
            "openai/gpt-oss-20b": CatalogModel(
                "openai/gpt-oss-20b", tiers={"fast": 1, "agentic": 1}),
            "openai/gpt-oss-120b": CatalogModel(
                "openai/gpt-oss-120b",
                tiers={"agentic": 2, "reasoning": 2, "heavy": 2, "council": 2}),
        }),
        "cerebras": ProviderCatalog(slug="cerebras", quota_unit="tokens", models={
            "gpt-oss-120b": CatalogModel(
                "gpt-oss-120b", tiers={"fast": 1, "reasoning": 1, "heavy": 1, "council": 1}),
        }),
        "cloudflare": ProviderCatalog(slug="cloudflare", quota_unit="neurons", models={
            "@cf/moonshotai/kimi-k2.7-code": CatalogModel(
                "@cf/moonshotai/kimi-k2.7-code", tiers={"coding": 1}),
        }),
        "github_models": ProviderCatalog(slug="github_models", models={
            "Codestral-25.01": CatalogModel("Codestral-25.01", tiers={"coding": 1}),
            "gpt-5": CatalogModel("gpt-5", tiers={"reasoning": 1, "saas": 1}),
        }),
    }
    domains = {
        "security": DomainChain("security", chain=[("ollama", "vector-reasoning")],
                                local_only=True),
    }
    return providers, domains


_lock = threading.Lock()
_providers: dict[str, ProviderCatalog] | None = None
_domains: dict[str, DomainChain] | None = None


def _ensure_loaded() -> None:
    global _providers, _domains
    if _providers is not None:
        return
    with _lock:
        if _providers is not None:
            return
        try:
            _providers, _domains = _load_from_yaml()
            logger.info(f"[VECTOR][catalog] model catalog loaded: "
                        f"{len(_providers)} providers, {len(_domains)} domains")
        except Exception as e:
            logger.warning(f"[VECTOR][catalog] YAML load failed ({e}) — using fallback")
            _providers, _domains = _load_fallback()
        _register_domain_pool_models()


def _register_domain_pool_models() -> None:
    """Register each domain chain as a model_pool logical model
    "domain:<name>" — provider_client's existing logical-model expansion,
    cooldown, and whitelist machinery then handles everything."""
    try:
        from core.inference.model_pool import MODEL_POOL
        for name, dom in (_domains or {}).items():
            key = f"domain:{name}"
            if dom.chain:
                MODEL_POOL[key] = _active_local_chain(dom.chain)  # always refresh (supports reload)
        logger.debug(f"[VECTOR][catalog] registered {len(_domains or {})} domain pools")
    except Exception as e:
        logger.debug(f"[VECTOR][catalog] domain pool registration skipped: {e}")


def reload_catalog() -> None:
    """Re-read the YAML (owner edits / tests)."""
    global _providers, _domains
    with _lock:
        _providers = None
        _domains = None
    _ensure_loaded()


def get_catalog() -> dict[str, ProviderCatalog]:
    _ensure_loaded()
    return _providers or {}


def get_domains() -> dict[str, DomainChain]:
    _ensure_loaded()
    return _domains or {}


# ── the three consumer APIs ──────────────────────────────────────────────────

def select_model(provider_slug: str, tier: str) -> str | None:
    """Best model this provider offers for this tier, or None."""
    try:
        cat = get_catalog().get(provider_slug)
        return cat.best_for_tier(tier) if cat else None
    except Exception as e:
        logger.debug(f"[VECTOR][catalog] select_model failed: {e}")
        return None


def is_model_allowed(provider_slug: str, model_id: str) -> bool:
    """Whitelist/pattern gate. True when the provider isn't cataloged
    (unknown providers keep today's behavior)."""
    try:
        cat = get_catalog().get(provider_slug)
        return cat.is_allowed(model_id) if cat else True
    except Exception as e:
        # Fail CLOSED for the known locked providers, open otherwise.
        logger.debug(f"[VECTOR][catalog] is_model_allowed failed: {e}")
        return provider_slug not in ("opencode_zen", "zai")


def chain_for_domain(domain: str) -> list[tuple[str, str]]:
    d = get_domains().get(domain)
    return _active_local_chain(d.chain) if d else []


def _active_local_chain(chain: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Map stable YAML Ollama aliases through the active local profile."""
    try:
        from core.config import CONFIG
        from core.inference.model_profiles import active_alias_for_production_model

        models = CONFIG.get("models", {})
        return [
            (
                provider,
                active_alias_for_production_model(model, models)
                if provider == "ollama"
                else model,
            )
            for provider, model in chain
        ]
    except Exception as exc:
        logger.debug("[VECTOR][catalog] active local profile unavailable: {}", exc)
        return list(chain)


def domain_local_only(domain: str) -> bool:
    d = get_domains().get(domain)
    return bool(d and d.local_only)


if __name__ == "__main__":
    # real test, no mocks
    ok = True
    cat = get_catalog()
    ok &= len(cat) >= 10
    ok &= select_model("cloudflare", "coding") == "@cf/moonshotai/kimi-k2.7-code"
    ok &= select_model("cerebras", "heavy") == "gpt-oss-120b"      # alias → reasoning
    ok &= is_model_allowed("opencode_zen", "gpt-5.5") is False    # guardrail
    ok &= is_model_allowed("opencode_zen", "big-pickle") is True
    ok &= is_model_allowed("zai", "glm-4.5") is False             # paid model blocked
    ok &= is_model_allowed("openrouter", "anthropic/claude-sonnet-5") is False
    ok &= is_model_allowed("openrouter", "qwen/qwen3-coder:free") is True
    ok &= domain_local_only("security") is True
    ok &= chain_for_domain("coding.review")[-1][0] == "ollama"    # terminal fallback

    # freellmapi must never appear in an autonomous domain chain — it's
    # coding-only, explicit-selection (see vectorcode/src/providers/coding_catalog.py).
    ok &= select_model("freellmapi", "fast") is None
    ok &= all("freellmapi" not in (p for p, _ in chain_for_domain(d))
              for d in ("agentic.loop", "coding.generation", "orchestration",
                        "summarization", "research"))
    from core.inference.model_pool import MODEL_POOL
    ok &= "domain:agentic.loop" in MODEL_POOL
    print("✅ model_catalog.py OK" if ok else "❌ FAILED")
