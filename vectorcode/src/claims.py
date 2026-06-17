"""
VECTOR Task Claiming System
===========================
Work claiming, work stealing, and load balancing for VECTOR agents.

Provides:
  - ClaimRepository    — SQLite-backed persistence for all claims
  - ClaimService       — Core claiming lifecycle (claim, release, handoff, progress)
  - WorkStealingService — Redistribute stale/blocked/overloaded work
  - LoadBalancer       — Swarm-level utilisation tracking and rebalance
  - MCP tool functions — Thin async wrappers for every operation

All classes follow VECTOR naming conventions. No external dependencies
beyond stdlib + loguru. DB is stored at ~/.vector/claims.db by default.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = Path.home() / ".vector" / "claims.db"

# ---------------------------------------------------------------------------
# Domain enums
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Claimant:
    """A human or agent that can claim tasks in the VECTOR system."""

    id: str
    type: str  # "human" or "agent"
    name: str
    capabilities: list[str] = field(default_factory=list)
    specializations: list[str] = field(default_factory=list)
    current_workload: int = 0
    max_concurrent_claims: int = 5

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "capabilities": self.capabilities,
            "specializations": self.specializations,
            "current_workload": self.current_workload,
            "max_concurrent_claims": self.max_concurrent_claims,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Claimant":
        return cls(
            id=d["id"],
            type=d["type"],
            name=d["name"],
            capabilities=d.get("capabilities", []),
            specializations=d.get("specializations", []),
            current_workload=d.get("current_workload", 0),
            max_concurrent_claims=d.get("max_concurrent_claims", 5),
        )


@dataclass
class Issue:
    """A unit of work that can be claimed by VECTOR agents or humans."""

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
    """Tracks a single handoff request between claimants."""

    id: str
    from_claimant: Claimant
    to_claimant: Claimant
    reason: str
    status: str = "pending"  # pending | accepted | rejected
    requested_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    rejection_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_claimant": self.from_claimant.to_dict(),
            "to_claimant": self.to_claimant.to_dict(),
            "reason": self.reason,
            "status": self.status,
            "requested_at": self.requested_at,
            "resolved_at": self.resolved_at,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffRecord":
        return cls(
            id=d["id"],
            from_claimant=Claimant.from_dict(d["from_claimant"]),
            to_claimant=Claimant.from_dict(d["to_claimant"]),
            reason=d["reason"],
            status=d.get("status", "pending"),
            requested_at=d.get("requested_at", time.time()),
            resolved_at=d.get("resolved_at"),
            rejection_reason=d.get("rejection_reason", ""),
        )


@dataclass
class StealableInfo:
    """Metadata describing why a claim is available for stealing."""

    reason: StealableReason
    marked_at: float
    original_progress: int = 0
    allowed_stealer_types: Optional[list[AgentType]] = None

    def to_dict(self) -> dict:
        return {
            "reason": self.reason.value,
            "marked_at": self.marked_at,
            "original_progress": self.original_progress,
            "allowed_stealer_types": (
                [t.value for t in self.allowed_stealer_types]
                if self.allowed_stealer_types
                else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StealableInfo":
        ast_raw = d.get("allowed_stealer_types")
        allowed = (
            [AgentType(t) for t in ast_raw] if ast_raw is not None else None
        )
        return cls(
            reason=StealableReason(d["reason"]),
            marked_at=d["marked_at"],
            original_progress=d.get("original_progress", 0),
            allowed_stealer_types=allowed,
        )


@dataclass
class ContestInfo:
    """Information about an ongoing steal contest."""

    contested_at: float
    contested_by: Claimant       # original owner who wants it back
    stolen_by: Claimant          # agent that performed the steal
    reason: str
    window_ends_at: float
    resolution: Optional[dict] = None  # {"winner_id": ..., "reason": ..., "resolved_at": ...}

    def to_dict(self) -> dict:
        return {
            "contested_at": self.contested_at,
            "contested_by": self.contested_by.to_dict(),
            "stolen_by": self.stolen_by.to_dict(),
            "reason": self.reason,
            "window_ends_at": self.window_ends_at,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ContestInfo":
        return cls(
            contested_at=d["contested_at"],
            contested_by=Claimant.from_dict(d["contested_by"]),
            stolen_by=Claimant.from_dict(d["stolen_by"]),
            reason=d["reason"],
            window_ends_at=d["window_ends_at"],
            resolution=d.get("resolution"),
        )


@dataclass
class IssueClaim:
    """An active or historical claim on a task."""

    id: str
    issue_id: str
    claimant: Claimant
    status: ClaimStatus
    claimed_at: float
    last_activity_at: float
    expires_at: Optional[float] = None
    notes: list[str] = field(default_factory=list)
    handoff_chain: list[HandoffRecord] = field(default_factory=list)
    progress: int = 0                          # 0-100
    steal_info: Optional[StealableInfo] = None
    contest_info: Optional[ContestInfo] = None
    blocked_reason: str = ""
    blocked_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "issue_id": self.issue_id,
            "claimant": self.claimant.to_dict(),
            "status": self.status.value,
            "claimed_at": self.claimed_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "notes": self.notes,
            "handoff_chain": [h.to_dict() for h in self.handoff_chain],
            "progress": self.progress,
            "steal_info": self.steal_info.to_dict() if self.steal_info else None,
            "contest_info": self.contest_info.to_dict() if self.contest_info else None,
            "blocked_reason": self.blocked_reason,
            "blocked_at": self.blocked_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IssueClaim":
        si_raw = d.get("steal_info")
        ci_raw = d.get("contest_info")
        return cls(
            id=d["id"],
            issue_id=d["issue_id"],
            claimant=Claimant.from_dict(d["claimant"]),
            status=ClaimStatus(d["status"]),
            claimed_at=d["claimed_at"],
            last_activity_at=d["last_activity_at"],
            expires_at=d.get("expires_at"),
            notes=d.get("notes", []),
            handoff_chain=[HandoffRecord.from_dict(h) for h in d.get("handoff_chain", [])],
            progress=d.get("progress", 0),
            steal_info=StealableInfo.from_dict(si_raw) if si_raw else None,
            contest_info=ContestInfo.from_dict(ci_raw) if ci_raw else None,
            blocked_reason=d.get("blocked_reason", ""),
            blocked_at=d.get("blocked_at"),
        )


@dataclass
class WorkStealingConfig:
    """Configuration for the VECTOR work stealing system."""

    stale_threshold_minutes: int = 30
    blocked_threshold_minutes: int = 60
    overload_threshold: int = 5
    grace_period_minutes: int = 10
    min_progress_to_protect: int = 75
    contest_window_minutes: int = 5
    allow_cross_type_steal: bool = True
    # pairs that can steal from each other
    cross_type_steal_rules: list[tuple[AgentType, AgentType]] = field(
        default_factory=lambda: [
            (AgentType.coder, AgentType.debugger),
            (AgentType.tester, AgentType.reviewer),
        ]
    )


DEFAULT_CONFIG = WorkStealingConfig()


# ---------------------------------------------------------------------------
# Valid claim status transitions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ClaimRepository — SQLite-backed
# ---------------------------------------------------------------------------


class ClaimRepository:
    """
    SQLite-backed persistence for VECTOR task claims.

    Schema is a flat `claims` table; JSON columns handle nested structures
    (claimant, handoff chain, steal info, contest info, notes).
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()
        logger.info(f"[VECTOR][claims] ClaimRepository ready at {self.db_path}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS claims (
                        id              TEXT PRIMARY KEY,
                        issue_id        TEXT NOT NULL,
                        claimant_id     TEXT NOT NULL,
                        claimant_name   TEXT NOT NULL,
                        claimant_type   TEXT NOT NULL,
                        status          TEXT NOT NULL,
                        claimed_at      REAL NOT NULL,
                        last_activity_at REAL NOT NULL,
                        progress        INTEGER NOT NULL DEFAULT 0,
                        blob            TEXT NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_issue_id ON claims(issue_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_claimant_id ON claims(claimant_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id          TEXT PRIMARY KEY,
                        claim_id    TEXT NOT NULL,
                        issue_id    TEXT NOT NULL,
                        event_type  TEXT NOT NULL,
                        payload     TEXT NOT NULL,
                        occurred_at REAL NOT NULL
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def _row_to_claim(self, row: sqlite3.Row) -> IssueClaim:
        blob = json.loads(row["blob"])
        return IssueClaim.from_dict(blob)

    def _claim_to_row(self, claim: IssueClaim) -> dict:
        return {
            "id": claim.id,
            "issue_id": claim.issue_id,
            "claimant_id": claim.claimant.id,
            "claimant_name": claim.claimant.name,
            "claimant_type": claim.claimant.type,
            "status": claim.status.value,
            "claimed_at": claim.claimed_at,
            "last_activity_at": claim.last_activity_at,
            "progress": claim.progress,
            "blob": json.dumps(claim.to_dict()),
        }

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save(self, claim: IssueClaim) -> None:
        row = self._claim_to_row(claim)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO claims
                    (id, issue_id, claimant_id, claimant_name, claimant_type,
                     status, claimed_at, last_activity_at, progress, blob)
                    VALUES
                    (:id, :issue_id, :claimant_id, :claimant_name, :claimant_type,
                     :status, :claimed_at, :last_activity_at, :progress, :blob)
                    """,
                    row,
                )
                conn.commit()
            finally:
                conn.close()
        logger.debug(
            f"[VECTOR][claims] saved claim {claim.id} issue={claim.issue_id} status={claim.status}"
        )

    def append_event(self, claim_id: str, issue_id: str, event_type: str, payload: dict) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO events (id, claim_id, issue_id, event_type, payload, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"evt-{uuid.uuid4().hex}",
                        claim_id,
                        issue_id,
                        event_type,
                        json.dumps(payload),
                        time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def find_by_id(self, claim_id: str) -> Optional[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM claims WHERE id = ?", (claim_id,)
                ).fetchone()
            finally:
                conn.close()
        return self._row_to_claim(row) if row else None

    def find_by_issue_id(self, issue_id: str) -> Optional[IssueClaim]:
        """Return the most recent active claim for an issue, or None."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM claims
                    WHERE issue_id = ? AND status NOT IN ('completed','released','expired')
                    ORDER BY claimed_at DESC LIMIT 1
                    """,
                    (issue_id,),
                ).fetchone()
            finally:
                conn.close()
        return self._row_to_claim(row) if row else None

    def find_by_agent_id(self, agent_id: str) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM claims WHERE claimant_id = ?", (agent_id,)
                ).fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def find_stealable(self, agent_type: Optional[AgentType] = None) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM claims WHERE status = 'stealable'"
                ).fetchall()
            finally:
                conn.close()
        claims = [self._row_to_claim(r) for r in rows]
        if agent_type is None:
            return claims
        result = []
        for c in claims:
            if c.steal_info is None:
                result.append(c)
            elif c.steal_info.allowed_stealer_types is None:
                result.append(c)
            elif agent_type in c.steal_info.allowed_stealer_types:
                result.append(c)
        return result

    def find_all_active(self) -> list[IssueClaim]:
        statuses = tuple(s.value for s in _ACTIVE_STATUSES)
        placeholder = ",".join("?" * len(statuses))
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    f"SELECT * FROM claims WHERE status IN ({placeholder})", statuses
                ).fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def find_all(self) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM claims").fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def find_stale(self, since_timestamp: float) -> list[IssueClaim]:
        """Claims with last_activity_at older than since_timestamp."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM claims
                    WHERE last_activity_at < ?
                      AND status NOT IN ('completed','released','expired','stealable')
                    """,
                    (since_timestamp,),
                ).fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def count_by_agent(self, agent_id: str) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) as cnt FROM claims
                    WHERE claimant_id = ?
                      AND status NOT IN ('completed','released','expired')
                    """,
                    (agent_id,),
                ).fetchone()
            finally:
                conn.close()
        return row["cnt"] if row else 0

    def get_events(self, claim_id: str) -> list[dict]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM events WHERE claim_id = ? ORDER BY occurred_at",
                    (claim_id,),
                ).fetchall()
            finally:
                conn.close()
        return [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "payload": json.loads(r["payload"]),
                "occurred_at": r["occurred_at"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# ClaimService
# ---------------------------------------------------------------------------


class ClaimService:
    """
    Core VECTOR task claiming lifecycle.

    Handles: claim, release, handoff (request/accept/reject),
             progress update, status update, auto-assign, expiry.
    """

    def __init__(self, repo: Optional[ClaimRepository] = None) -> None:
        self.repo = repo or ClaimRepository()

    # ------------------------------------------------------------------
    # Claim
    # ------------------------------------------------------------------

    def claim(
        self,
        issue_id: str,
        claimant: Claimant,
        issue_title: str = "",
        labels: Optional[list[str]] = None,
        priority: IssuePriority = IssuePriority.medium,
        complexity: IssueComplexity = IssueComplexity.moderate,
        required_capabilities: Optional[list[str]] = None,
    ) -> Optional[IssueClaim]:
        """
        Claim a task. Returns the new IssueClaim on success, or None if
        already claimed / capacity exceeded / capability mismatch.
        """
        existing = self.repo.find_by_issue_id(issue_id)
        if existing and existing.status == ClaimStatus.active:
            logger.warning(
                f"[VECTOR][claims] issue {issue_id} already claimed by {existing.claimant.name}"
            )
            return None

        active_count = self.repo.count_by_agent(claimant.id)
        if active_count >= claimant.max_concurrent_claims:
            logger.warning(
                f"[VECTOR][claims] {claimant.name} at capacity ({active_count}/{claimant.max_concurrent_claims})"
            )
            return None

        required = required_capabilities or []
        if required:
            missing = [c for c in required if c not in claimant.capabilities]
            if missing:
                logger.warning(
                    f"[VECTOR][claims] {claimant.name} missing capabilities: {missing}"
                )
                return None

        now = time.time()
        claim = IssueClaim(
            id=f"claim-{uuid.uuid4().hex}",
            issue_id=issue_id,
            claimant=claimant,
            status=ClaimStatus.active,
            claimed_at=now,
            last_activity_at=now,
        )
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "ClaimCreated", {
            "claimant_id": claimant.id,
            "issue_title": issue_title,
            "priority": priority.value if hasattr(priority, "value") else str(priority),
        })
        logger.info(f"[VECTOR][claims] {claimant.name} claimed issue {issue_id}")
        return claim

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------

    def release(self, issue_id: str, claimant_id: str) -> bool:
        """Release a claim. Returns True on success, False if not found / unauthorized."""
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            logger.warning(f"[VECTOR][claims] release: no active claim for issue {issue_id}")
            return False
        if claim.claimant.id != claimant_id:
            logger.warning(
                f"[VECTOR][claims] release: {claimant_id} does not own claim on {issue_id}"
            )
            return False
        pending = [h for h in claim.handoff_chain if h.status == "pending"]
        if pending:
            logger.warning(
                f"[VECTOR][claims] release blocked: pending handoff on {issue_id}"
            )
            return False
        claim.status = ClaimStatus.released
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "ClaimReleased", {"claimant_id": claimant_id})
        logger.info(f"[VECTOR][claims] {claimant_id} released issue {issue_id}")
        return True

    # ------------------------------------------------------------------
    # Handoff
    # ------------------------------------------------------------------

    def request_handoff(
        self,
        issue_id: str,
        from_id: str,
        to_claimant: Claimant,
        reason: str,
    ) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            logger.warning(f"[VECTOR][claims] handoff: no active claim for {issue_id}")
            return False
        if claim.claimant.id != from_id:
            logger.warning(f"[VECTOR][claims] handoff: {from_id} not owner of {issue_id}")
            return False
        if any(h.status == "pending" for h in claim.handoff_chain):
            logger.warning(f"[VECTOR][claims] handoff: already pending on {issue_id}")
            return False

        record = HandoffRecord(
            id=f"handoff-{uuid.uuid4().hex}",
            from_claimant=claim.claimant,
            to_claimant=to_claimant,
            reason=reason,
            requested_at=time.time(),
        )
        claim.handoff_chain.append(record)
        claim.status = ClaimStatus.pending_handoff
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "HandoffRequested", {
            "from_id": from_id,
            "to_id": to_claimant.id,
            "reason": reason,
        })
        logger.info(
            f"[VECTOR][claims] handoff requested: {from_id} → {to_claimant.name} for {issue_id}"
        )
        return True

    def accept_handoff(self, issue_id: str, accepting_claimant_id: str) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            logger.warning(f"[VECTOR][claims] accept_handoff: no claim for {issue_id}")
            return False
        pending = [
            h for h in claim.handoff_chain
            if h.status == "pending" and h.to_claimant.id == accepting_claimant_id
        ]
        if not pending:
            logger.warning(
                f"[VECTOR][claims] accept_handoff: no pending handoff to {accepting_claimant_id} on {issue_id}"
            )
            return False
        handoff = pending[0]
        handoff.status = "accepted"
        handoff.resolved_at = time.time()
        claim.claimant = handoff.to_claimant
        claim.status = ClaimStatus.active
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "HandoffAccepted", {
            "new_claimant_id": accepting_claimant_id,
        })
        logger.info(
            f"[VECTOR][claims] handoff accepted: {accepting_claimant_id} now owns {issue_id}"
        )
        return True

    def reject_handoff(self, issue_id: str, rejecting_id: str, reason: str) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            return False
        pending = [
            h for h in claim.handoff_chain
            if h.status == "pending" and h.to_claimant.id == rejecting_id
        ]
        if not pending:
            return False
        handoff = pending[0]
        handoff.status = "rejected"
        handoff.resolved_at = time.time()
        handoff.rejection_reason = reason
        claim.status = ClaimStatus.active
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "HandoffRejected", {
            "rejecting_id": rejecting_id,
            "reason": reason,
        })
        logger.info(
            f"[VECTOR][claims] handoff rejected by {rejecting_id} on {issue_id}: {reason}"
        )
        return True

    # ------------------------------------------------------------------
    # Progress & status
    # ------------------------------------------------------------------

    def update_progress(self, issue_id: str, claimant_id: str, progress: int) -> bool:
        """Update 0-100 progress on a claim. Returns True on success."""
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            return False
        if claim.claimant.id != claimant_id:
            return False
        claim.progress = max(0, min(100, progress))
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "ProgressUpdated", {"progress": claim.progress})
        logger.debug(f"[VECTOR][claims] {issue_id} progress → {claim.progress}%")
        return True

    def update_status(
        self,
        issue_id: str,
        new_status: ClaimStatus,
        note: Optional[str] = None,
    ) -> bool:
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            logger.warning(f"[VECTOR][claims] update_status: no claim for {issue_id}")
            return False
        allowed = _VALID_TRANSITIONS.get(claim.status, set())
        if new_status not in allowed:
            logger.warning(
                f"[VECTOR][claims] invalid transition {claim.status} → {new_status} for {issue_id}"
            )
            return False
        old = claim.status
        claim.status = new_status
        claim.last_activity_at = time.time()
        if note:
            claim.notes.append(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {note}")
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "StatusChanged", {
            "from": old.value,
            "to": new_status.value,
            "note": note,
        })
        logger.info(f"[VECTOR][claims] {issue_id} status {old} → {new_status}")
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_claimed_by(self, agent_id: str) -> list[IssueClaim]:
        return [
            c for c in self.repo.find_by_agent_id(agent_id)
            if c.status in _ACTIVE_STATUSES
        ]

    # ------------------------------------------------------------------
    # Auto-management
    # ------------------------------------------------------------------

    def expire_stale(self, max_age_minutes: int = 120) -> list[IssueClaim]:
        """Expire active claims with no activity for max_age_minutes. Returns expired list."""
        cutoff = time.time() - max_age_minutes * 60
        stale = self.repo.find_stale(cutoff)
        expired: list[IssueClaim] = []
        for claim in stale:
            if claim.status != ClaimStatus.active:
                continue
            claim.status = ClaimStatus.expired
            self.repo.save(claim)
            self.repo.append_event(claim.id, claim.issue_id, "ClaimExpired", {
                "last_activity_at": claim.last_activity_at,
                "max_age_minutes": max_age_minutes,
            })
            expired.append(claim)
            logger.info(f"[VECTOR][claims] expired claim on {claim.issue_id} (inactive > {max_age_minutes}min)")
        return expired

    def auto_assign(
        self,
        issue_id: str,
        available_agents: list[Claimant],
        required_capabilities: Optional[list[str]] = None,
        labels: Optional[list[str]] = None,
    ) -> Optional[Claimant]:
        """
        Score and return the best agent for a task.
        Scoring: capability match × 10 + full match bonus 20 +
                 specialization match × 5 − utilisation_penalty (0-15).
        Returns None if no agent qualifies.
        """
        required = required_capabilities or []
        if not available_agents:
            return None

        scored: list[tuple[float, Claimant]] = []
        for agent in available_agents:
            score = 0.0
            if required:
                matched = [c for c in required if c in agent.capabilities]
                score += len(matched) * 10
                if len(matched) == len(required):
                    score += 20
            else:
                score += 10

            if labels and agent.specializations:
                spec_match = [lb for lb in labels if lb in agent.specializations]
                score += len(spec_match) * 5

            utilisation = agent.current_workload / max(agent.max_concurrent_claims, 1)
            score -= utilisation * 15

            if agent.type == "agent":
                score += 3

            scored.append((score, agent))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            return None

        best_score, best_agent = scored[0]

        # Only assign if the agent has all required capabilities
        if required:
            missing = [c for c in required if c not in best_agent.capabilities]
            if missing:
                return None

        return best_agent


# ---------------------------------------------------------------------------
# WorkStealingService
# ---------------------------------------------------------------------------


class WorkStealingService:
    """
    VECTOR work stealing — redistributes work from stale, blocked, or
    overloaded agents to idle agents, maximising swarm throughput.
    """

    def __init__(
        self,
        repo: Optional[ClaimRepository] = None,
        config: Optional[WorkStealingConfig] = None,
    ) -> None:
        self.repo = repo or ClaimRepository()
        self.config = config or WorkStealingConfig()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_agent_type(self, claimant: Claimant) -> AgentType:
        keywords = [t.value for t in AgentType]
        for kw in keywords:
            if kw in claimant.specializations:
                return AgentType(kw)
            if kw in claimant.capabilities:
                return AgentType(kw)
            if kw in claimant.name.lower():
                return AgentType(kw)
        return AgentType.coder

    def _in_grace_period(self, claim: IssueClaim) -> bool:
        grace_ms = self.config.grace_period_minutes * 60
        return (time.time() - claim.claimed_at) < grace_ms

    def _protected_by_progress(self, claim: IssueClaim) -> bool:
        return claim.progress >= self.config.min_progress_to_protect

    def _can_steal_cross_type(
        self,
        stealer_type: AgentType,
        owner_type: AgentType,
        steal_info: StealableInfo,
    ) -> bool:
        if stealer_type == owner_type:
            return True
        if not self.config.allow_cross_type_steal:
            return False
        if steal_info.allowed_stealer_types is not None:
            return stealer_type in steal_info.allowed_stealer_types
        for t1, t2 in self.config.cross_type_steal_rules:
            if (stealer_type == t1 and owner_type == t2) or (stealer_type == t2 and owner_type == t1):
                return True
        return False

    def _allowed_stealer_types(self, claimant: Claimant) -> Optional[list[AgentType]]:
        if not self.config.allow_cross_type_steal:
            return None
        owner_type = self._get_agent_type(claimant)
        allowed = {owner_type}
        for t1, t2 in self.config.cross_type_steal_rules:
            if owner_type == t1:
                allowed.add(t2)
            if owner_type == t2:
                allowed.add(t1)
        return list(allowed)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def mark_stealable(
        self,
        issue_id: str,
        reason: StealableReason,
        original_progress: int = 0,
    ) -> bool:
        """
        Mark a claim as stealable. Respects grace period and progress protection.
        Returns True on success.
        """
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            logger.warning(f"[VECTOR][claims] mark_stealable: no claim for {issue_id}")
            return False
        if claim.steal_info is not None:
            logger.debug(f"[VECTOR][claims] {issue_id} already stealable")
            return True
        if self._in_grace_period(claim):
            logger.warning(f"[VECTOR][claims] {issue_id} still in grace period")
            return False
        if self._protected_by_progress(claim):
            logger.warning(
                f"[VECTOR][claims] {issue_id} protected by progress ({claim.progress}%)"
            )
            return False

        claim.steal_info = StealableInfo(
            reason=reason,
            marked_at=time.time(),
            original_progress=original_progress or claim.progress,
            allowed_stealer_types=self._allowed_stealer_types(claim.claimant),
        )
        claim.status = ClaimStatus.stealable
        claim.last_activity_at = time.time()
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "IssueMarkedStealable", {
            "reason": reason.value,
            "original_progress": claim.steal_info.original_progress,
        })
        logger.info(
            f"[VECTOR][claims] issue {issue_id} marked stealable ({reason.value})"
        )
        return True

    def steal(self, issue_id: str, stealer: Claimant) -> Optional[IssueClaim]:
        """
        Steal a stealable claim.  Checks grace period, progress protection,
        cross-type rules, and stealer capacity.
        Returns the updated IssueClaim on success, or None on failure.
        """
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim:
            logger.warning(f"[VECTOR][claims] steal: no claim for {issue_id}")
            return None
        if claim.steal_info is None or claim.status != ClaimStatus.stealable:
            logger.warning(f"[VECTOR][claims] steal: {issue_id} is not stealable")
            return None
        if claim.contest_info and claim.contest_info.resolution is None:
            logger.warning(f"[VECTOR][claims] steal: {issue_id} has unresolved contest")
            return None
        if self._in_grace_period(claim):
            logger.warning(f"[VECTOR][claims] steal: {issue_id} in grace period")
            return None
        if self._protected_by_progress(claim):
            logger.warning(
                f"[VECTOR][claims] steal: {issue_id} protected by progress ({claim.progress}%)"
            )
            return None

        stealer_type = self._get_agent_type(stealer)
        owner_type = self._get_agent_type(claim.claimant)
        if not self._can_steal_cross_type(stealer_type, owner_type, claim.steal_info):
            logger.warning(
                f"[VECTOR][claims] steal: cross-type not allowed ({stealer_type} → {owner_type})"
            )
            return None

        stealer_count = self.repo.count_by_agent(stealer.id)
        if stealer_count >= self.config.overload_threshold:
            logger.warning(
                f"[VECTOR][claims] steal: {stealer.name} overloaded ({stealer_count} claims)"
            )
            return None

        now = time.time()
        prev_claimant = claim.claimant
        prev_steal_info = claim.steal_info
        contest_window_ends = now + self.config.contest_window_minutes * 60

        claim.contest_info = ContestInfo(
            contested_at=now,
            contested_by=prev_claimant,
            stolen_by=stealer,
            reason="",
            window_ends_at=contest_window_ends,
        )
        claim.claimant = stealer
        claim.steal_info = None
        claim.status = ClaimStatus.active
        claim.last_activity_at = now
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "IssueStolen", {
            "previous_claimant_id": prev_claimant.id,
            "new_claimant_id": stealer.id,
            "steal_reason": prev_steal_info.reason.value,
            "contest_window_ends_at": contest_window_ends,
        })
        logger.info(
            f"[VECTOR][claims] {stealer.name} stole {issue_id} from {prev_claimant.name}"
        )
        return claim

    def get_stealable(self, agent_type: Optional[AgentType] = None) -> list[IssueClaim]:
        """Return stealable claims visible to the given agent type (all if None)."""
        candidates = self.repo.find_stealable(agent_type)
        result = []
        for c in candidates:
            if self._in_grace_period(c):
                continue
            if self._protected_by_progress(c):
                continue
            result.append(c)
        return result

    def detect_stale_work(
        self, config: Optional[WorkStealingConfig] = None
    ) -> list[IssueClaim]:
        """
        Return claims that should be marked stealable based on thresholds.
        Does NOT mutate any claim — call auto_mark_stealable to act on them.
        """
        cfg = config or self.config
        all_claims = self.repo.find_all_active()
        now = time.time()
        stale_threshold = cfg.stale_threshold_minutes * 60
        blocked_threshold = cfg.blocked_threshold_minutes * 60
        result: list[IssueClaim] = []

        agent_counts: dict[str, list[IssueClaim]] = {}
        for c in all_claims:
            agent_counts.setdefault(c.claimant.id, []).append(c)

        for claim in all_claims:
            if claim.steal_info is not None:
                continue
            cfg_local = cfg  # for grace/progress checks with passed-in config
            grace_ms = cfg_local.grace_period_minutes * 60
            if (now - claim.claimed_at) < grace_ms:
                continue
            if claim.progress >= cfg_local.min_progress_to_protect:
                continue

            # Stale check
            if (now - claim.last_activity_at) > stale_threshold:
                result.append(claim)
                continue

            # Blocked check
            if (
                claim.status == ClaimStatus.blocked
                and claim.blocked_at is not None
                and (now - claim.blocked_at) > blocked_threshold
            ):
                result.append(claim)
                continue

        # Overloaded agents
        for agent_id, claims in agent_counts.items():
            if len(claims) > cfg.overload_threshold:
                candidates = [
                    c for c in claims
                    if c.steal_info is None and c not in result
                ]
                candidates.sort(key=lambda c: c.progress)
                if candidates:
                    result.append(candidates[0])

        return result

    def auto_mark_stealable(
        self, config: Optional[WorkStealingConfig] = None
    ) -> int:
        """Mark all detected stale work as stealable. Returns count marked."""
        cfg = config or self.config
        stale = self.detect_stale_work(cfg)
        now = time.time()
        marked = 0
        for claim in stale:
            # Determine reason
            stale_threshold = cfg.stale_threshold_minutes * 60
            blocked_threshold = cfg.blocked_threshold_minutes * 60
            if (
                claim.status == ClaimStatus.blocked
                and claim.blocked_at is not None
                and (now - claim.blocked_at) > blocked_threshold
            ):
                reason = StealableReason.blocked
            elif (now - claim.last_activity_at) > stale_threshold:
                reason = StealableReason.stale
            else:
                reason = StealableReason.overloaded

            ok = self.mark_stealable(claim.issue_id, reason, claim.progress)
            if ok:
                marked += 1
        logger.info(f"[VECTOR][claims] auto-marked {marked} claims as stealable")
        return marked

    def resolve_contest(
        self, issue_id: str, winner_id: str, reason: str
    ) -> bool:
        """
        Queen resolves a contested steal. winner_id must be either the original
        claimant (reversal) or the stealer (uphold).
        """
        claim = self.repo.find_by_issue_id(issue_id)
        if not claim or claim.contest_info is None:
            return False
        if claim.contest_info.resolution is not None:
            logger.warning(f"[VECTOR][claims] contest already resolved on {issue_id}")
            return False

        now = time.time()
        claim.contest_info.resolution = {
            "winner_id": winner_id,
            "reason": reason,
            "resolved_at": now,
        }
        # If original claimant wins, revert
        if winner_id == claim.contest_info.contested_by.id:
            claim.claimant = claim.contest_info.contested_by

        claim.last_activity_at = now
        self.repo.save(claim)
        self.repo.append_event(claim.id, issue_id, "StealContestResolved", {
            "winner_id": winner_id,
            "reason": reason,
        })
        logger.info(
            f"[VECTOR][claims] contest resolved on {issue_id}: winner={winner_id}"
        )
        return True


# ---------------------------------------------------------------------------
# LoadBalancer
# ---------------------------------------------------------------------------


class LoadBalancer:
    """
    VECTOR swarm load balancer.

    Tracks utilisation per agent, detects over/under-loaded agents, and
    produces rebalance move recommendations.  Uses a weighted utilisation
    model (critical=2×, high=1.5×, medium=1×, low=0.5×).
    """

    _PRIORITY_WEIGHTS: dict[str, float] = {
        "critical": 2.0,
        "high": 1.5,
        "medium": 1.0,
        "low": 0.5,
    }
    _DEFAULT_MAX_CLAIMS = 5

    def __init__(self, repo: Optional[ClaimRepository] = None) -> None:
        self.repo = repo or ClaimRepository()
        self._background_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Load info
    # ------------------------------------------------------------------

    def get_agent_load(self, agent_ids: list[str]) -> dict[str, float]:
        """
        Return a dict of agent_id → load_percentage (0-100).
        """
        result: dict[str, float] = {}
        for agent_id in agent_ids:
            claims = self.repo.find_by_agent_id(agent_id)
            active = [c for c in claims if c.status in _ACTIVE_STATUSES]
            weighted = sum(
                self._PRIORITY_WEIGHTS.get("medium", 1.0) for _ in active
            )
            pct = min(100.0, (weighted / self._DEFAULT_MAX_CLAIMS) * 100)
            result[agent_id] = round(pct, 1)
        return result

    def get_agent_claim_count(self, agent_id: str) -> int:
        return self.repo.count_by_agent(agent_id)

    # ------------------------------------------------------------------
    # Rebalance
    # ------------------------------------------------------------------

    def rebalance(
        self,
        agents: list[Claimant],
        config: Optional[WorkStealingConfig] = None,
        overload_threshold_pct: float = 90.0,
        underload_threshold_pct: float = 30.0,
        max_moves: int = 10,
    ) -> list[tuple[str, str, str]]:
        """
        Produce a list of (claim_id, from_agent_id, to_agent_id) moves.
        Does NOT execute the moves — caller uses ClaimService.request_handoff.
        """
        cfg = config or WorkStealingConfig()
        if not agents:
            return []

        load_map = self.get_agent_load([a.id for a in agents])
        overloaded = self.find_overloaded(agents, overload_threshold_pct)
        underloaded = self.find_underloaded(agents, underload_threshold_pct)

        if not overloaded or not underloaded:
            return []

        agent_by_id = {a.id: a for a in agents}
        moves: list[tuple[str, str, str]] = []

        for over_id in overloaded:
            if len(moves) >= max_moves:
                break
            claims = [
                c for c in self.repo.find_by_agent_id(over_id)
                if c.status == ClaimStatus.active and c.progress < 25
            ]
            claims.sort(key=lambda c: c.progress)
            for claim in claims:
                if len(moves) >= max_moves:
                    break
                if not underloaded:
                    break
                target_id = underloaded[0]
                moves.append((claim.id, over_id, target_id))
                # Reduce underloaded capacity tracking
                new_pct = load_map.get(target_id, 0) + 20
                load_map[target_id] = new_pct
                if new_pct >= underload_threshold_pct:
                    underloaded.pop(0)

        logger.info(f"[VECTOR][claims] rebalance produced {len(moves)} move(s)")
        return moves

    def find_overloaded(
        self, agents: list[Claimant], threshold: float = 90.0
    ) -> list[str]:
        load = self.get_agent_load([a.id for a in agents])
        return [aid for aid, pct in load.items() if pct >= threshold]

    def find_underloaded(
        self, agents: list[Claimant], threshold: float = 30.0
    ) -> list[str]:
        load = self.get_agent_load([a.id for a in agents])
        return [aid for aid, pct in load.items() if pct <= threshold]

    # ------------------------------------------------------------------
    # Background check loop
    # ------------------------------------------------------------------

    def schedule_check(
        self,
        interval_minutes: int = 5,
        agents: Optional[list[Claimant]] = None,
    ) -> None:
        """
        Start a background asyncio task that calls rebalance() every
        interval_minutes.  Safe to call multiple times (replaces previous task).
        """
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()

        async def _loop() -> None:
            while True:
                try:
                    await asyncio.sleep(interval_minutes * 60)
                    if agents:
                        moves = self.rebalance(agents)
                        if moves:
                            logger.info(
                                f"[VECTOR][claims] scheduled rebalance: {len(moves)} moves available"
                            )
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error(f"[VECTOR][claims] rebalance loop error: {exc}")

        loop = asyncio.get_event_loop()
        self._background_task = loop.create_task(_loop())
        logger.info(
            f"[VECTOR][claims] load balancer check scheduled every {interval_minutes}min"
        )


# ---------------------------------------------------------------------------
# Singleton lazy-init helpers (shared across MCP functions)
# ---------------------------------------------------------------------------

_repo: Optional[ClaimRepository] = None
_claim_svc: Optional[ClaimService] = None
_steal_svc: Optional[WorkStealingService] = None
_lb: Optional[LoadBalancer] = None


def _get_repo() -> ClaimRepository:
    global _repo
    if _repo is None:
        _repo = ClaimRepository()
    return _repo


def _get_claim_svc() -> ClaimService:
    global _claim_svc
    if _claim_svc is None:
        _claim_svc = ClaimService(_get_repo())
    return _claim_svc


def _get_steal_svc() -> WorkStealingService:
    global _steal_svc
    if _steal_svc is None:
        _steal_svc = WorkStealingService(_get_repo())
    return _steal_svc


def _get_lb() -> LoadBalancer:
    global _lb
    if _lb is None:
        _lb = LoadBalancer(_get_repo())
    return _lb


# ---------------------------------------------------------------------------
# MCP tool functions
# ---------------------------------------------------------------------------


async def mcp_claim_task(
    issue_id: str,
    agent_id: str,
    agent_name: str,
    capabilities: Optional[list[str]] = None,
    title: str = "",
    priority: str = "medium",
) -> dict[str, Any]:
    """MCP wrapper: claim a VECTOR task."""
    svc = _get_claim_svc()
    claimant = Claimant(
        id=agent_id,
        type="agent",
        name=agent_name,
        capabilities=capabilities or [],
    )
    claim = svc.claim(
        issue_id=issue_id,
        claimant=claimant,
        issue_title=title,
        priority=IssuePriority(priority) if priority in IssuePriority._value2member_map_ else IssuePriority.medium,
    )
    if claim is None:
        return {"success": False, "error": "Claim failed (already claimed, capacity, or capability mismatch)"}
    return {
        "success": True,
        "claim_id": claim.id,
        "issue_id": claim.issue_id,
        "claimant": claim.claimant.name,
        "status": claim.status.value,
        "claimed_at": claim.claimed_at,
    }


async def mcp_release_task(issue_id: str, agent_id: str) -> dict[str, Any]:
    """MCP wrapper: release a VECTOR task claim."""
    svc = _get_claim_svc()
    ok = svc.release(issue_id, agent_id)
    return {"success": ok, "issue_id": issue_id, "agent_id": agent_id}


async def mcp_list_claims(agent_id: Optional[str] = None) -> dict[str, Any]:
    """MCP wrapper: list active claims, optionally filtered by agent."""
    repo = _get_repo()
    if agent_id:
        claims = [
            c for c in repo.find_by_agent_id(agent_id) if c.status in _ACTIVE_STATUSES
        ]
    else:
        claims = repo.find_all_active()
    return {
        "total": len(claims),
        "claims": [
            {
                "claim_id": c.id,
                "issue_id": c.issue_id,
                "claimant": c.claimant.name,
                "status": c.status.value,
                "progress": c.progress,
                "last_activity_at": c.last_activity_at,
            }
            for c in claims
        ],
    }


async def mcp_steal_task(
    issue_id: str,
    stealer_id: str,
    stealer_name: str,
) -> dict[str, Any]:
    """MCP wrapper: steal a stealable VECTOR task."""
    svc = _get_steal_svc()
    stealer = Claimant(id=stealer_id, type="agent", name=stealer_name)
    claim = svc.steal(issue_id, stealer)
    if claim is None:
        return {"success": False, "error": "Steal failed (not stealable, grace period, progress, or capacity)"}
    return {
        "success": True,
        "claim_id": claim.id,
        "issue_id": claim.issue_id,
        "new_owner": claim.claimant.name,
        "contest_window_ends_at": (
            claim.contest_info.window_ends_at if claim.contest_info else None
        ),
    }


async def mcp_get_stealable() -> dict[str, Any]:
    """MCP wrapper: list all stealable tasks."""
    svc = _get_steal_svc()
    claims = svc.get_stealable()
    return {
        "total": len(claims),
        "stealable": [
            {
                "claim_id": c.id,
                "issue_id": c.issue_id,
                "current_owner": c.claimant.name,
                "progress": c.progress,
                "reason": c.steal_info.reason.value if c.steal_info else "unknown",
                "marked_at": c.steal_info.marked_at if c.steal_info else None,
            }
            for c in claims
        ],
    }


async def mcp_rebalance_load(agent_ids: list[str]) -> dict[str, Any]:
    """MCP wrapper: compute and return rebalance move recommendations."""
    repo = _get_repo()
    lb = _get_lb()
    agents = []
    for aid in agent_ids:
        claims = repo.find_by_agent_id(aid)
        agents.append(
            Claimant(id=aid, type="agent", name=aid, current_workload=len(claims))
        )
    moves = lb.rebalance(agents)
    load = lb.get_agent_load(agent_ids)
    return {
        "moves": [
            {"claim_id": m[0], "from_agent": m[1], "to_agent": m[2]} for m in moves
        ],
        "total_moves": len(moves),
        "load_map": load,
    }


async def mcp_claim_stats() -> dict[str, Any]:
    """MCP wrapper: overall claim statistics."""
    repo = _get_repo()
    all_claims = repo.find_all()
    by_status: dict[str, int] = {}
    for c in all_claims:
        key = c.status.value
        by_status[key] = by_status.get(key, 0) + 1

    active_count = sum(1 for c in all_claims if c.status in _ACTIVE_STATUSES)
    completed_count = sum(1 for c in all_claims if c.status == ClaimStatus.completed)
    stealable_count = sum(1 for c in all_claims if c.status == ClaimStatus.stealable)
    avg_progress = (
        sum(c.progress for c in all_claims) / len(all_claims) if all_claims else 0
    )

    return {
        "total_claims": len(all_claims),
        "active_claims": active_count,
        "completed_claims": completed_count,
        "stealable_claims": stealable_count,
        "avg_progress": round(avg_progress, 1),
        "by_status": by_status,
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    print("[VECTOR][claims] running smoke test …")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_claims.db"

        repo = ClaimRepository(db_path=db_path)
        claim_svc = ClaimService(repo)
        steal_svc = WorkStealingService(repo, WorkStealingConfig(grace_period_minutes=0))
        lb = LoadBalancer(repo)

        # 1. Create a claimant and claim a task
        alice = Claimant(id="agent-alice", type="agent", name="alice",
                         capabilities=["python", "testing"], specializations=["tester"])
        claim = claim_svc.claim(
            issue_id="issue-001",
            claimant=alice,
            issue_title="Fix flaky test",
            priority=IssuePriority.high,
        )
        assert claim is not None, "claim should succeed"
        assert claim.status == ClaimStatus.active
        print(f"  ✓ alice claimed issue-001 → claim_id={claim.id}")

        # 2. Update progress to 30 %
        ok = claim_svc.update_progress("issue-001", "agent-alice", 30)
        assert ok, "progress update should succeed"
        refreshed = repo.find_by_issue_id("issue-001")
        assert refreshed is not None and refreshed.progress == 30
        print(f"  ✓ progress updated to 30%")

        # 3. Mark stealable (grace_period_minutes=0 so it passes)
        marked = steal_svc.mark_stealable("issue-001", StealableReason.manual, 30)
        assert marked, "mark_stealable should succeed"
        stealable = repo.find_by_issue_id("issue-001")
        assert stealable is not None and stealable.status == ClaimStatus.stealable
        print(f"  ✓ issue-001 marked stealable")

        # 4. Bob steals the task
        bob = Claimant(id="agent-bob", type="agent", name="bob",
                       capabilities=["python", "testing"], specializations=["tester"])
        stolen = steal_svc.steal("issue-001", bob)
        assert stolen is not None, "steal should succeed"
        assert stolen.claimant.id == "agent-bob"
        print(f"  ✓ bob stole issue-001 from alice")

        # 5. Verify new owner
        final = repo.find_by_issue_id("issue-001")
        assert final is not None and final.claimant.id == "agent-bob"
        assert final.claimant.name == "bob"
        print(f"  ✓ verified new owner is bob (status={final.status.value})")

        # 6. Load balancer sanity check
        load = lb.get_agent_load(["agent-alice", "agent-bob"])
        assert "agent-alice" in load and "agent-bob" in load
        print(f"  ✓ load map: {load}")

        # 7. Stats
        stats = asyncio.run(mcp_claim_stats())
        assert stats["total_claims"] >= 1
        print(f"  ✓ stats: {stats}")

    print("[VECTOR][claims] ✅ smoke test PASSED")
