"""Mission planning and execution API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.runtime.missions import (
    MISSION_JOBS,
    MISSION_STORE,
    MissionPlanAdvisor,
    MissionRunner,
    ObjectiveDecomposer,
)


router = APIRouter(prefix="/missions", tags=["missions"])


def _safe_proposed_by(value: str) -> str:
    """Neutralise reserved owner-trust markers on this client-supplied field.

    2026-08-04: mission steps execute through the PermissionGateway, so a
    body claiming {"proposed_by": "api_command"} would otherwise inherit the
    RED_INTERACTIVE_TOOLS owner-initiated bypass (shell/GUI/code execution
    with no owner approval). Imported lazily to match this package's existing
    gateway-import style and avoid an import cycle at module load.
    """
    from core.loop.permission_gateway import sanitize_proposed_by

    return sanitize_proposed_by(value, fallback="api.missions")


class MissionRequest(BaseModel):
    objective: str = Field(..., min_length=1)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    proposed_by: str = "api.missions"
    dry_run: bool = False
    max_steps: int = 8
    decompose: bool = False
    llm_plan: bool = False


class RollbackRequest(BaseModel):
    reason: str = "Manual rollback requested."


def _runner_from_request(request: Request) -> MissionRunner:
    gateway = getattr(request.app.state, "permission_gateway", None)
    return MissionRunner(permission_gateway=gateway, app_state=request.app.state)


@router.post("/plan")
async def plan_mission(body: MissionRequest, request: Request) -> dict[str, Any]:
    mission = _runner_from_request(request).plan(
        objective=body.objective,
        steps=body.steps,
        proposed_by=_safe_proposed_by(body.proposed_by),
        max_steps=body.max_steps,
        decompose=body.decompose,
        llm_plan=body.llm_plan,
    )
    return {"status": "planned", "mission": mission.to_dict()}


@router.post("/run")
async def run_mission(body: MissionRequest, request: Request) -> dict[str, Any]:
    runner = _runner_from_request(request)
    mission = runner.plan(
        objective=body.objective,
        steps=body.steps,
        proposed_by=_safe_proposed_by(body.proposed_by),
        max_steps=body.max_steps,
        decompose=body.decompose,
        llm_plan=body.llm_plan,
    )
    mission = await runner.run(mission, dry_run=body.dry_run)
    return {"status": mission.status, "mission": mission.to_dict()}


@router.post("/run-async")
async def run_mission_async(body: MissionRequest, request: Request) -> dict[str, Any]:
    runner = _runner_from_request(request)
    mission = runner.plan(
        objective=body.objective,
        steps=body.steps,
        proposed_by=_safe_proposed_by(body.proposed_by),
        max_steps=body.max_steps,
        decompose=body.decompose,
        llm_plan=body.llm_plan,
    )
    job = MISSION_JOBS.submit(mission, runner, dry_run=body.dry_run)
    return {
        "status": job.status,
        "job": job.to_dict(),
        "mission": mission.to_dict(),
    }


@router.post("/decompose")
async def decompose_mission(body: MissionRequest) -> dict[str, Any]:
    decomposition = ObjectiveDecomposer().decompose(
        body.objective,
        max_steps=body.max_steps,
    )
    return {"status": decomposition["status"], "decomposition": decomposition}


@router.post("/advise")
async def advise_mission(body: MissionRequest, request: Request) -> dict[str, Any]:
    gateway = getattr(request.app.state, "permission_gateway", None)
    decomposition = MissionPlanAdvisor(permission_gateway=gateway).advise(
        body.objective,
        max_steps=body.max_steps,
    )
    return {"status": decomposition["status"], "decomposition": decomposition}


@router.get("")
async def list_missions(limit: int = 20) -> dict[str, Any]:
    missions = [mission.to_dict() for mission in MISSION_STORE.list(limit=limit)]
    return {"status": "ok", "count": len(missions), "missions": missions}


@router.get("/jobs")
async def list_mission_jobs(limit: int = 20) -> dict[str, Any]:
    jobs = [job.to_dict() for job in MISSION_JOBS.list(limit=limit)]
    return {"status": "ok", "count": len(jobs), "jobs": jobs}


@router.get("/jobs/{job_id}")
async def get_mission_job(job_id: str) -> dict[str, Any]:
    job = MISSION_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Mission job {job_id!r} not found")
    mission = MISSION_STORE.get(job.mission_id)
    return {
        "status": job.status,
        "job": job.to_dict(),
        "mission": mission.to_dict() if mission else None,
    }


@router.get("/{mission_id}/timeline")
async def get_mission_timeline(mission_id: str) -> dict[str, Any]:
    mission = MISSION_STORE.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return {
        "status": mission.status,
        "mission_id": mission.id,
        "events": [event.to_dict() for event in mission.events],
        "artifacts": [artifact.to_dict() for artifact in mission.artifacts],
    }


@router.get("/{mission_id}/artifacts")
async def get_mission_artifacts(mission_id: str) -> dict[str, Any]:
    mission = MISSION_STORE.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return {
        "status": mission.status,
        "mission_id": mission.id,
        "count": len(mission.artifacts),
        "artifacts": [artifact.to_dict() for artifact in mission.artifacts],
    }


@router.post("/{mission_id}/retry")
async def retry_mission(mission_id: str, request: Request) -> dict[str, Any]:
    mission = MISSION_STORE.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    mission = await _runner_from_request(request).retry(mission)
    return {"status": mission.status, "mission": mission.to_dict()}


@router.post("/{mission_id}/rollback")
async def rollback_mission(
    mission_id: str,
    body: RollbackRequest,
    request: Request,
) -> dict[str, Any]:
    mission = MISSION_STORE.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    mission = _runner_from_request(request).request_rollback(mission, reason=body.reason)
    return {"status": mission.status, "mission": mission.to_dict()}


@router.get("/{mission_id}")
async def get_mission(mission_id: str) -> dict[str, Any]:
    mission = MISSION_STORE.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return {"status": mission.status, "mission": mission.to_dict()}
