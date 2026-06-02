"""Content district router — /content/* endpoints.

Exposes the ContentScheduler (postiz feedback loop):
  GET  /content/scheduled  — summary of all post jobs by status
  POST /content/schedule   — schedule a new post across platforms
  POST /content/run        — publish all pending jobs immediately
"""

__all__ = [
    "get_scheduled_posts",
    "schedule_post",
    "run_pending_posts",
    "router",
    "SchedulePostReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/content", tags=["content"])


class SchedulePostReq(BaseModel):
    title: str
    content: str
    platforms: list[str]
    scheduled_for: str = ""


@router.get("/scheduled")
async def get_scheduled_posts():
    """Return per-status job counts for the content post queue."""
    try:
        from districts.content.content_scheduler import ContentScheduler
        s = ContentScheduler()
        return s.get_summary()
    except Exception as e:
        logger.error("[VECTOR][content] get_scheduled_posts failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schedule")
async def schedule_post(body: SchedulePostReq):
    """Schedule a post for publishing across the given platforms."""
    try:
        from districts.content.content_scheduler import ContentScheduler
        s = ContentScheduler()
        return await s.schedule_post(
            title=body.title,
            content=body.content,
            platforms=body.platforms,
            scheduled_for=body.scheduled_for or None,
        )
    except Exception as e:
        logger.error("[VECTOR][content] schedule_post failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_pending_posts():
    """Publish all pending/retrying post jobs immediately."""
    try:
        from districts.content.content_scheduler import ContentScheduler
        s = ContentScheduler()
        return await s.run_pending()
    except Exception as e:
        logger.error("[VECTOR][content] run_pending_posts failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
