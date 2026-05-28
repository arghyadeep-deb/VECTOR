"""
vectorcode/src/guidance/_engine.py
All VECTOR Guidance Engine components.

Imports from the canonical guidance.py monolith until inline decomposition
is done in a later cleanup pass. This gives the package the correct public
surface immediately without duplicating ~1600 lines of logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure vectorcode/src is on the path so the monolith can be imported directly
_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Import all engine classes from the monolith
from guidance import (  # type: ignore[import]  # noqa: F401
    ThreatDetector,
    CollusionDetector,
    MemoryQuorum,
    AuthorityGate,
    CoherenceScheduler,
    EconomicGovernor,
    ContinueGate,
    create_guidance_system,
)

__all__ = [
    "ThreatDetector",
    "CollusionDetector",
    "MemoryQuorum",
    "AuthorityGate",
    "CoherenceScheduler",
    "EconomicGovernor",
    "ContinueGate",
    "create_guidance_system",
]
