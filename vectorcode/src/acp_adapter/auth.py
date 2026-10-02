"""ACP auth helpers — detect the currently configured VectorCode provider."""

from __future__ import annotations

from typing import Optional

from loguru import logger


def detect_provider() -> Optional[str]:
    """Resolve the active VectorCode runtime provider, or None if unavailable."""
    try:
        from vector_cli.runtime_provider import resolve_runtime_provider
        runtime = resolve_runtime_provider()
        api_key = runtime.get("api_key")
        provider = runtime.get("provider")
        if isinstance(api_key, str) and api_key.strip() and isinstance(provider, str) and provider.strip():
            return provider.strip().lower()
    except Exception as e:
        logger.debug("[VECTOR][acp_adapter] detect_provider failed: {}", e)
        return None
    return None


def has_provider() -> bool:
    """Return True if VectorCode can resolve any runtime provider credentials."""
    return detect_provider() is not None
