"""Background task management REST endpoints."""
from loguru import logger

__all__ = [
    "cancel_task",
    "ExternalTaskRequest",
    "get_task",
    "ingest_external_task",
    "list_tasks",
    "router",
    "submit_task",
    "SubmitRequest",
]

import os
import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

router = APIRouter(prefix="/tasks", tags=["tasks"])

# â”€â”€ Rate limiting (Phase 1C) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_RATE_LIMIT_PER_MIN = int(os.environ.get("VECTOR_TASK_RATE_PER_MIN", "60"))
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate(authorization: str | None) -> None:
    """Token-bucket rate limiter: max VECTOR_TASK_RATE_PER_MIN requests/min/key."""
    key = (authorization or "anon")[:48]  # truncate for safety
    now = time.time()
    bucket = _rate_buckets[key]
    # Evict timestamps older than 60s
    _rate_buckets[key] = [t for t in bucket if now - t < 60]
    if len(_rate_buckets[key]) >= _RATE_LIMIT_PER_MIN:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_RATE_LIMIT_PER_MIN} requests/min",
        )
    _rate_buckets[key].append(now)

# â”€â”€ External task ingestion (Gap 3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Pre-shared key auth: set VECTOR_TASK_API_KEY in .env.
# External callers (phone, cloud, ESP32) POST to /api/v1/tasks with
# Authorization: Bearer <key>. Validated through permission gateway.

def _check_api_key(authorization: str | None) -> None:
    from core.security.secrets_manager import get_secret
    task_api_key = get_secret("VECTOR_TASK_API_KEY")
    if not task_api_key:
        # Fail-closed: require explicit opt-in to open mode (Phase 1B)
        if os.environ.get("VECTOR_ALLOW_OPEN_TASK_API") != "1":
            raise HTTPException(
                status_code=503,
                detail=(
                    "External task API requires VECTOR_TASK_API_KEY to be set. "
                    "Set the env var or VECTOR_ALLOW_OPEN_TASK_API=1 to override (dev only)."
                ),
            )
        return  # explicit dev opt-in
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, task_api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")


class ExternalTaskRequest(BaseModel):
    text: str                    # natural-language task description
    source: str = "external"     # phone | cloud | esp32 | webhook | etc.
    priority: str = "normal"     # normal | high | critical
    district: str | None = None  # optional routing hint


@router.post("/api/v1/tasks")
async def ingest_external_task(
    req: ExternalTaskRequest,
    authorization: str | None = Header(default=None),
):
    """
    External task ingestion endpoint (Gap 3).
    Accepts tasks from phone, cloud agents, ESP32, webhooks.
    Validates through permission gateway before injecting into the think→act pipeline.
    """
    _check_api_key(authorization)
    _check_rate(authorization)

    from core.loop.permission_gateway import PermissionGateway, Action
    gw = PermissionGateway()
    action = Action(
        action_type="respond",
        params={"message": req.text, "source": req.source, "district": req.district},
        proposed_by=req.source,
        priority=req.priority,
    )
    result = await gw.execute(action)

    if not result.approved:
        return {
            "accepted": False,
            "source": req.source,
            "gateway_level": result.level,
            "message": result.reason or "Task blocked by Permission Gateway.",
        }

    # Inject into the autonomous loop's pending voice intent so it gets
    # processed immediately (event-driven wake — no 10s poll wait).
    # BUG FIX: _pending_voice is a dict|None, not a list — .append() always
    # raised and was swallowed by the except below.
    try:
        import asyncio as _aio
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop.get_instance()
        if loop is not None:
            loop._pending_voice = {
                "intent": "respond",
                "params": {"query": req.text},
                "source": req.source,
                "confidence": 0.8,
                "actionable": True,
            }
            _aio.create_task(loop.wake_think())
    except Exception: logger.warning("[VECTOR][tasks] loop not running, task executed via gateway") # loop not running — task still executed via gateway above

    return {
        "accepted": True,
        "source": req.source,
        "gateway_level": result.level if hasattr(result, "level") else str(result),
        "message": result.result.get("message", "Task queued.") if hasattr(result, "result") else "Task queued.",
    }


class SubmitRequest(BaseModel):
    name:     str
    query:    str
    district: str  = "research"
    priority: str  = "NORMAL"


@router.get("/")
async def list_tasks():
    """Running + recent tasks summary."""
    from core.loop.task_queue import TaskQueue
    return TaskQueue.get().summary()


@router.get("/{task_id}")
async def get_task(task_id: str):
    from core.loop.task_queue import TaskQueue
    task = TaskQueue.get().status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return task.to_dict()


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    from core.loop.task_queue import TaskQueue
    cancelled = TaskQueue.get().cancel(task_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found or already done")
    return {"cancelled": task_id}


@router.post("/submit")
async def submit_task(req: SubmitRequest):
    """Submit a background research/analysis task."""
    from core.loop.task_queue import TaskQueue, Priority

    try:
        priority = Priority[req.priority.upper()]
    except KeyError:
        priority = Priority.NORMAL

    tq = TaskQueue.get()

    # Route by district
    if req.district == "research":
        async def _work():
            from districts.research.research_hub import ResearchHub
            hub = ResearchHub()
            results = await hub.search_web(req.query, max_results=10)
            digest  = await hub.daily_digest() if req.query.lower() == "digest" else None
            return {"results": results[:10], "digest": digest}
    elif req.district == "council":
        async def _work():
            from districts.governance.llm_council import LLMCouncil
            return await LLMCouncil().convene(
                question=req.query, stakes="high", requester_hp=700
            )
    else:
        async def _work():
            from core.inference.ollama_safe import chat
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt()
            import asyncio
            return await asyncio.to_thread(
                chat,
                model="vector-deep",
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": req.query},
                ],
                timeout=300.0,
                caller_id="api_tasks_submit",
            )

    task_id = tq.submit(
        _work(),
        name=req.name,
        priority=priority,
        district=req.district,
        tags=[req.district, "api"],
    )
    return {"task_id": task_id, "status": "queued"}
