# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Inference Engine primitive — LLM runtime management."""

from __future__ import annotations
from loguru import logger

import importlib

# Import engine modules to trigger @EngineRegistry.register() decorators
import vectorcode.src.vc_engine.ollama  # noqa: F401
import vectorcode.src.vc_engine.openai_compat_engines  # noqa: F401
from vectorcode.src.vc_engine._base import (
    EngineConnectionError,
    InferenceEngine,
    messages_to_dicts,
)
from vectorcode.src.vc_engine._discovery import discover_engines, discover_models, get_engine

# Optional engines — only register if their SDK deps are present
for _optional in ("cloud", "litellm", "gemma_cpp"):
    try:
        importlib.import_module(f".{_optional}", __name__)
    except ImportError:
        logger.opt(exception=True).debug(
            "[VECTOR][vc_engine] optional engine {} unavailable", _optional
        )

__all__ = [
    "EngineConnectionError",
    "InferenceEngine",
    "discover_engines",
    "discover_models",
    "get_engine",
    "messages_to_dicts",
]
