"""
vectorcode/src/claims/_types.py
Domain enums, dataclasses, and constants for the VECTOR claiming system.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Retained as a compatibility export for callers that display the historical
# default. New repositories must resolve their path at construction time via
# ``default_claims_db_path()`` so test/smoke runtime roots are honored.
DEFAULT_DB_PATH = Path.home() / ".vector" / "claims.db"


def default_claims_db_path() -> Path:
    """Return the claims store under VECTOR's active runtime data root."""
    from core.runtime_paths import get_data_root

    return get_data_root() / "claims.db"


class ClaimStatus(str, Enum):
    active = "active"
    pending_handoff = "pending_handoff"
    in_review = "in_review"
    completed = "completed"
    released = "released"
    expired = "expired"
    paused = "paused"
    blocked = "blocked"
    stealable = "stealable"


class IssuePriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class IssueComplexity(str, Enum):
    trivial = "trivial"
    simple = "simple"
    moderate = "moderate"
    complex = "complex"
    epic = "epic"


class AgentType(str, Enum):
    coder = "coder"
    debugger = "debugger"
    tester = "tester"
    reviewer = "reviewer"
    researcher = "researcher"
    planner = "planner"
    architect = "architect"
    coordinator = "coordinator"


class StealableReason(str, Enum):
    stale = "stale"
    blocked = "blocked"
    overloaded = "overloaded"
    manual = "manual"
    timeout = "timeout"


@dataclass
class Claimant:
    id: str
    type: str
    name: str
    capabilities: list[str] = field(default_factory=list)
    specializations: list[str] = field(default_factory=list)
    current_workload: int = 0
    max_concurrent_claims: int = 5

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "name": self.name,
            "capabilities": self.capabilities, "specializations": self.specializations,
            "current_workload": self.current_workload,
            "max_concurrent_claims": self.max_concurrent_claims,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Claimant":
        return cls(
            id=d["id"], type=d["type"], name=d["name"],
            capabilities=d.get("capabilities", []),
            specializations=d.get("specializations", []),
            current_workload=d.get("current_workload", 0),
            max_concurrent_claims=d.get("max_concurrent_claims", 5),
        )


@dataclass
class Issue:
    id: str
    title: str
    description: str = ""
    labels: list[str] = field(default_factory=list)
    priority: IssuePriority = IssuePriority.medium
    complexity: IssueComplexity = IssueComplexity.moderate
    required_capabilities: list[str] = field(default_factory=list)
    estimated_duration_minutes: int = 60
    repository_id: str = ""


@dataclass
class HandoffRecord:
    id: str
    from_claimant: Claimant
    to_claimant: Claimant
    reason: str
    status: str = "pending"
    requested_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    rejection_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "from_claimant": self.from_claimant.to_dict(),
            "to_claimant": self.to_claimant.to_dict(), "reason": self.reason,
            "status": self.status, "requested_at": self.requested_at,
            "resolved_at": self.resolved_at, "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffRecord":
        return cls(
            id=d["id"], from_claimant=Claimant.from_dict(d["from_claimant"]),
            to_claimant=Claimant.from_dict(d["to_claimant"]), reason=d["reason"],
            status=d.get("status", "pending"), requested_at=d.get("requested_at", time.time()),
            resolved_at=d.get("resolved_at"), rejection_reason=d.get("rejection_reason", ""),
        )


@dataclass
class StealableInfo:
    reason: StealableReason
    marked_at: float
    original_progress: int = 0
    allowed_stealer_types: Optional[list[AgentType]] = None

    def to_dict(self) -> dict:
        return {
            "reason": self.reason.value, "marked_at": self.marked_at,
            "original_progress": self.original_progress,
            "allowed_stealer_types": (
                [t.value for t in self.allowed_stealer_types]
                if self.allowed_stealer_types else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StealableInfo":
        ast_raw = d.get("allowed_stealer_types")
        return cls(
            reason=StealableReason(d["reason"]), marked_at=d["marked_at"],
            original_progress=d.get("original_progress", 0),
            allowed_stealer_types=[AgentType(t) for t in ast_raw] if ast_raw else None,
        )


@dataclass
class ContestInfo:
    contested_at: float
    contested_by: Claimant
    stolen_by: Claimant
    reason: str
    window_ends_at: float
    resolution: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "contested_at": self.contested_at, "contested_by": self.contested_by.to_dict(),
            "stolen_by": self.stolen_by.to_dict(), "reason": self.reason,
            "window_ends_at": self.window_ends_at, "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ContestInfo":
        return cls(
            contested_at=d["contested_at"], contested_by=Claimant.from_dict(d["contested_by"]),
            stolen_by=Claimant.from_dict(d["stolen_by"]), reason=d["reason"],
            window_ends_at=d["window_ends_at"], resolution=d.get("resolution"),
        )


@dataclass
class IssueClaim:
    id: str
    issue_id: str
    claimant: Claimant
    status: ClaimStatus
    claimed_at: float
    last_activity_at: float
    expires_at: Optional[float] = None
    notes: list[str] = field(default_factory=list)
    handoff_chain: list[HandoffRecord] = field(default_factory=list)
    progress: int = 0
    steal_info: Optional[StealableInfo] = None
    contest_info: Optional[ContestInfo] = None
    blocked_reason: str = ""
    blocked_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "issue_id": self.issue_id,
            "claimant": self.claimant.to_dict(), "status": self.status.value,
            "claimed_at": self.claimed_at, "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at, "notes": self.notes,
            "handoff_chain": [h.to_dict() for h in self.handoff_chain],
            "progress": self.progress,
            "steal_info": self.steal_info.to_dict() if self.steal_info else None,
            "contest_info": self.contest_info.to_dict() if self.contest_info else None,
            "blocked_reason": self.blocked_reason, "blocked_at": self.blocked_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IssueClaim":
        si_raw, ci_raw = d.get("steal_info"), d.get("contest_info")
        return cls(
            id=d["id"], issue_id=d["issue_id"],
            claimant=Claimant.from_dict(d["claimant"]),
            status=ClaimStatus(d["status"]),
            claimed_at=d["claimed_at"], last_activity_at=d["last_activity_at"],
            expires_at=d.get("expires_at"), notes=d.get("notes", []),
            handoff_chain=[HandoffRecord.from_dict(h) for h in d.get("handoff_chain", [])],
            progress=d.get("progress", 0),
            steal_info=StealableInfo.from_dict(si_raw) if si_raw else None,
            contest_info=ContestInfo.from_dict(ci_raw) if ci_raw else None,
            blocked_reason=d.get("blocked_reason", ""),
            blocked_at=d.get("blocked_at"),
        )


@dataclass
class WorkStealingConfig:
    stale_threshold_minutes: int = 30
    blocked_threshold_minutes: int = 60
    overload_threshold: int = 5
    grace_period_minutes: int = 10
    min_progress_to_protect: int = 75
    contest_window_minutes: int = 5
    allow_cross_type_steal: bool = True
    cross_type_steal_rules: list[tuple[AgentType, AgentType]] = field(
        default_factory=lambda: [
            (AgentType.coder, AgentType.debugger),
            (AgentType.tester, AgentType.reviewer),
        ]
    )


DEFAULT_CONFIG = WorkStealingConfig()

_VALID_TRANSITIONS: dict[ClaimStatus, set[ClaimStatus]] = {
    ClaimStatus.active: {
        ClaimStatus.pending_handoff, ClaimStatus.in_review, ClaimStatus.completed,
        ClaimStatus.released, ClaimStatus.paused, ClaimStatus.blocked, ClaimStatus.stealable,
    },
    ClaimStatus.pending_handoff: {ClaimStatus.active, ClaimStatus.released},
    ClaimStatus.in_review: {ClaimStatus.active, ClaimStatus.completed, ClaimStatus.released},
    ClaimStatus.completed: set(),
    ClaimStatus.released: set(),
    ClaimStatus.expired: set(),
    ClaimStatus.paused: {ClaimStatus.active, ClaimStatus.blocked, ClaimStatus.stealable, ClaimStatus.completed},
    ClaimStatus.blocked: {ClaimStatus.active, ClaimStatus.paused, ClaimStatus.stealable, ClaimStatus.completed},
    ClaimStatus.stealable: {ClaimStatus.active, ClaimStatus.completed},
}

_ACTIVE_STATUSES = {
    ClaimStatus.active, ClaimStatus.pending_handoff, ClaimStatus.in_review,
    ClaimStatus.paused, ClaimStatus.blocked, ClaimStatus.stealable,
}
