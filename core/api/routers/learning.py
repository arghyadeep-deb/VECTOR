"""VECTOR learning router - /learning/* endpoints."""

__all__ = [
    "extract_concepts",
    "ExtractConceptsReq",
    "generate_quiz",
    "GenerateQuizReq",
    "ingest_video",
    "IngestVideoReq",
    "router",
    "track_course",
    "TrackCourseReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/learning", tags=["learning"])


class IngestVideoReq(BaseModel):
    url: str = ""
    language: str = "en"

@router.post("/ingest-video")
async def ingest_video(body: IngestVideoReq):
    """Extract transcript and concepts from any video URL."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "ingest_video", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][learning] ingest_video failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TrackCourseReq(BaseModel):
    course_name: str = ""
    platform: str = ""
    progress_pct: int = 0

@router.post("/track-course")
async def track_course(body: TrackCourseReq):
    """Track course enrollment and completion."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "track_course", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][learning] track_course failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ExtractConceptsReq(BaseModel):
    content: str = ""
    depth: int = 2

@router.post("/extract-concepts")
async def extract_concepts(body: ExtractConceptsReq):
    """Extract concept dependency graph from content."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "extract_concepts", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][learning] extract_concepts failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateQuizReq(BaseModel):
    topic: str = ""
    difficulty: str = "medium"
    count: int = 5

@router.post("/quiz-generate")
async def generate_quiz(body: GenerateQuizReq):
    """Generate quiz from learned material."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_quiz", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][learning] generate_quiz failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
