"""VECTOR projects router - /projects/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/projects", tags=["projects"])




class CreateProjectReq(BaseModel):
    name: str = ""
    description: str = ""
    deadline: str = ""

@router.post("/create")
async def create_project(body: CreateProjectReq):
    """Create project with roadmap and milestones."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "create_project", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][projects] create_project failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_projects():
    """List all active projects with progress."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "list_projects", "params": {}})
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
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "track_experiment", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][projects] track_experiment failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deadline")
async def upcoming_deadlines():
    """Get upcoming project deadlines."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "upcoming_deadlines", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][projects] upcoming_deadlines failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
