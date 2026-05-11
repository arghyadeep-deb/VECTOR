"""Background task management REST endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
            from agents.districts.research.research_hub import ResearchHub
            hub = ResearchHub()
            results = await hub.search_web(req.query, max_results=10)
            digest  = await hub.daily_digest() if req.query.lower() == "digest" else None
            return {"results": results[:10], "digest": digest}
    elif req.district == "council":
        async def _work():
            from agents.districts.governance.llm_council import LLMCouncil
            return await LLMCouncil().convene(
                question=req.query, stakes="high", requester_hp=700
            )
    else:
        async def _work():
            from core.inference.ollama_safe import chat
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt()
            return chat(
                model="vector-deep",
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user",   "content": req.query},
                ],
                timeout=300.0,
            )

    task_id = tq.submit(
        _work(),
        name=req.name,
        priority=priority,
        district=req.district,
        tags=[req.district, "api"],
    )
    return {"task_id": task_id, "status": "queued"}
