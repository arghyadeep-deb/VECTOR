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
    # RR-3.7B (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
    # RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md): this used to call
    # governor.dispatch({"type": "ingest_video", ...}) directly -- zero
    # PermissionGateway anywhere in the path. "video" is an exact
    # DISTRICT_TASK_MAP key (governor.py) and a substring of "ingest_video",
    # so district resolution to "learning" is deterministic, not an LLM
    # guess. districts/learning/video_ingestor.py::VideoIngestor.run() has
    # NO task_type check at all -- it fires a real yt-dlp download of
    # `params["url"]` (fully caller-controlled) for ANY task carrying a url
    # param, whenever VideoIngestor is the learning district's highest-HP
    # agent. "ingest_video" has never been assigned a permission tier in
    # core/config.py (confirmed by grep) -- per this mission's Section 6
    # ("do not invent tiers, do not mass-classify UNKNOWN action names just
    # to make endpoints work"), this is NOT added to
    # _PLAN_COMPOSABLE_ACTION_TYPES. Routing through PermissionGateway lets
    # its existing fail-closed UNKNOWN-tier behavior deny this by default
    # (core/loop/permission_gateway.py's `# UNKNOWN — default to RED, never
    # silently allow` branch) until an owner consciously assigns a real
    # tier -- the correct outcome for an unreviewed external-fetch capability,
    # not a functional regression to work around.
    from core.loop.decision_engine import DecisionEngine, Candidate
    from core.loop.permission_gateway import PermissionGateway, Action
    try:
        candidate = Candidate(
            action_type="ingest_video",
            params=body.model_dump(),
            goal_ids=[],
            urgency=0.3,
            confidence=0.9,
            source="structured_api",
        )
        decision = await DecisionEngine().evaluate([candidate])
        winner = decision.winner
        gateway_result = await PermissionGateway().execute(Action(
            action_type=winner.action_type,
            params=winner.params,
            proposed_by="structured_api",
        ))
        result = gateway_result.result or {}
        if not gateway_result.approved:
            return {"status": "blocked", "reason": gateway_result.reason, "level": gateway_result.level}
        if result.get("status") == "not_implemented":
            return {"status": "not_implemented", "note": result.get("note")}
        return result
    except Exception as e:
        logger.error("[VECTOR][learning] ingest_video failed: {}", e)
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
        logger.error("[VECTOR][learning] track_course failed: {}", e)
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
        logger.error("[VECTOR][learning] extract_concepts failed: {}", e)
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
        logger.error("[VECTOR][learning] generate_quiz failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
