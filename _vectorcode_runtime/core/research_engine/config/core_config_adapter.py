"""Adapter layer: map research_engine settings to VECTOR core.config.

This module provides a thin compatibility shim so that research_engine code
can read settings from core.config.CONFIG while preserving the existing
get_setting_from_snapshot() API used by 400+ call sites.

Usage (drop-in replacement for existing imports):
    from core.research_engine.config.core_config_adapter import (
        get_setting_from_snapshot,
        get_bool_setting_from_snapshot,
    )
"""
from __future__ import annotations

__all__ = [
    "get_bool_setting_from_snapshot",
    "get_setting_from_snapshot",
]


from typing import Any

from loguru import logger

try:
    from core.config import CONFIG
    _HAS_CORE_CONFIG = True
except ImportError:
    CONFIG = {}
    _HAS_CORE_CONFIG = False

# ── Setting key mapping: research_engine keys → core.config paths ─────────────

_KEY_MAP: dict[str, tuple[str, ...]] = {
    # LLM / API keys
    "llm.api_key": ("api_keys", "anthropic_key"),
    "llm.openai_api_key": ("api_keys", "openai_key"),
    "llm.gemini_api_key": ("api_keys", "gemini_key"),
    "llm.provider": ("models", "focus"),  # VECTOR uses named model slots
    "llm.model": ("models", "focus"),
    "llm.temperature": ("models", "temperature"),
    "llm.max_tokens": ("models", "max_tokens"),
    "llm.context_window": ("models", "context_window"),
    "llm.base_url": ("models", "base_url"),
    # Ollama
    "ollama.host": ("ollama_host",),
    "ollama.model": ("models", "focus"),
    # Search
    "search.api_key": ("api_keys", "newsapi_key"),
    "search.provider": ("search", "provider"),
    # Security
    "security.ssrf_enabled": ("security", "ssrf_enabled"),
    # App
    "app.version": ("version",),
    "app.debug": ("debug",),
    "app.env": ("env",),
}


def _resolve_key(key: str) -> Any:
    """Look up a research_engine key in core.config. Returns None if not found."""
    if not _HAS_CORE_CONFIG:
        return None
    path = _KEY_MAP.get(key)
    if path is None:
        return None
    # Single-key lookup (top-level env var name)
    if len(path) == 1:
        return CONFIG.get(path[0])
    # Nested lookup
    val = CONFIG
    for segment in path:
        if isinstance(val, dict):
            val = val.get(segment)
        else:
            return None
        if val is None:
            return None
    return val


def get_setting_from_snapshot(
    key: str,
    default: Any = None,
    username: str | None = None,  # noqa: ARG001
    settings_snapshot: dict[str, Any] | None = None,
) -> Any:
    """Get setting — tries snapshot → core.config → default.

    Preserves the exact signature used by 400+ call sites in research_engine.
    """
    # 1. Check explicit snapshot (highest priority — per-request overrides)
    if settings_snapshot and key in settings_snapshot:
        value = settings_snapshot[key]
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value

    # 2. Check child keys in snapshot
    if settings_snapshot:
        child = {}
        for k, v in settings_snapshot.items():
            if k.startswith(f"{key}."):
                child[k.removeprefix(f"{key}.")] = (
                    v["value"] if isinstance(v, dict) and "value" in v else v
                )
        if child:
            return child

    # 3. Check core.config via adapter
    core_val = _resolve_key(key)
    if core_val is not None:
        return core_val

    # 4. Fall back to default
    if default is not None:
        return default

    logger.warning(
        "[research_engine][config_adapter] key '{}' not found in snapshot or core.config",
        key,
    )
    return None


def get_bool_setting_from_snapshot(
    key: str,
    default: bool = False,
    username: str | None = None,
    settings_snapshot: dict[str, Any] | None = None,
) -> bool:
    """Boolean setting from snapshot/core.config."""
    value = get_setting_from_snapshot(
        key, default, username=username, settings_snapshot=settings_snapshot,
    )
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "on", "yes")
    return bool(value) if value is not None else default
