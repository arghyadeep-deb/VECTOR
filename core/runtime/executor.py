"""Safe autonomous execution contract for VECTOR.

This module does not bypass the permission gateway. It gives callers a stable
plan/execute/report shape around the existing gateway so UI, API, and future
agents can reason about action safety without claiming phantom success.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

from core.loop.permission_gateway import Action, GatewayResult, PermissionGateway
from core.runtime.world_model import build_world_snapshot


# 2026-09-23 (third independent review round -- a real correction, not just
# an addition): a PRIOR version of this file flipped this check to a
# whitelist of exactly {"ok", "executed"}, reasoning the failure taxonomy
# was open-ended and the success taxonomy was closed. That reasoning was
# backwards. `_execute_action()`'s `hand_*` branches (and, more broadly,
# Governor.dispatch() returning a capable agent's own `run()` result
# UNMODIFIED on success -- core/city/governor.py:2701) mean the SUCCESS
# status string is chosen by whichever of ~133 district agents handled the
# task, not by this gateway -- and it is NOT canonical: a large fraction of
# real agents (districts/agency/client_manager.py, districts/calls/*,
# districts/content/*, districts/investment/*, ~100+ occurrences) use
# "success", not "ok". The whitelist rejected all of them as failures --
# trading one false-success bug for a much larger false-FAILURE bug across
# most of the agent fleet.
#
# The FAILURE side is the one that is actually closed and enumerable: every
# entry below is authored directly by this gateway or by
# Governor.dispatch()'s own infrastructure-level failure paths (dispatch
# found no agents / no capable agent / timed out / rate-limited / a
# decomposed task partially completed / the handler declined or never ran)
# -- code this project owns and can keep exhaustive by inspection, unlike
# the open, agent-chosen success vocabulary. So: blacklist is correct here,
# not a whitelist -- but it must stay genuinely exhaustive against this
# gateway's OWN authored statuses (see core/city/governor.py:2567,2672,2712,
# 2379,2400 and this file's _execute_action's own branches), which is a
# realistic, bounded thing to keep complete.
TERMINAL_STATUSES = {
    "error", "failed", "not_implemented", "blocked",
    "no_agents", "no_capable_agent", "timeout", "partial", "rate_limited",
    "rejected", "executed_with_warnings",
    # 2026-09-23 round 3: home_control's own non-execution replies
    # (VoiceBridge.process() returning a parse failure or a pending
    # confirmation question, neither of which ran a real device action).
    "awaiting_confirmation",
    # 2026-09-23 round 4: core/loop/permission_gateway.py's own
    # _OWNER_READONLY_DISPATCH_ACTION_TYPES branch reports "unknown" for
    # git_status/check_git/git_log/recent_commits when the real handler's
    # raw dict carries no "status" key AND no real evidence of success
    # either (no "branch", no non-empty "commits") -- indistinguishable
    # from a real internal failure, per that handler's own docstring.
    "unknown",
}


def assess_payload_failure(payload: Any) -> str | None:
    """Explicit failure signals inside an otherwise "successful-looking" result payload, or None.

    Shared outcome assessment (V1 handoff 2026-09-13, "shared outcome-assessment slice"; built 2026-09-26). The status
    blacklist above only catches a handler that *says* it failed through `status`. Real agents also signal failure
    through other keys while leaving `status` at "ok"/"success" or absent -- a non-empty `error`, `success: false`,
    `ok: false`, `verified: false` -- and those used to be certified as executed (and verified) by every completion
    boundary that trusts this module. This stays conservative on purpose:

      * it only looks for an EXPLICIT negative signal; it never infers failure from a missing field, and it never
        treats a positive-looking flag (`verified: true`, `success: true`) as proof of anything -- an LLM-supplied
        "verified" is not evidence, real evidence is checked by plan verification (`result_field`);
      * `None`, `""`, `0`, `[]` and `False` values for `error` are "no error";
      * it does not touch nested payloads, only the top level of the handler's own result.

    Returns a short check name such as "error_field" (used as the `checks` entry and in the reason).
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is False:
        return "success_false"
    if payload.get("ok") is False:
        return "ok_false"
    if payload.get("verified") is False:
        return "verified_false"
    err = payload.get("error")
    if isinstance(err, (str, dict, list)) and len(err) > 0:
        return "error_field"
    return None


def result_failure_reason(payload: Any) -> str | None:
    """Why a gateway-APPROVED handler result must not be reported to the owner as done, or None if it looks like success.

    One definition for every owner-facing boundary (/command, /ws/command; the autonomous executor uses the same two
    checks inline). 2026-09-27: /command only checked a status blacklist and /ws/command only "error"/"not_implemented",
    so {"status": "ok", "error": "..."} and {"status": "no_agents"} were still reported as success (V1 contract 11/17).
    """
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if status in TERMINAL_STATUSES:
        return f"status:{status}"
    signal = assess_payload_failure(payload)
    return f"payload_signal:{signal}" if signal else None


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

        signal = assess_payload_failure(payload)
        if signal:
            return {
                "ok": False,
                "checks": checks + [f"result_status:{payload_status}", f"payload_signal:{signal}"],
                "message": (str(payload.get("error")) if signal == "error_field" else "")
                or payload.get("note")
                or f"Action result reported failure ({signal}) although its status was {payload_status}.",
            }

        checks.append(f"result_status:{payload_status}")
        return {
            "ok": True,
            "checks": checks,
            "message": "Action approved, executed, and verified.",
        }
