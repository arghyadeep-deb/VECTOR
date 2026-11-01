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
async def get_scheduled_posts(limit: int = 25):
    """Return per-status job counts AND the jobs themselves.

    2026-07-19: previously returned only {"pending": N} — the HUD content
    scheduler panel had no way to show WHAT is queued. Now includes both the
    post queue (post_jobs.db) and the video pipeline queue (content_jobs.db).
    """
    try:
        from districts.content.content_scheduler import ContentScheduler
        s = ContentScheduler()
        summary = s.get_summary()

        jobs = []
        try:
            tracker = s._get_tracker()
            for status in ("pending", "retrying", "publishing"):
                for j in tracker.list_by_status(status)[:limit]:
                    jobs.append(j.to_dict())
        except Exception as e:
            logger.warning("[VECTOR][content] post job listing failed: {}", e)

        video_jobs = []
        try:
            from districts.content.video_pipeline import get_job_queue
            video_jobs = get_job_queue(limit=limit)
        except Exception as e:
            logger.warning("[VECTOR][content] video job listing failed: {}", e)

        return {**summary, "jobs": jobs[:limit], "video_jobs": video_jobs}
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


class PostVideoReq(BaseModel):
    video_path: str
    platform: str  # "youtube" | "instagram"
    caption: str = ""


@router.post("/post-video")
async def post_video(body: PostVideoReq):
    """Post a rendered video to YouTube/Instagram via the connected phone.

    2026-07-21: direct trigger for PhonePoster (previously only reachable
    through the full video pipeline). Media is pushed over ADB into the real
    app's composer — the ban-safest path; the final Share/Upload tap follows
    growth calibration or is left to the owner.
    """
    import os
    if not os.path.isfile(body.video_path):
        raise HTTPException(status_code=400, detail=f"video not found: {body.video_path}")
    plat = body.platform.lower().strip()
    if plat not in ("youtube", "instagram"):
        raise HTTPException(status_code=400, detail="platform must be youtube or instagram")
    try:
        from districts.content.phone_poster import PhonePoster
        poster = PhonePoster()
        if plat == "youtube":
            return await poster.post_youtube(body.video_path, caption=body.caption)
        return await poster.post_instagram(body.video_path, caption=body.caption)
    except Exception as e:
        logger.error("[VECTOR][content] post_video failed: {}", e)
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
