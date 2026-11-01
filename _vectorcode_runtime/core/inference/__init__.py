"""
VECTOR Inference — unified LLM provider layer.

RULE 11 (UPDATED): Ollama is the PRIMARY runtime (free, local, private).
Any of the 27 providers can be used via API keys — set in .env.
Routing priority: Ollama → configured cloud provider → fallback.

Usage:
    from core.inference import get_client, get_provider, route_for_tier

    client = get_client()
    result = await client.complete("Explain VECTOR", tier="agentic")

    # Explicit provider
    result = await client.complete("Write code", provider="deepseek")

    # Check what's configured
    from core.inference.llm_providers import configured_providers
    for p in configured_providers():
        logger.info(p.slug, p.default_model)

"""
from core.inference.llm_providers import (
    LLMProvider, PROVIDERS, TIER_ROUTING,
    get_provider, configured_providers, route_for_tier, list_free,
)
from core.inference.provider_client import ProviderClient, CompletionResult, get_client

__all__ = [
    "LLMProvider", "PROVIDERS", "TIER_ROUTING",
    "get_provider", "configured_providers", "route_for_tier", "list_free",
    "ProviderClient", "CompletionResult", "get_client",
]
