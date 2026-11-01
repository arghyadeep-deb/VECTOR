"""VECTOR projects router - /projects/* endpoints."""

__all__ = [
    "create_project",
    "CreateProjectReq",
    "list_projects",
    "router",
    "track_experiment",
    "TrackExperimentReq",
    "upcoming_deadlines",
]

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
    # RR-3.7B (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
    # RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md): this used to call
    # governor.dispatch({"type": "create_project", ...}) directly -- zero
    # PermissionGateway anywhere in the path -- despite "create_project"
    # being a real, YELLOW-tier (core/config.py), side-effecting action:
    # districts/projects/project_planner.py::ProjectPlanner.run() has an
    # exact `task["type"]=="create_project"` branch that writes a real
    # episodic-memory row AND a real Obsidian note file to disk, with
    # caller-supplied name/goal/deadline flowing directly into file content.
    # Fixed by routing through the same canonical Candidate ->
    # DecisionEngine.evaluate() -> PermissionGateway.execute() pipeline
    # RR-3.6/RR-3.7A already established -- proposed_by="structured_api"
    # (deliberately distinct from "api_command"/"voice" so this does NOT
    # inherit YELLOW pre-confirmation).
    from core.loop.decision_engine import DecisionEngine, Candidate
    from core.loop.permission_gateway import PermissionGateway, Action
    try:
        candidate = Candidate(
            action_type="create_project",
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
        logger.error("[VECTOR][projects] create_project failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_projects():
    """List all active projects with progress."""
    try:
        projects = _read_project_deadlines(within_days=365)
        return {
            "status": "ok",
            "projects": projects,
            "count": len(projects),
            "source": "semantic_memory.project_deadline",
        }
    except Exception as e:
        logger.error("[VECTOR][projects] list_projects failed: {}", e)
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
        logger.error("[VECTOR][projects] track_experiment failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deadline")
async def upcoming_deadlines():
    """Get upcoming project deadlines."""
    try:
        deadlines = _read_project_deadlines(within_days=30)
        return {"status": "ok", "deadlines": deadlines, "count": len(deadlines)}
    except Exception as e:
        logger.error("[VECTOR][projects] upcoming_deadlines failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


def _read_project_deadlines(within_days: int = 30) -> list[dict]:
    import datetime

    from core.memory.episodic import EpisodicMemory

    today = datetime.date.today()
    cutoff_end = today + datetime.timedelta(days=within_days)
    rows = []
    memory = EpisodicMemory()
    cur = memory.conn.cursor()
    cur.execute(
        "SELECT key, value FROM semantic_memory WHERE category = ? ORDER BY key ASC",
        ("project_deadline",),
    )
    for key, value in cur.fetchall():
        parts = str(key).split(":", 2)
        if len(parts) < 3:
            continue
        try:
            due_date = datetime.date.fromisoformat(parts[1])
        except ValueError:
            continue
        if not (today <= due_date <= cutoff_end):
            continue
        val_parts = str(value).split("|")
        rows.append({
            "name": val_parts[0] if val_parts and val_parts[0] else parts[2].replace("_", " "),
            "date": due_date.isoformat(),
            "days_away": (due_date - today).days,
            "project_id": val_parts[1] if len(val_parts) > 1 else "",
            "urgency": val_parts[2] if len(val_parts) > 2 else "medium",
        })
    return sorted(rows, key=lambda item: item["days_away"])
