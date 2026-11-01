"""Shared helpers for direct xAI HTTP integrations."""

from __future__ import annotations


def vector_xai_user_agent() -> str:
    """Return a stable VectorCode-specific User-Agent for xAI HTTP calls."""
    try:
        from vector_cli import __version__
    except Exception:
        __version__ = "unknown"
    return f"VectorCode/{__version__}"
