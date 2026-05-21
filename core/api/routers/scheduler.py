"""Scheduler router — /scheduler/jobs."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

from core.api.schemas import SchedulerJobsResponse

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

@router.get("/jobs", response_model=SchedulerJobsResponse)
async def scheduler_jobs():
    try:
        from core.scheduler.store import SchedulerStore
        store = SchedulerStore(Path.home() / ".vector" / "scheduler.db")
        all_tasks = store.list_tasks()
        active_tasks = store.list_tasks(status="active")
        return SchedulerJobsResponse(
            total=len(all_tasks),
            active=len(active_tasks),
            jobs=all_tasks,
        )
    except Exception as e:
        logger.warning(f"[VECTOR][api][scheduler] jobs failed: {e}")
        return SchedulerJobsResponse(total=0, active=0, jobs=[])

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ scheduler.py OK")
