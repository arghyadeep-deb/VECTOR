# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by core/inference/llm_providers.py (PROVIDERS) and model_catalog.yaml. Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""VECTOR provider capability registry.

This is intentionally small and derived from the providers VECTOR already owns.
It is not a bulk provider catalog.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.inference.llm_providers import PROVIDERS

__all__ = ["ProviderCapability", "list_provider_capabilities", "get_provider_capability"]


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    default_model: str
    models: tuple[str, ...]
    supports_stream: bool
    supports_tools: bool
    supports_vision: bool
    context_window: int
    cost_tier: str
    local: bool
    priority: int


def _cost_tier(provider) -> str:
    if provider.free:
        return "free"
    pricing = provider.pricing_per_1m or {}
    output = float(pricing.get("output", 0.0) or 0.0)
    if output <= 1.0:
        return "low"
    if output <= 8.0:
        return "medium"
    return "high"


def _priority(slug: str, local: bool, free: bool) -> int:
    if slug == "ollama":
        return 100
    if local:
        return 90
    if free:
        return 70
    return 50


def list_provider_capabilities() -> list[ProviderCapability]:
    records: list[ProviderCapability] = []
    for slug, provider in PROVIDERS.items():
        local = provider.driver == "ollama" or slug == "ollama" or "localhost" in provider.base_url
        records.append(ProviderCapability(
            provider=slug,
            default_model=provider.default_model,
            models=tuple(provider.models),
            supports_stream=bool(getattr(provider, 'supports_stream', True)),
            supports_tools=bool(provider.supports_tools),
            supports_vision=bool(provider.supports_vision),
            context_window=int(provider.context_window),
            cost_tier=_cost_tier(provider),
            local=local,
            priority=_priority(slug, local, bool(provider.free)),
        ))
    return sorted(records, key=lambda r: (-r.priority, r.provider))


def get_provider_capability(provider: str) -> ProviderCapability | None:
    for record in list_provider_capabilities():
        if record.provider == provider:
            return record
    return None
