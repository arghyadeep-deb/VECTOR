"""Autonomous execution API.

Planning is safe and side-effect free. Running actions always delegates to the
PermissionGateway and reports blocked/failed outcomes honestly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.runtime.executor import AutonomousExecutor


router = APIRouter(prefix="/execute", tags=["execution"])


class ExecuteRequest(BaseModel):
    action_type: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    proposed_by: str = "api.executor"
    dry_run: bool = False


def _executor_from_request(request: Request) -> AutonomousExecutor:
    gateway = getattr(request.app.state, "permission_gateway", None)
    return AutonomousExecutor(permission_gateway=gateway, app_state=request.app.state)


@router.post("/plan")
async def plan_endpoint(body: ExecuteRequest, request: Request) -> dict[str, Any]:
    # proposed_by is client-supplied here — never let it claim a reserved
    # owner-trust marker (see sanitize_proposed_by's docstring).
    from core.loop.permission_gateway import sanitize_proposed_by

    plan = _executor_from_request(request).plan(
        action_type=body.action_type,
        params=body.params,
        proposed_by=sanitize_proposed_by(body.proposed_by, fallback="api.executor"),
    )
    return {"status": "planned", "plan": plan.to_dict()}


@router.post("/run")
async def run_endpoint(body: ExecuteRequest, request: Request) -> dict[str, Any]:
    # 2026-08-04: without this, POST /execute/run with
    # {"proposed_by": "api_command"} would hit the RED_INTERACTIVE_TOOLS
    # owner-initiated bypass and execute arbitrary shell with no approval.
    from core.loop.permission_gateway import sanitize_proposed_by

    report = await _executor_from_request(request).execute(
        action_type=body.action_type,
        params=body.params,
        proposed_by=sanitize_proposed_by(body.proposed_by, fallback="api.executor"),
        dry_run=body.dry_run,
    )
    return report.to_dict()
