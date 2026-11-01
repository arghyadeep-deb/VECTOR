# -*- coding: utf-8 -*-
"""PersonModel - thin redirect to VectorCode persona module.

Canonical source: vectorcode/src/persona/person_model.py
Falls back to a minimal dataclass stub if vectorcode is unavailable.
"""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

try:
    from persona.person_model import PersonModel  # type: ignore[import]
except ModuleNotFoundError:
    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class PersonModel:  # type: ignore[no-redef]
        """Minimal fallback PersonModel when vectorcode persona is unavailable."""
        name: str = ""
        traits: dict[str, Any] = field(default_factory=dict)

__all__ = ["PersonModel"]
