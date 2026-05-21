"""VECTOR learning router - /learning/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/learning", tags=["learning"])


def _run(task_type: str, params: dict) -> dict:
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            gov.dispatch({"type": task_type, "params": params})
        )
    finally:
        loop.close()
    return result


class IngestVideoReq(BaseModel):
    url: str = ""
    language: str = "en"

@router.post("/ingest-video")
async def ingest_video(body: IngestVideoReq):
    """Extract transcript and concepts from any video URL."""
    try:
        return _run("ingest_video", body.model_dump())
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
    try:
        return _run("track_course", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][learning] track_course failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ExtractConceptsReq(BaseModel):
    content: str = ""
    depth: int = 2

@router.post("/extract-concepts")
async def extract_concepts(body: ExtractConceptsReq):
    """Extract concept dependency graph from content."""
    try:
        return _run("extract_concepts", body.model_dump())
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
    try:
        return _run("generate_quiz", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][learning] generate_quiz failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
