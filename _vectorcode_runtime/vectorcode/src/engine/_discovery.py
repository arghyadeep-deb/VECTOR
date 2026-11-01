"""Compatibility exports for the canonical engine discovery implementation."""

from vectorcode.src.vc_engine._discovery import (
    _make_engine,
    discover_engines,
    discover_models,
    get_engine,
)

__all__ = ["_make_engine", "discover_engines", "discover_models", "get_engine"]
