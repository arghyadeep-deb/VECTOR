"""VectorCode v3 Agent — domain entity for the agent lifecycle system."""

from datetime import datetime, timezone
from typing import Any, Callable, Optional

class Agent:
    def __init__(self, agent_id: str, agent_type: str, *,
                 capabilities: Optional[list[str]] = None,
                 role: Optional[str] = None,
                 parent: Optional[str] = None,
                 metadata: Optional[dict] = None):
        self.id = agent_id
        self.type = agent_type
        self.status = "idle"
        self.capabilities = capabilities or []
        self.role = role
        self.parent = parent
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.last_active = self.created_at

    def can_execute(self, task_type: str) -> bool:
        # Deliberately ignores task_type -- this is a general-availability
        # check, not a capability check. coordinator.py's assign_task()
        # relies on this exact behavior: a real capability match is done
        # separately via `task_type in a.capabilities` at its first tier,
        # and this method is reused unmodified as the capability-blind
        # "any available agent" fallback at its second tier. Do not change
        # this to check capabilities -- it would silently defeat that
        # fallback (both tiers would then return the same, possibly empty,
        # result). The task_type parameter is kept for interface
        # consistency with that call site, not because it's used.
        return self.status in ("idle", "active")

    def assign_task(self, task: Any) -> None:
        self.status = "busy"
        from datetime import datetime, timezone
        self.last_active = datetime.now(timezone.utc).isoformat()

    def complete_task(self) -> None:
        self.status = "idle"
        from datetime import datetime, timezone
        self.last_active = datetime.now(timezone.utc).isoformat()

    def fail_task(self) -> None:
        self.status = "idle"
        self.last_active = datetime.now(timezone.utc).isoformat()

    def terminate(self) -> None:
        self.status = "terminated"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "capabilities": self.capabilities,
            "role": self.role,
            "parent": self.parent,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }
