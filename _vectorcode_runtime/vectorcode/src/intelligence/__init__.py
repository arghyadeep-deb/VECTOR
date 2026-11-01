# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Intelligence primitive — the model definition and catalog."""

from __future__ import annotations

from vectorcode.src.intelligence.model_catalog import (
    BUILTIN_MODELS,
    merge_discovered_models,
    register_builtin_models,
)

__all__ = ["BUILTIN_MODELS", "merge_discovered_models", "register_builtin_models"]
