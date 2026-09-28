"""
RR-3.7B (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md): closes three confirmed,
source-verified authorization gaps across the ~50 structured HTTP router
endpoints scoped by this mission (26 files under core/api/routers/ that call
Governor.dispatch() with a hardcoded literal action_type and no
PermissionGateway boundary):

1. POST /health/exercise -> "log_exercise" (YELLOW tier). Real handler
   districts/health/exercise_logger.py::ExerciseLogger.run() has an exact
   `task["type"]=="log_exercise"` branch -> real, persistent episodic-memory
   write. Router used to call Governor.dispatch() directly.
2. POST /projects/create -> "create_project" (YELLOW tier). Real handler
   districts/projects/project_planner.py::ProjectPlanner.run() has an exact
   `task["type"]=="create_project"` branch -> real episodic-memory write AND
   a real Obsidian note file write, caller-supplied name/goal/deadline
   flowing directly into file content. Router used to call
   Governor.dispatch() directly.
3. POST /learning/ingest-video -> "ingest_video" (never assigned a tier --
   UNKNOWN). Real handler districts/learning/video_ingestor.py::
   VideoIngestor.run() has NO task_type check at all -- it fires a real
   yt-dlp download of the caller-supplied URL for ANY task carrying a `url`
   param, whenever VideoIngestor wins the learning district's HP lottery.
   District resolution to "learning" is deterministic (DISTRICT_TASK_MAP
   "video" is an exact-key substring of "ingest_video"). Router used to call
   Governor.dispatch() directly.

All three are fixed identically: Candidate -> DecisionEngine.evaluate() ->
PermissionGateway.execute() first, proposed_by="structured_api"
(deliberately distinct from "api_command"/"voice" so none of these inherit
YELLOW pre-confirmation). log_exercise/create_project were added to
PermissionGateway._PLAN_COMPOSABLE_ACTION_TYPES (the same narrow,
individually-verified allowlist RR-3.5A/RR-3.6 already used) so a
Gateway-approved execution still reaches the real, already-correct
district-agent handler via Governor.dispatch() afterward. ingest_video was
deliberately NOT added -- it has no assigned tier, so PermissionGateway's
own fail-closed UNKNOWN-tier default denies it, which is the correct
security posture for an unreviewed external-fetch capability (mission
Section 6: never invent a tier just to keep something executing).

Per this repo's testing rules: no mocking of PermissionGateway's real
classification/approval logic -- the real PermissionGateway/DecisionEngine
run throughout; only Governor.dispatch() (the deepest execution boundary
these fixes are responsible for gating) is stubbed, mirroring
tests/test_rr3_6_authorization_boundary.py's established convention.
"""
import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _run(coro):
    return asyncio.run(coro)


# ============================================================
# Pre-fix exploit proof (mission Section 11) -- these three tests must FAIL
# against pre-fix HEAD (verified via git-stash below in this same session)
# ============================================================

def test_rr3_7b_exploit_log_exercise_must_reach_gateway_not_governor_directly():
    """Pre-fix, health.py::log_exercise called Governor.dispatch() directly
    with zero PermissionGateway involvement. Post-fix, PermissionGateway.execute()
    must be reached with the exact action_type, and it -- not the router --
    must be what decides whether Governor.dispatch() ever runs."""
    from core.api.routers import health as health_module

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
        from core.loop.permission_gateway import GatewayResult
        mock_gw.return_value = GatewayResult(
            approved=False, level="YELLOW", executed=False,
            result={}, reason="Rejected by owner",
        )
        body = health_module.LogExerciseReq(exercise_type="cardio", duration_min=20, intensity="high")
        response = _run(health_module.log_exercise(body))

    mock_gw.assert_awaited_once()
    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.action_type == "log_exercise"
    assert dispatched_action.proposed_by == "structured_api"
    assert response["status"] == "blocked"


def test_rr3_7b_exploit_create_project_must_reach_gateway_not_governor_directly():
    from core.api.routers import projects as projects_module

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
        from core.loop.permission_gateway import GatewayResult
        mock_gw.return_value = GatewayResult(
            approved=False, level="YELLOW", executed=False,
            result={}, reason="Rejected by owner",
        )
        body = projects_module.CreateProjectReq(name="Test Project", description="goal text", deadline="2026-12-01")
        response = _run(projects_module.create_project(body))

    mock_gw.assert_awaited_once()
    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.action_type == "create_project"
    assert dispatched_action.proposed_by == "structured_api"
    assert response["status"] == "blocked"


def test_rr3_7b_exploit_ingest_video_must_reach_gateway_not_governor_directly():
    from core.api.routers import learning as learning_module

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
        from core.loop.permission_gateway import GatewayResult
        mock_gw.return_value = GatewayResult(
            approved=False, level="UNKNOWN", executed=False,
            result={}, reason="Unknown action type: ingest_video",
        )
        body = learning_module.IngestVideoReq(url="https://example.com/video", language="en")
        response = _run(learning_module.ingest_video(body))

    mock_gw.assert_awaited_once()
    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.action_type == "ingest_video"
    assert dispatched_action.proposed_by == "structured_api"
    assert response["status"] == "blocked"


# ============================================================
# Authorization + double-execution (mission Section 12)
# ============================================================

def test_rr3_7b_log_exercise_denial_means_zero_governor_dispatch():
    """A YELLOW denial must never reach Governor.dispatch() -- the exact
    shape of the original bypass. PermissionGateway.execute() is mocked to
    return a denial (matching tests/test_rr3_6_authorization_boundary.py's
    established convention -- patching PermissionGateway's internal
    _wait_for_confirmation() instead hits a real, permanent test-shim in
    permission_gateway.py's YELLOW branch, `hasattr(self._wait_for_confirmation,
    "mock_calls")`, that force-confirms any Mock object regardless of its
    return value -- it exists to let unrelated tests exercise the YELLOW
    path without needing to mock confirmation at all, not to support
    simulating a denial via a mocked confirmation result)."""
    from core.api.routers import health as health_module
    from core.loop.permission_gateway import GatewayResult

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
        return_value=GatewayResult(approved=False, level="YELLOW", executed=False,
                                    result={}, reason="Rejected by owner")
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            body = health_module.LogExerciseReq()
            response = _run(health_module.log_exercise(body))

    mock_dispatch.assert_not_awaited()
    assert response["status"] == "blocked"


def test_rr3_7b_create_project_denial_means_zero_governor_dispatch():
    from core.api.routers import projects as projects_module
    from core.loop.permission_gateway import GatewayResult

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
        return_value=GatewayResult(approved=False, level="YELLOW", executed=False,
                                    result={}, reason="Rejected by owner")
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            body = projects_module.CreateProjectReq(name="X", description="Y", deadline="2026-12-01")
            response = _run(projects_module.create_project(body))

    mock_dispatch.assert_not_awaited()
    assert response["status"] == "blocked"


def test_rr3_7b_ingest_video_unknown_tier_zero_governor_dispatch():
    """ingest_video has no assigned tier -- real PermissionGateway._classify()
    must return UNKNOWN and deny immediately, with zero owner-confirmation
    wait (matches the real fail-closed UNKNOWN branch, not a YELLOW path)."""
    from core.api.routers import learning as learning_module
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()
    assert gw._classify("ingest_video") == "UNKNOWN"

    with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
        body = learning_module.IngestVideoReq(url="https://example.com/video")
        response = _run(learning_module.ingest_video(body))

    mock_dispatch.assert_not_awaited()
    assert response["status"] == "blocked"
    assert response["level"] == "UNKNOWN"


def test_rr3_7b_log_exercise_approved_dispatches_exactly_once():
    """An approved log_exercise must reach the real district handler exactly
    once via the _PLAN_COMPOSABLE_ACTION_TYPES delegation seam -- no double
    execution."""
    from core.api.routers import health as health_module

    with patch("core.loop.permission_gateway.PermissionGateway._wait_for_confirmation", new=AsyncMock(return_value=True)):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock(
            return_value={"status": "ok"}
        )) as mock_dispatch:
            body = health_module.LogExerciseReq(exercise_type="run", duration_min=25)
            response = _run(health_module.log_exercise(body))

    assert mock_dispatch.await_count == 1, (
        f"Governor.dispatch() must be called exactly once for an approved, "
        f"delegated action -- got {mock_dispatch.await_count} calls"
    )
    dispatched_task = mock_dispatch.await_args.args[0]
    assert dispatched_task["type"] == "log_exercise"
    assert response["status"] == "ok"


def test_rr3_7b_create_project_approved_dispatches_exactly_once():
    from core.api.routers import projects as projects_module

    with patch("core.loop.permission_gateway.PermissionGateway._wait_for_confirmation", new=AsyncMock(return_value=True)):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock(
            return_value={"status": "ok", "id": "abc123"}
        )) as mock_dispatch:
            body = projects_module.CreateProjectReq(name="Real Project", description="goal", deadline="2026-12-01")
            response = _run(projects_module.create_project(body))

    assert mock_dispatch.await_count == 1
    dispatched_task = mock_dispatch.await_args.args[0]
    assert dispatched_task["type"] == "create_project"
    assert response["status"] == "ok"


def test_rr3_7b_gateway_exception_means_zero_governor_dispatch():
    """A PermissionGateway exception must produce an honest error, not a
    silent fallback to ungated Governor.dispatch()."""
    from core.api.routers import health as health_module
    from fastapi import HTTPException

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
        side_effect=RuntimeError("gateway crashed")
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            body = health_module.LogExerciseReq()
            with pytest.raises(HTTPException):
                _run(health_module.log_exercise(body))

    mock_dispatch.assert_not_awaited()


def test_rr3_7b_not_implemented_reported_as_failure_not_success():
    """Mission Section 12: approved+executed must never be reported as a
    bare success when the downstream status is not_implemented."""
    from core.api.routers import health as health_module

    with patch("core.loop.permission_gateway.PermissionGateway._wait_for_confirmation", new=AsyncMock(return_value=True)):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock(
            return_value={"status": "not_implemented", "note": "stub"}
        )):
            body = health_module.LogExerciseReq()
            response = _run(health_module.log_exercise(body))

    assert response["status"] == "not_implemented"


# ============================================================
# Confused deputy (mission Section 9)
# ============================================================

def test_rr3_7b_confused_deputy_extra_body_fields_cannot_change_action_type():
    """Pydantic v2's default extra="ignore" must silently drop any
    caller-supplied "type"/"action" field inside the request body -- the
    dispatched action_type must always be the router's own hardcoded
    literal, never caller-influenced."""
    from core.api.routers import health as health_module

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
        from core.loop.permission_gateway import GatewayResult
        mock_gw.return_value = GatewayResult(approved=False, level="YELLOW", executed=False, result={}, reason="x")
        # Attempt to smuggle a different action_type via extra fields.
        body = health_module.LogExerciseReq.model_validate({
            "exercise_type": "cardio", "duration_min": 20,
            "type": "push_github", "action": "delete_files",
        })
        _run(health_module.log_exercise(body))

    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.action_type == "log_exercise", (
        "caller-supplied type/action fields must never influence the "
        "authorized action_type"
    )


# ============================================================
# Existing safe endpoints unchanged (mission Section 12)
# ============================================================

def test_rr3_7b_check_fatigue_unchanged_no_gateway_involved():
    """check_fatigue is GREEN-tier, S1, and was never part of this fix --
    it must continue to call Governor.dispatch() directly, unchanged."""
    from core.api.routers import health as health_module

    with patch("core.city.governor.GovernorCouncil.dispatch", new=AsyncMock(
        return_value={"status": "ok", "fatigue_score": 0.1}
    )) as mock_dispatch:
        response = _run(health_module.check_fatigue())

    assert mock_dispatch.await_count == 1
    assert mock_dispatch.await_args.args[0]["type"] == "check_fatigue"
    assert response["status"] == "ok"


def test_rr3_7b_track_experiment_unchanged_no_gateway_involved():
    """projects.py's track_experiment (S3, unclassified, low-risk local
    bookkeeping) was intentionally left untouched by this mission."""
    from core.api.routers import projects as projects_module

    with patch("core.city.governor.GovernorCouncil.dispatch", new=AsyncMock(
        return_value={"status": "ok"}
    )) as mock_dispatch:
        body = projects_module.TrackExperimentReq(name="exp1", hypothesis="h", result="r")
        response = _run(projects_module.track_experiment(body))

    assert mock_dispatch.await_count == 1
    assert mock_dispatch.await_args.args[0]["type"] == "track_experiment"


def test_rr3_7b_list_projects_unchanged_no_dispatch_at_all():
    """list_projects (S0, read-only, direct file read) is not Governor-
    mediated at all and must remain untouched."""
    from core.api.routers import projects as projects_module
    import inspect
    src = inspect.getsource(projects_module.list_projects)
    assert "Governor" not in src and "dispatch" not in src


# ============================================================
# District routing determinism (discovered via live production validation,
# mission Section 14 -- not merely predicted, reproduced against the real,
# running server: log_exercise had no DISTRICT_TASK_MAP entry, so even
# after correct YELLOW authorization it nondeterministically misrouted to
# "learning" instead of "health" via _llm_classify(), where the wrong
# agent (CourseTracker) ran with no real capability match)
# ============================================================

def test_rr3_7b_log_exercise_routes_deterministically_to_health():
    from core.city.governor import DISTRICT_TASK_MAP, Governor
    assert DISTRICT_TASK_MAP.get("log_exercise") == "health"
    assert Governor().route_task("log_exercise") == "health"


def test_rr3_7b_create_project_routes_deterministically_to_projects():
    """create_project was already deterministic before this mission -- the
    existing "project" substring key (DISTRICT_TASK_MAP) already matches
    it -- verified here as a sanity control, no DISTRICT_TASK_MAP change
    was needed or made for this one."""
    from core.city.governor import Governor
    assert Governor().route_task("create_project") == "projects"


def test_rr3_7b_exercise_logger_declares_log_exercise_capability():
    """Governor.dispatch()'s agent selection is an EXACT match on
    `task_type in agent.capabilities` -- without this, correct district
    routing alone still leaves the actual executing agent to an HP-lottery
    among health-district agents (confirmed live in production: picked
    FatigueMonitor, a harmless read-only agent this time, instead of the
    real ExerciseLogger.log_session() write)."""
    from districts.health.exercise_logger import ExerciseLogger
    assert "log_exercise" in ExerciseLogger().capabilities


def test_rr3_7b_project_planner_declares_create_project_capability():
    from districts.projects.project_planner import ProjectPlanner
    assert "create_project" in ProjectPlanner().capabilities


# ============================================================
# _PLAN_COMPOSABLE_ACTION_TYPES allowlist shape (mission Section 8)
# ============================================================

def test_rr3_7b_composable_allowlist_grew_by_exactly_two_new_entries():
    from core.loop.permission_gateway import _PLAN_COMPOSABLE_ACTION_TYPES
    # RR-3.7B itself added the two entries above; "web_extract" (GREEN, read-only page extraction) was added on 2026-09-26
    # and is deliberately a member of the exact snapshot so any further growth still has to touch this test.
    assert _PLAN_COMPOSABLE_ACTION_TYPES == {
        "script", "schedule_post", "idea_validate",
        "log_exercise", "create_project", "web_extract",
    }
    assert "ingest_video" not in _PLAN_COMPOSABLE_ACTION_TYPES, (
        "ingest_video must NOT be added -- it has no assigned permission "
        "tier and must fail closed via UNKNOWN, not be given a fabricated tier"
    )


def test_rr3_7b_no_red_action_in_composable_allowlist():
    from core.loop.permission_gateway import _PLAN_COMPOSABLE_ACTION_TYPES
    from core.config import CONFIG
    for red_action in CONFIG["permission"]["red"]:
        assert red_action not in _PLAN_COMPOSABLE_ACTION_TYPES


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], cwd=str(Path(__file__).parent.parent))
    print("OK test_rr3_7b_structured_router_authorization.py" if result.returncode == 0 else "FAILED")
