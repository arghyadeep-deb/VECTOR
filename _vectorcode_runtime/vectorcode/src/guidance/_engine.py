"""
vectorcode/src/guidance/_engine.py
All VECTOR Guidance Engine components.

Loads the canonical guidance.py monolith via importlib by file path to avoid
the package/module name collision: both vectorcode/src/guidance.py (monolith)
and vectorcode/src/guidance/ (this package) exist. A bare `from guidance import`
resolves to this package instead of the monolith, causing a circular import.
Using spec_from_file_location bypasses module-name resolution entirely.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path as _Path

import sys as _sys

_monolith_path = _Path(__file__).parent.parent / "guidance.py"
_spec = _ilu.spec_from_file_location("_guidance_monolith", _monolith_path)
_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_sys.modules["_guidance_monolith"] = _mod  # must register before exec so @dataclass resolves __module__
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

ThreatDetector = _mod.ThreatDetector
CollusionDetector = _mod.CollusionDetector
MemoryQuorum = _mod.MemoryQuorum
AuthorityGate = _mod.AuthorityGate
CoherenceScheduler = _mod.CoherenceScheduler
EconomicGovernor = _mod.EconomicGovernor
ContinueGate = _mod.ContinueGate
create_guidance_system = _mod.create_guidance_system

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
