"""VECTOR projects router - /projects/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/projects", tags=["projects"])


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


class CreateProjectReq(BaseModel):
    name: str = ""
    description: str = ""
    deadline: str = ""

@router.post("/create")
async def create_project(body: CreateProjectReq):
    """Create project with roadmap and milestones."""
    try:
        return _run("create_project", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][projects] create_project failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_projects():
    """List all active projects with progress."""
    try:
        return _run("list_projects", {})
    except Exception as e:
        logger.error("[VECTOR][projects] list_projects failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TrackExperimentReq(BaseModel):
    name: str = ""
    hypothesis: str = ""
    metric: str = ""

@router.post("/experiment")
async def track_experiment(body: TrackExperimentReq):
    """Track experiment: hypothesis, run, results."""
    try:
        return _run("track_experiment", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][projects] track_experiment failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deadline")
async def upcoming_deadlines():
    """Get upcoming project deadlines."""
    try:
        return _run("upcoming_deadlines", {})
    except Exception as e:
        logger.error("[VECTOR][projects] upcoming_deadlines failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
