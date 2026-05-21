"""External task ingestion API — phone, cloud, ESP32 push tasks here."""
import hmac
import os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskSubmission(BaseModel):
    action_type: str
    params: dict = {}
    source: str = "external"
    priority: str = "normal"


_INTERNAL_TOKEN = os.environ.get("VECTOR_INTERNAL_TOKEN", "")


@router.post("")
async def submit_task(
    task: TaskSubmission,
    authorization: str = Header(None),
):
    if _INTERNAL_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Missing authorization")
        token = authorization.removeprefix("Bearer ")
        if not hmac.compare_digest(token, _INTERNAL_TOKEN):
            raise HTTPException(403, "Invalid token")
    from core.loop.autonomous_loop import AutonomousLoop
    loop = AutonomousLoop()
    gateway = loop._get_gateway()
    await gateway.evaluate_external(task.action_type, task.params, task.source)
    loop._pending_voice = {
        "intent": task.action_type,
        "params": task.params,
        "source": task.source,
        "confidence": 0.95 if task.priority == "critical" else 0.8,
        "actionable": True,
    }
    return {"status": "accepted", "source": task.source}


@router.get("/health")
async def health():
    return {"status": "ok"}
