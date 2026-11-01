"""Compatibility re-export for canonical security data types."""

from dataclasses import dataclass, field
from typing import List

from vectorcode.src.vc_security.types import *  # noqa: F401,F403


@dataclass
class InjectionScanResult:
    """Legacy result shape used by older injection-scanner callers."""

    detected: bool = False
    patterns: List[str] = field(default_factory=list)
    confidence: float = 0.0
