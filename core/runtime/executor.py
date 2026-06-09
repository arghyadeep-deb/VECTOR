"""Safe autonomous execution contract for VECTOR.

This module does not bypass the permission gateway. It gives callers a stable
plan/execute/report shape around the existing gateway so UI, API, and future
agents can reason about action safety without claiming phantom success.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any

from core.loop.permission_gateway import Action, GatewayResult, PermissionGateway
from core.runtime.world_model import build_world_snapshot


TERMINAL_STATUSES = {"error", "failed", "not_implemented", "blocked"}


@dataclass
class ExecutionPlan:
    action_type: str
    params: dict[str, Any]
    proposed_by: str
    risk_level: str
    requires_approval: bool
    world_status: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionReport:
    status: str
    plan: dict[str, Any]
    gateway: dict[str, Any] | None
    verification: dict[str, Any]
    result: dict[str, Any]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomousExecutor:
    """Plan and execute actions through VECTOR's permission gateway."""

    def __init__(
        self,
        permission_gateway: PermissionGateway | None = None,
        app_state: Any | None = None,
    ) -> None:
        self.permission_gateway = permission_gateway or PermissionGateway()
        self.app_state = app_state

    def plan(
        self,
        action_type: str,
        params: dict[str, Any] | None = None,
        proposed_by: str = "api.executor",
    ) -> ExecutionPlan:
        params = params or {}
        risk_level = self._classify(action_type)
        snapshot = build_world_snapshot(app_state=self.app_state)
        world = snapshot.to_dict() if hasattr(snapshot, "to_dict") else snapshot
        world_status = str(world.get("runtime", {}).get("status", "unknown"))
        requires_approval = risk_level in {"YELLOW", "RED"}
        return ExecutionPlan(
            action_type=action_type,
            params=params,
            proposed_by=proposed_by,
            risk_level=risk_level,
            requires_approval=requires_approval,
            world_status=world_status,
            steps=[
                {
                    "name": "world_snapshot",
                    "status": "ready",
                    "detail": f"runtime={world_status}",
                },
                {
                    "name": "permission_classification",
                    "status": "ready",
                    "detail": risk_level,
                },
                {
                    "name": "gateway_execute",
                    "status": "pending",
                    "detail": "execution must pass PermissionGateway.execute",
                },
                {
                    "name": "verify_result",
                    "status": "pending",
                    "detail": "approved, executed, and non-terminal result required",
                },
            ],
        )

    async def execute(
        self,
        action_type: str,
        params: dict[str, Any] | None = None,
        proposed_by: str = "api.executor",
        dry_run: bool = False,
    ) -> ExecutionReport:
        plan = self.plan(action_type, params=params, proposed_by=proposed_by)
        if dry_run:
            return ExecutionReport(
                status="planned",
                plan=plan.to_dict(),
                gateway=None,
                verification={
                    "ok": True,
                    "checks": ["dry_run_only"],
                    "message": "No action executed.",
                },
                result={},
                reason="Dry run only",
            )

        action = Action(
            action_type=plan.action_type,
            params=plan.params,
            proposed_by=plan.proposed_by,
        )
        gateway_result = await self.permission_gateway.execute(action)
        gateway = self._gateway_to_dict(gateway_result)
        verification = self._verify_gateway_result(gateway_result)
        result = gateway_result.result or {}

        if verification["ok"]:
            status = "executed"
        elif not gateway_result.approved:
            status = "blocked"
        else:
            status = "failed"

        return ExecutionReport(
            status=status,
            plan=plan.to_dict(),
            gateway=gateway,
            verification=verification,
            result=result,
            reason=verification["message"],
        )

    def _classify(self, action_type: str) -> str:
        classify = getattr(self.permission_gateway, "_classify", None)
        if callable(classify):
            return str(classify(action_type))
        return "UNKNOWN"

    @staticmethod
    def _gateway_to_dict(result: GatewayResult) -> dict[str, Any]:
        return {
            "approved": bool(result.approved),
            "level": result.level,
            "executed": bool(result.executed),
            "result": result.result or {},
            "reason": result.reason,
        }

    @staticmethod
    def _verify_gateway_result(result: GatewayResult) -> dict[str, Any]:
        checks: list[str] = []
        if not result.approved:
            return {
                "ok": False,
                "checks": checks + ["not_approved"],
                "message": result.reason or "Gateway did not approve action.",
            }
        checks.append("approved")

        if not result.executed:
            return {
                "ok": False,
                "checks": checks + ["not_executed"],
                "message": "Gateway approved but did not execute action.",
            }
        checks.append("executed")

        payload = result.result or {}
        payload_status = str(payload.get("status", "executed")).lower()
        if payload_status in TERMINAL_STATUSES:
            return {
                "ok": False,
                "checks": checks + [f"result_status:{payload_status}"],
                "message": payload.get("note")
                or payload.get("error")
                or f"Action result status was {payload_status}.",
            }

        checks.append(f"result_status:{payload_status}")
        return {
            "ok": True,
            "checks": checks,
            "message": "Action approved, executed, and verified.",
        }
