"""Security types shim."""
from vectorcode.src.vc_security import *
from typing import Any, List
class ThreatLevel:
    LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"
class SecurityContext:
    pass
from dataclasses import dataclass, field
from typing import List

@dataclass
class ScanFinding:
    rule: str = ""
    severity: str = "medium"
    description: str = ""
    line: int = 0
    column: int = 0

@dataclass
class ScanResult:
    findings: List[ScanFinding] = field(default_factory=list)
    scanned_bytes: int = 0
    is_safe: bool = True

@dataclass
class InjectionScanResult:
    detected: bool = False
    patterns: List[str] = field(default_factory=list)
    confidence: float = 0.0
