"""
Rich ambient directive system with 3-way task targeting.

Replaces vectorcode's basic queue submission with:
  - Persistent directive storage to disk
  - AmbientStatus (Idle/Running/Scheduled/Paused/Disabled)
  - ScheduleTarget: Ambient | Session | Spawn
  - Priority: Low | Normal | High
  - DateTime-based scheduling with UTC awareness

Ported from the high-performance agent harness ambient.rs.
"""
from __future__ import annotations

__all__ = [
    "AmbientScheduler",
    "AmbientState",
    "AmbientStatus",
    "CycleStatus",
    "Priority",
    "ScheduledItem",
    "ScheduleTarget",
]


import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger

_AMBIENT_DIR = Path.home() / ".vector_ca" / "ambient"


# â”€â”€ Enums â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    def __lt__(self, other: "Priority") -> bool:
        order = {Priority.LOW: 0, Priority.NORMAL: 1, Priority.HIGH: 2}
        return order[self] < order[other]


class AmbientStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SCHEDULED = "scheduled"
    PAUSED = "paused"
    DISABLED = "disabled"


class CycleStatus(str, Enum):
    COMPLETE = "complete"
    INTERRUPTED = "interrupted"
    INCOMPLETE = "incomplete"


# â”€â”€ ScheduleTarget â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class ScheduleTarget:
    """
    Where a scheduled task is delivered when it becomes due.

    kind: "ambient" | "session" | "spawn"
    """
    kind: str = "ambient"
    session_id: str | None = None
    parent_session_id: str | None = None

    @classmethod
    def ambient(cls) -> "ScheduleTarget":
        return cls(kind="ambient")

    @classmethod
    def session(cls, session_id: str) -> "ScheduleTarget":
        return cls(kind="session", session_id=session_id)

    @classmethod
    def spawn(cls, parent_session_id: str) -> "ScheduleTarget":
        return cls(kind="spawn", parent_session_id=parent_session_id)

    @property
    def is_direct_delivery(self) -> bool:
        return self.kind in ("session", "spawn")

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


# â”€â”€ ScheduledItem â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class ScheduledItem:
    id: str
    scheduled_for: datetime
    context: str
    priority: Priority
    target: ScheduleTarget
    created_by_session: str
    created_at: datetime
    working_dir: str | None = None
    task_description: str | None = None
    relevant_files: list[str] = field(default_factory=list)
    git_branch: str | None = None
    additional_context: str | None = None

    def is_due(self) -> bool:
        return datetime.now(timezone.utc) >= self.scheduled_for

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "scheduled_for": self.scheduled_for.isoformat(),
            "context": self.context,
            "priority": self.priority.value,
            "target": self.target.to_dict(),
            "created_by_session": self.created_by_session,
            "created_at": self.created_at.isoformat(),
        }
        for opt in ("working_dir", "task_description", "git_branch", "additional_context"):
            if getattr(self, opt) is not None:
                d[opt] = getattr(self, opt)
        if self.relevant_files:
            d["relevant_files"] = self.relevant_files
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledItem":
        target_d = d.get("target", {})
        target = ScheduleTarget(
            kind=target_d.get("kind", "ambient"),
            session_id=target_d.get("session_id"),
            parent_session_id=target_d.get("parent_session_id"),
        )
        return cls(
            id=d["id"],
            scheduled_for=datetime.fromisoformat(d["scheduled_for"]),
            context=d["context"],
            priority=Priority(d.get("priority", "normal")),
            target=target,
            created_by_session=d.get("created_by_session", ""),
            created_at=datetime.fromisoformat(d["created_at"]),
            working_dir=d.get("working_dir"),
            task_description=d.get("task_description"),
            relevant_files=d.get("relevant_files", []),
            git_branch=d.get("git_branch"),
            additional_context=d.get("additional_context"),
        )


# â”€â”€ AmbientState â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class AmbientState:
    status: AmbientStatus = AmbientStatus.IDLE
    last_run: datetime | None = None
    last_summary: str | None = None
    last_compactions: int | None = None
    last_memories_modified: int | None = None
    total_cycles: int = 0
    status_detail: str | None = None
    next_wake: datetime | None = None
    paused_reason: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"status": self.status.value, "total_cycles": self.total_cycles}
        for opt in ("last_run", "last_summary", "last_compactions", "last_memories_modified",
                    "status_detail", "paused_reason"):
            val = getattr(self, opt)
            if val is not None:
                d[opt] = val.isoformat() if isinstance(val, datetime) else val
        if self.next_wake:
            d["next_wake"] = self.next_wake.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AmbientState":
        obj = cls(
            status=AmbientStatus(d.get("status", "idle")),
            total_cycles=d.get("total_cycles", 0),
            last_summary=d.get("last_summary"),
            last_compactions=d.get("last_compactions"),
            last_memories_modified=d.get("last_memories_modified"),
            status_detail=d.get("status_detail"),
            paused_reason=d.get("paused_reason"),
        )
        for dt_field in ("last_run", "next_wake"):
            val = d.get(dt_field)
            if val:
                setattr(obj, dt_field, datetime.fromisoformat(val))
        return obj


# â”€â”€ AmbientScheduler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AmbientScheduler:
    """
    Manages ambient directives, scheduling, and status with disk persistence.

    Usage:
        sched = AmbientScheduler()
        sched.add_directive("research trending LLM papers tonight")
        sched.schedule(
            context="run weekly code review",
            wake_in_minutes=60,
            priority=Priority.HIGH,
        )
        due = sched.take_due_items()
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._dir = (base_dir or _AMBIENT_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._dir / "state.json"
        self._queue_file = self._dir / "queue.json"
        self._directives_file = self._dir / "directives.json"

    # â”€â”€ State â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def load_state(self) -> AmbientState:
        if self._state_file.exists():
            try:
                return AmbientState.from_dict(json.loads(self._state_file.read_text()))
            except Exception as e:
                logger.warning("[VECTOR][ambient] state load failed: {}", e)
        return AmbientState()

    def save_state(self, state: AmbientState) -> None:
        self._state_file.write_text(json.dumps(state.to_dict(), indent=2))

    def set_status(self, status: AmbientStatus, **kwargs: str) -> None:
        state = self.load_state()
        state.status = status
        if "detail" in kwargs:
            state.status_detail = kwargs["detail"]
        if "reason" in kwargs:
            state.paused_reason = kwargs["reason"]
        if "next_wake" in kwargs:
            state.next_wake = datetime.fromisoformat(kwargs["next_wake"])
        self.save_state(state)
        logger.info("[VECTOR][ambient] status → {}", status.value)

    # â”€â”€ Directives â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def add_directive(self, text: str, session_id: str = "") -> str:
        """Add a persistent directive. Returns directive id."""
        directives = self._load_directives()
        d = {"id": str(uuid.uuid4()), "text": text, "session_id": session_id,
             "created_at": datetime.now(timezone.utc).isoformat()}
        directives.append(d)
        self._save_directives(directives)
        logger.info("[VECTOR][ambient] directive added: {}", text[:60])
        return d["id"]

    def load_directives(self) -> list[dict]:
        return self._load_directives()

    def take_pending_directives(self) -> list[dict]:
        """Return and clear all pending directives."""
        directives = self._load_directives()
        self._save_directives([])
        return directives

    def has_pending_directives(self) -> bool:
        return len(self._load_directives()) > 0

    def _load_directives(self) -> list[dict]:
        if self._directives_file.exists():
            try:
                return json.loads(self._directives_file.read_text())
            except Exception as e:
                logger.warning("[VECTOR][ambient] directives load failed: {}", e)
        return []

    def _save_directives(self, directives: list[dict]) -> None:
        self._directives_file.write_text(json.dumps(directives, indent=2))

    # â”€â”€ Queue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def schedule(
        self,
        context: str,
        wake_in_minutes: int | None = None,
        wake_at: datetime | None = None,
        priority: Priority = Priority.NORMAL,
        target: ScheduleTarget | None = None,
        session_id: str = "",
        task_description: str | None = None,
        relevant_files: list[str] | None = None,
        git_branch: str | None = None,
        additional_context: str | None = None,
    ) -> ScheduledItem:
        """Schedule a task for future delivery."""
        if wake_at is None and wake_in_minutes is not None:
            from datetime import timedelta
            wake_at = datetime.now(timezone.utc) + timedelta(minutes=wake_in_minutes)
        if wake_at is None:
            raise ValueError("Either wake_at or wake_in_minutes is required")

        item = ScheduledItem(
            id=str(uuid.uuid4()),
            scheduled_for=wake_at,
            context=context,
            priority=priority,
            target=target or ScheduleTarget.ambient(),
            created_by_session=session_id,
            created_at=datetime.now(timezone.utc),
            task_description=task_description,
            relevant_files=relevant_files or [],
            git_branch=git_branch,
            additional_context=additional_context,
        )
        queue = self._load_queue()
        queue.append(item.to_dict())
        queue.sort(key=lambda x: (x["scheduled_for"], {"high": 0, "normal": 1, "low": 2}[x.get("priority", "normal")]))
        self._save_queue(queue)
        logger.info("[VECTOR][ambient] scheduled: {} at {}", context[:40], wake_at.isoformat())
        return item

    def take_due_items(self) -> list[ScheduledItem]:
        """Return and remove all items whose scheduled_for has passed."""
        queue = self._load_queue()
        due, remaining = [], []
        for d in queue:
            item = ScheduledItem.from_dict(d)
            (due if item.is_due() else remaining).append(d)
        self._save_queue(remaining)
        items = [ScheduledItem.from_dict(d) for d in due]
        if items:
            logger.info("[VECTOR][ambient] {} item(s) due", len(items))
        return items

    def peek_queue(self) -> list[ScheduledItem]:
        return [ScheduledItem.from_dict(d) for d in self._load_queue()]

    def _load_queue(self) -> list[dict]:
        if self._queue_file.exists():
            try:
                return json.loads(self._queue_file.read_text())
            except Exception as e:
                logger.warning("[VECTOR][ambient] queue load failed: {}", e)
        return []

    def _save_queue(self, queue: list[dict]) -> None:
        self._queue_file.write_text(json.dumps(queue, indent=2))


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        sched = AmbientScheduler(base_dir=Path(tmpdir))

        sched.set_status(AmbientStatus.RUNNING, detail="processing tasks")
        state = sched.load_state()
        assert state.status == AmbientStatus.RUNNING

        did = sched.add_directive("check for new research papers")
        assert sched.has_pending_directives()
        directives = sched.take_pending_directives()
        assert len(directives) == 1
        assert not sched.has_pending_directives()

        from datetime import timedelta
        item = sched.schedule(
            context="run code review",
            wake_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            priority=Priority.HIGH,
        )
        due = sched.take_due_items()
        assert len(due) == 1
        assert due[0].context == "run code review"
        assert len(sched.peek_queue()) == 0

    print("OK ambient_scheduler.py")
