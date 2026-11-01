"""
vectorcode/src/guidance/__init__.py
VECTOR Guidance Engine — package entry point.

All public symbols re-exported so existing code continues to work:
    from vectorcode.src.guidance import create_guidance_system
    from vectorcode.src.guidance import ThreatDetector, AuthorityGate, ...
"""
from ._types import (
    ThreatCategory,
    ThreatSignal,
    AuthorityLevel,
    IrreversibilityClass,
    PrivilegeLevel,
    CoherenceScore,
    BudgetUsage,
    _clamp,
    _now_ms,
    _safe_pct,
)
from ._engine import (
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
    "ThreatCategory", "ThreatSignal", "AuthorityLevel", "IrreversibilityClass",
    "PrivilegeLevel", "CoherenceScore", "BudgetUsage",
    "ThreatDetector", "CollusionDetector", "MemoryQuorum", "AuthorityGate",
    "CoherenceScheduler", "EconomicGovernor", "ContinueGate",
    "create_guidance_system",
]
