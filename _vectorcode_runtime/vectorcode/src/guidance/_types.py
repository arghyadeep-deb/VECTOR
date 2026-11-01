"""
vectorcode/src/guidance/_types.py
Enums, dataclasses, and utility helpers for the VECTOR Guidance Engine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_pct(used: float, limit: float) -> float:
    if limit <= 0:
        return 0.0
    return (used / limit) * 100.0


class ThreatCategory(str, Enum):
    prompt_injection = "prompt_injection"
    memory_poisoning = "memory_poisoning"
    shard_manipulation = "shard_manipulation"
    malicious_delegation = "malicious_delegation"
    privilege_escalation = "privilege_escalation"
    data_exfiltration = "data_exfiltration"


@dataclass
class ThreatSignal:
    id: str
    category: ThreatCategory
    source_agent: str
    description: str
    evidence: List[str]
    severity: float
    timestamp: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def severity_label(self) -> str:
        if self.severity >= 0.9:
            return "critical"
        if self.severity >= 0.7:
            return "high"
        if self.severity >= 0.5:
            return "medium"
        return "low"


class AuthorityLevel(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class IrreversibilityClass(str, Enum):
    reversible = "reversible"
    costly_reversible = "costly_reversible"
    irreversible = "irreversible"


class PrivilegeLevel(str, Enum):
    full = "full"
    restricted = "restricted"
    suspended = "suspended"


@dataclass
class CoherenceScore:
    agent_id: str
    score: float  # 0.0 – 1.0
    timestamp: int = field(default_factory=_now_ms)


@dataclass
class BudgetUsage:
    tokens_used: int = 0
    tool_calls_used: int = 0
    cost_usd: float = 0.0

    def pct_tokens(self, limit: int) -> float:
        return _safe_pct(self.tokens_used, limit)

    def pct_tool_calls(self, limit: int) -> float:
        return _safe_pct(self.tool_calls_used, limit)

    def pct_cost(self, limit: float) -> float:
        return _safe_pct(self.cost_usd, limit)
