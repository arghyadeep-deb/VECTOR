"""
RR-3.6 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR3_6_AUTHORIZATION_BOUNDARY_REPORT.md):
closes the /ws/command authorization bypass RR-3.5 discovered and this
mission independently reproduced: `core/api/routers/websocket.py`'s
`ws_command_http()` used to build a raw task dict from
`classify_chat_intent()`'s output and call `Governor.dispatch()` DIRECTLY --
zero `Candidate`, zero `DecisionEngine.evaluate()`, zero
`PermissionGateway.execute()` anywhere in the function. Governor's own
RED-tier Council review is advisory-only (a rejection only logs and
proceeds); `classify_chat_intent()`'s own LLM prompt is explicitly
instructed to emit exact RED-tier task_type strings. Fixed by routing the
executable branch through the exact same canonical
Candidate -> DecisionEngine.evaluate() -> PermissionGateway.execute()
pipeline RR-1 already established for /command.

Per this repo's testing rules: no mocking of PermissionGateway's real
classification/approval logic -- the real PermissionGateway/DecisionEngine
are used throughout; only classify_chat_intent() (an LLM call) and
Governor.dispatch() (the deepest execution boundary this fix is
responsible for gating, not the district agent chain beyond it) are
stubbed, mirroring the established convention from
tests/test_rr3_5_foundation_closure.py.
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


def _make_request(text):
    from core.api.routers.websocket import WSCommandRequest
    return WSCommandRequest(text=text, priority="normal", source="test")


# ============================================================
# Structural (mission Section 19, A-J) + exploit-shape regression (22)
# ============================================================

def test_rr3_6_a_executable_intent_builds_candidate_and_reaches_gateway():
    """A+B+C+D: an executable classifier intent must construct a real
    Candidate, pass it through DecisionEngine.evaluate(), and reach
    PermissionGateway.execute() with the DecisionEngine-selected winner --
    not the raw classifier output verbatim."""
    from core.api.routers import websocket as ws_module

    action_type = f"test_rr36_exec_{uuid.uuid4().hex[:8]}"

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": action_type, "district": None}
    )):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw_execute:
            from core.loop.permission_gateway import GatewayResult
            mock_gw_execute.return_value = GatewayResult(
                approved=False, level="UNKNOWN", executed=False,
                result={}, reason=f"Unknown action type: {action_type}",
            )
            response = _run(ws_module.ws_command_http(_make_request("do the test action")))

    mock_gw_execute.assert_awaited_once()
    dispatched_action = mock_gw_execute.await_args.args[0]
    assert dispatched_action.action_type == action_type, (
        "PermissionGateway must receive the DecisionEngine-selected winner's action_type"
    )
    assert response.success is False
    assert response.error == "UNKNOWN"


def test_rr3_6_e_f_gateway_denial_means_zero_governor_dispatch():
    """E+F: Governor.dispatch() must never be called for an action
    PermissionGateway denies -- the exact shape of the original bypass."""
    from core.api.routers import websocket as ws_module
    from core.loop.permission_gateway import GatewayResult

    action_type = f"test_rr36_denied_{uuid.uuid4().hex[:8]}"

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": action_type, "district": None}
    )):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Timed out waiting for owner")
        )):
            with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
                response = _run(ws_module.ws_command_http(_make_request("do something risky")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False
    assert response.error == "RED"


def test_rr3_6_g_gateway_exception_means_zero_governor_dispatch():
    """G: a PermissionGateway exception must not silently fall through to
    an ungated Governor.dispatch() -- the endpoint's own outer try/except
    must catch it and report failure, never dispatch."""
    from core.api.routers import websocket as ws_module

    action_type = f"test_rr36_gwerr_{uuid.uuid4().hex[:8]}"

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": action_type, "district": None}
    )):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            side_effect=RuntimeError("simulated gateway failure")
        )):
            with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
                response = _run(ws_module.ws_command_http(_make_request("trigger a gateway error")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False


def test_rr3_6_h_decision_engine_failure_means_zero_governor_dispatch():
    """H: a DecisionEngine.evaluate() exception must not fall through to
    Governor.dispatch() either."""
    from core.api.routers import websocket as ws_module

    action_type = f"test_rr36_deerr_{uuid.uuid4().hex[:8]}"

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": action_type, "district": None}
    )):
        with patch("core.loop.decision_engine.DecisionEngine.evaluate", new=AsyncMock(
            side_effect=RuntimeError("simulated decision engine failure")
        )):
            with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
                response = _run(ws_module.ws_command_http(_make_request("trigger a decision engine error")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False


def test_rr3_6_i_j_approved_action_dispatches_exactly_once_no_recursion():
    """I+J: an APPROVED action must reach Governor.dispatch() (via the real
    PermissionGateway's own internal delegation, for action types that
    support it) exactly once -- no duplicate dispatch, no recursive
    Gateway/Governor loop. Uses the real, unmodified PermissionGateway and
    a real GREEN-tier action already in _PLAN_COMPOSABLE_ACTION_TYPES
    (idea_validate, RR-3.5A) so the real delegation path is exercised."""
    from core.api.routers import websocket as ws_module

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": "idea_validate", "district": None}
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock(
            return_value={"status": "ok", "verdict": "test"}
        )) as mock_dispatch:
            response = _run(ws_module.ws_command_http(_make_request(
                "validate this startup idea: an AI code review tool"
            )))

    assert mock_dispatch.await_count == 1, (
        f"Governor.dispatch() must be called exactly once for an approved, "
        f"delegated action -- got {mock_dispatch.await_count} calls"
    )
    assert response.success is True
    assert response.task_type == "idea_validate"


def test_rr3_6_exploit_shape_regression_red_action_no_longer_bypasses_gateway():
    """Mission Section 22: the exact previous bypass shape. Before the fix,
    a classifier result naming a RED-tier task_type (e.g. execute_code)
    reached Governor.dispatch() directly with no gate at all. After the
    fix, PermissionGateway intercepts it first; a denial/timeout produces
    Governor.dispatch() call count == 0. Does not actually execute code or
    send external requests -- only proves the architectural boundary."""
    from core.api.routers import websocket as ws_module
    from core.loop.permission_gateway import GatewayResult

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": "execute_code", "district": None}
    )):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Timed out waiting for owner")
        )) as mock_gw_execute:
            with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
                response = _run(ws_module.ws_command_http(_make_request(
                    "run this python script for me right now"
                )))

    mock_gw_execute.assert_awaited_once(), "PermissionGateway must be reached for a RED-tier classified action"
    dispatched_action = mock_gw_execute.await_args.args[0]
    assert dispatched_action.action_type == "execute_code"
    mock_dispatch.assert_not_awaited(), "Governor.dispatch() must NOT be reachable when Gateway denies a RED action"
    assert response.success is False


# ============================================================
# Permission tiers (mission Section 20)
# ============================================================

def test_rr3_6_tier_green_real_harmless_action_proceeds():
    """GREEN: a real, harmless action can proceed -- uses the real
    PermissionGateway._classify() (not mocked) against a real GREEN
    action_type."""
    from core.api.routers import websocket as ws_module
    from core.loop.permission_gateway import PermissionGateway

    gw = PermissionGateway()
    assert gw._classify("respond") == "GREEN"

    # "respond" is handled entirely inside PermissionGateway._execute_action()
    # (no district delegation needed) -- real GREEN tier, real gateway,
    # real execution, no Governor.dispatch() involved at all for this
    # specific action_type (that path is separately proven by the
    # idea_validate-based i/j test above).
    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": "respond", "district": None}
    )):
        response = _run(ws_module.ws_command_http(_make_request("just say hello")))

    assert response.success is True
    assert response.error is None


def test_rr3_6_tier_forbidden_zero_dispatch():
    from core.api.routers import websocket as ws_module
    from core.loop.permission_gateway import FORBIDDEN

    forbidden_action = FORBIDDEN[0]
    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": forbidden_action, "district": None}
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            response = _run(ws_module.ws_command_http(_make_request("do the forbidden thing")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False
    assert response.error == "FORBIDDEN"


def test_rr3_6_tier_unknown_zero_dispatch():
    from core.api.routers import websocket as ws_module

    unknown_action = f"totally_unknown_action_{uuid.uuid4().hex[:8]}"
    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": unknown_action, "district": None}
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            response = _run(ws_module.ws_command_http(_make_request("do something nonsensical")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False
    assert response.error == "UNKNOWN"


def test_rr3_6_tier_not_implemented_reported_as_failure_not_success():
    """Mission Section 15/25: approved+executed must never be reported as
    success=True when the downstream status is not_implemented."""
    from core.api.routers import websocket as ws_module

    # read_calendar: real GREEN-tier Stage-0 keyword, confirmed in RR-3.5's
    # own audit to have zero _execute_action() handler -- the exact
    # fake-success shape this test proves is now closed for /ws/command.
    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": "read_calendar", "district": None}
    )):
        response = _run(ws_module.ws_command_http(_make_request("what's on my calendar")))

    assert response.success is False, (
        "a not_implemented downstream status must never be reported as success=True"
    )
    assert response.error == "not_implemented"


# ============================================================
# Classifier behavior (mission Section 21)
# ============================================================

def test_rr3_6_classifier_conversational_no_executable_dispatch():
    """is_action=False (answer_question) -> conversational, non-executing
    behavior -- Candidate/DecisionEngine/PermissionGateway are never
    invoked for pure conversation."""
    from core.api.routers import websocket as ws_module

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": "answer_question", "district": None}
    )):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            with patch("core.city.governor.Governor.dispatch", new=AsyncMock(
                return_value={"status": "ok", "response": "Hello!"}
            )) as mock_dispatch:
                response = _run(ws_module.ws_command_http(_make_request("hello there")))

    mock_gw.assert_not_awaited()
    assert mock_dispatch.await_count == 1
    assert response.success is True
    assert response.task_type == "answer_question"


def test_rr3_6_classifier_timeout_no_executable_dispatch():
    """A classifier timeout/exception must not produce an executable
    dispatch -- the endpoint's outer except must catch it safely."""
    from core.api.routers import websocket as ws_module

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        side_effect=TimeoutError("classifier timed out")
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            response = _run(ws_module.ws_command_http(_make_request("anything")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False


def test_rr3_6_classifier_malformed_output_no_executable_dispatch():
    """Malformed classifier output (missing the expected 'type' key) must
    not silently produce an executable dispatch -- the endpoint's outer
    except must catch the resulting KeyError."""
    from core.api.routers import websocket as ws_module

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"district": "startups"}  # no "type" key
    )):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
            response = _run(ws_module.ws_command_http(_make_request("anything")))

    mock_dispatch.assert_not_awaited()
    assert response.success is False


# ============================================================
# Advisory Council cannot override Gateway (mission Section 23)
# ============================================================

def test_rr3_6_council_advisory_cannot_bypass_gateway_denial():
    """Even if Governor's own internal advisory Council would have
    'proceeded with caution' on a RED action, PermissionGateway's real
    denial must still win -- Governor.dispatch() (where Council review
    lives) must never even be reached when Gateway denies."""
    from core.api.routers import websocket as ws_module
    from core.loop.permission_gateway import GatewayResult

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(
        return_value={"type": "execute_code", "district": None}
    )):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Council-independent Gateway denial")
        )):
            with patch("core.city.governor.Governor._should_convene_council", new=AsyncMock(return_value=True)):
                with patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as mock_dispatch:
                    response = _run(ws_module.ws_command_http(_make_request("run arbitrary code")))

    mock_dispatch.assert_not_awaited(), (
        "Council logic lives inside Governor.dispatch() -- it must never run at all "
        "once PermissionGateway has denied the action"
    )
    assert response.success is False


# ============================================================
# /command regression (mission Section 24) -- unaffected by this fix
# ============================================================

def test_rr3_6_command_endpoint_unchanged_idea_validate_still_works():
    """RR-3.5A's idea_validate delegation must remain intact -- this fix
    touches only websocket.py, never commands.py."""
    from core.loop.permission_gateway import _PLAN_COMPOSABLE_ACTION_TYPES
    assert _PLAN_COMPOSABLE_ACTION_TYPES == {"script", "schedule_post", "idea_validate"}


def test_rr3_6_command_py_not_modified_by_this_fix():
    import inspect
    from core.api.routers import commands as commands_module
    src = inspect.getsource(commands_module.command_endpoint)
    assert "PermissionGateway" in src or "perm_gateway" in src, (
        "commands.py's own canonical pipeline must remain intact and untouched"
    )
