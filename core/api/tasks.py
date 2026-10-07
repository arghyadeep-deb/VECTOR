"""External task ingestion API — phone, cloud, ESP32 push tasks here."""
import hmac

__all__ = [
    "health",
    "router",
    "submit_task",
    "TaskSubmission",
]

import os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskSubmission(BaseModel):
    action_type: str
    params: dict = Field(default_factory=dict)
    source: str = "external"
    priority: str = "normal"


def _internal_token() -> str:
    """Read the token at call time, not at import time — a module-global
    frozen at import made this unreachable/untestable whenever
    VECTOR_INTERNAL_TOKEN was set after this module first imported (.env
    load ordering, or a test monkeypatching os.environ). Same fix already
    applied to core/api/auth.py's _api_key() for the identical reason."""
    return os.environ.get("VECTOR_INTERNAL_TOKEN", "")


@router.post("")
async def submit_task(
    task: TaskSubmission,
    authorization: str = Header(None),
):
    internal_token = _internal_token()
    if not internal_token:
        raise HTTPException(
            503,
            "External task ingestion requires VECTOR_INTERNAL_TOKEN to be set",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization")
    token = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(token, internal_token):
        raise HTTPException(403, "Invalid token")
    from core.loop.autonomous_loop import AutonomousLoop
    # BUG FIX: previously constructed a FRESH AutonomousLoop() and set
    # _pending_voice on it — the running loop never saw the intent. Use the
    # running-loop singleton; fall back to a throwaway instance only for the
    # gateway evaluation side-effect when the loop isn't running.
    loop = AutonomousLoop.get_instance()
    gateway = (loop or AutonomousLoop())._get_gateway()
    gateway_result = await gateway.evaluate_external(
        task.action_type, task.params, task.source,
    )
    if not gateway_result.approved:
        return {
            "status": "blocked",
            "source": task.source,
            "reason": gateway_result.reason,
            "level": gateway_result.level,
        }
    if loop is not None:
        loop._pending_voice = {
            "intent": task.action_type,
            "params": task.params,
            "source": task.source,
            "confidence": 0.95 if task.priority == "critical" else 0.8,
            "actionable": True,
        }
        # event-driven: process NOW instead of waiting for the 10s think poll
        import asyncio as _aio
        _aio.create_task(loop.wake_think())
        return {"status": "accepted", "source": task.source}
    return {"status": "accepted_no_loop", "source": task.source,
            "note": "autonomous loop not running — gateway evaluated only"}


@router.get("/health")
async def health():
    return {"status": "ok"}
