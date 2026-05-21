# -*- coding: utf-8 -*-
"""PersonModel - thin redirect to VectorCode persona module.

Canonical source: vectorcode/src/persona/person_model.py
Falls back to a minimal dataclass stub if vectorcode is unavailable.
"""
import sys
from pathlib import Path

_VC_SRC = Path(__file__).resolve().parent.parent.parent / "vectorcode" / "src"
if _VC_SRC.exists() and str(_VC_SRC) not in sys.path:
    sys.path.insert(0, str(_VC_SRC))

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
