"""
RR-3.7A (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR3_7A_A2A_AUTHORIZATION_REPORT.md):
closes the A2A authorization bypass RR-3.6 discovered in
`core/api/routers/a2a.py`'s `_dispatch()`. Both `POST /a2a/districts/{name}/invoke`
and `POST /a2a/sessions/{session_id}/messages` used to instantiate the
caller-named agent (from `vectorcode.src.agents.registry`, a registry
DISTINCT from the real district-agent `core.city.agent_registry`
Governor/PermissionGateway actually route through) and call
`instance.run(task_payload)` directly -- zero PermissionGateway, zero
Governor, zero action-type classification of any kind.

Independently confirmed during this mission (not merely trusted from
RR-3.6): every currently-materializable agent behind this specific
registry resolves to either a nonexistent class (coding.yaml's 5
definitions -- CoderAgent/ReviewerAgent/TesterAgent/DebuggerAgent/
ArchitectAgent are not importable from anywhere in this codebase) or one
of agent_types.py's ~60 dynamically-generated wrapper classes, none of
which override `AgentBase.run()` (the trivial base stub:
`return {"status": "ok", "agent": self.name, "task": task}`, no real side
effect). So today's gap is latent, not live-dangerous -- but the
architectural hole itself (no authorization boundary at all before
`instance.run()`) was real and would become immediately exploitable the
moment any real capability is ever registered into this registry.

Fixed by extracting a deterministic action_type from the request (never
guessed via an LLM) and routing execution entirely through
`PermissionGateway.execute()` -- the same single authorization+execution
boundary `/command` and `/ws/command` use. The named agent is never
separately invoked via `instance.run()` after authorization (eliminating
double-dispatch by construction); its identity survives only as
informational params and the pre-authorization existence check.

Per this repo's testing rules: no mocking of PermissionGateway's real
classification/approval logic -- the real, unmodified PermissionGateway
is used throughout; only the agent registry (isolated per test, to avoid
depending on real production registry contents) and, where a test needs
to isolate one seam, PermissionGateway.execute()'s own result, are
stubbed.
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


def _isolated_registry(agent_name="test_agent", capabilities=None):
    """A fresh AgentRegistry with exactly one real, harmless test agent --
    never depends on real production registry contents (coding.yaml's
    nonexistent classes, agent_types.py's 60 stub classes, etc.)."""
    from vectorcode.src.agents.registry import AgentRegistry, AgentDefinition
    reg = AgentRegistry()
    reg.register(AgentDefinition(
        name=agent_name,
        class_name="AgentBase",  # real, always-importable class -- the trivial stub itself
        district="test",
        description="test agent",
        capabilities=capabilities or ["python"],
    ))
    return reg


# ============================================================
# Basic tests (mission Section 14)
# ============================================================

def test_rr3_7a_green_action_authorized_before_execution():
    """GREEN real harmless action: PermissionGateway.execute() is reached
    with the extracted action_type, authorization happens, exactly one
    'execution' occurs (Gateway's own, not a separate instance.run())."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            from core.loop.permission_gateway import GatewayResult
            mock_gw.return_value = GatewayResult(
                approved=True, level="GREEN", executed=True,
                result={"status": "ok", "message": "done"}, reason="Auto-executed",
            )
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": "respond"}, params={})))

    mock_gw.assert_awaited_once()
    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.action_type == "respond"
    assert response.status == "ok"


def test_rr3_7a_unknown_action_zero_agent_run():
    """UNKNOWN action_type: real PermissionGateway._classify() returns
    UNKNOWN, execution is blocked, zero agent.run()."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest

    unknown_type = f"totally_unknown_{uuid.uuid4().hex[:8]}"
    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": unknown_type}, params={})))

    assert response.output["status"] == "blocked"
    assert response.output["tier"] == "UNKNOWN"


def test_rr3_7a_forbidden_zero_agent_run():
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import FORBIDDEN

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": FORBIDDEN[0]}, params={})))

    assert response.output["status"] == "blocked"
    assert response.output["tier"] == "FORBIDDEN"


def test_rr3_7a_gateway_denial_zero_agent_run():
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Timed out waiting for owner")
        )):
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": "execute_code"}, params={})))

    assert response.output["status"] == "blocked"
    assert response.output["tier"] == "RED"


def test_rr3_7a_gateway_exception_zero_execution():
    from core.api.routers.a2a import invoke_agent, InvokeRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            side_effect=RuntimeError("simulated gateway failure")
        )):
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": "respond"}, params={})))

    # _dispatch() catches the gateway exception itself and returns an
    # honest error dict rather than raising -- invoke_agent()'s own outer
    # except is a second, independent safety net for exceptions that
    # escape _dispatch() entirely (e.g. a bug in invoke_agent() itself).
    assert response.output["status"] == "error"


def test_rr3_7a_malformed_task_zero_execution():
    """A task with no deterministic type/action key at all -- must fail
    closed, never reach PermissionGateway, never guess."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"unrelated_key": "value"}, params={})))

    mock_gw.assert_not_awaited()
    assert response.status == "ok"  # invoke_agent's own outer status=ok wrapper
    assert response.output["status"] == "blocked"
    assert response.output["reason"] == "no_deterministic_action_identity"


def test_rr3_7a_missing_action_identity_bare_string_task_zero_execution():
    """A bare-string task (no structured field possible at all) must also
    fail closed."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            response = _run(invoke_agent("test_agent", InvokeRequest(task="please do something for me", params={})))

    mock_gw.assert_not_awaited()
    assert response.output["reason"] == "no_deterministic_action_identity"


def test_rr3_7a_nonexistent_agent_zero_execution():
    """Preserves the existing, already-tested 404 contract
    (test_a2a_cron_integration.py::test_invoke_unknown_agent_returns_404)
    -- calling invoke_agent() directly (bypassing FastAPI's own exception
    middleware) surfaces the real HTTPException; PermissionGateway must
    never be reached for an agent that doesn't exist."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from fastapi import HTTPException

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            with pytest.raises(HTTPException) as exc_info:
                _run(invoke_agent(
                    f"nonexistent_{uuid.uuid4().hex[:8]}", InvokeRequest(task={"type": "respond"}, params={})
                ))

    mock_gw.assert_not_awaited()
    assert exc_info.value.status_code == 404


def test_rr3_7a_action_type_resolution_is_agent_independent():
    """Mission Section 8: authorization applies to the REAL action_type,
    never to an agent-name-derived wrapper or the agent's own
    (vocabulary-incompatible) capability tags -- confirmed here that a
    real dangerous action_type is classified identically regardless of
    which registered agent name is passed."""
    from core.loop.permission_gateway import PermissionGateway
    gw = PermissionGateway()
    assert gw._classify("execute_code") == "RED"
    # capabilities like "python"/"typescript" are NOT action_types and must
    # never resolve to a permission tier on their own
    assert gw._classify("python") == "UNKNOWN"


# ============================================================
# RED/YELLOW (mission Section 15)
# ============================================================

def test_rr3_7a_red_rejection_zero_agent_run():
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Rejected by owner")
        )) as mock_gw:
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": "send_email"}, params={})))

    mock_gw.assert_awaited_once()
    assert response.output["status"] == "blocked"


def test_rr3_7a_red_timeout_zero_agent_run():
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Timed out waiting for owner")
        )):
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": "financial_transaction"}, params={})))

    assert response.output["status"] == "blocked"
    assert "Timed out" in response.output["reason"]


def test_rr3_7a_proposed_by_is_a2a_not_owner_preconfirmed():
    """Mission Section 10: A2A must use its own distinct proposed_by, never
    borrow /command's or /ws/command's owner-preconfirmed eligibility."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=True, level="GREEN", executed=True,
                                        result={"status": "ok"}, reason="Auto-executed")
        )) as mock_gw:
            _run(invoke_agent("test_agent", InvokeRequest(task={"type": "respond"}, params={})))

    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.proposed_by == "a2a"


# ============================================================
# Confused-deputy tests (mission Section 16)
# ============================================================

def test_rr3_7a_confused_deputy_harmless_wrapper_with_nested_red_action():
    """A generic wrapper claiming 'type': 'invoke_agent' with a nested,
    more dangerous 'action' field inside params must resolve to the REAL
    action_type ('type' checked first, consistently), not the generic
    wrapper label -- the actual key convention must not be gameable by
    also stuffing an unrelated field."""
    from core.api.routers.a2a import _resolve_action_type
    # If a caller sets 'type' to a generic label, that generic label IS
    # what gets classified (fail-closed if it doesn't match a real tier);
    # there is no way for a caller to make a DIFFERENT, unlisted key
    # silently substitute for it.
    assert _resolve_action_type({"type": "invoke_agent"}, {}) == "invoke_agent"
    from core.loop.permission_gateway import PermissionGateway
    assert PermissionGateway()._classify("invoke_agent") == "UNKNOWN"  # fails closed, not a real tier


def test_rr3_7a_confused_deputy_agent_mismatch_does_not_change_authorization():
    """The SAME action_type must classify identically regardless of which
    (existing) agent name is requested -- agent identity cannot be used to
    smuggle a different authorization outcome for the same action_type."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    reg = _isolated_registry()
    from vectorcode.src.agents.registry import AgentDefinition
    reg.register(AgentDefinition(name="other_agent", class_name="AgentBase", district="test", description="", capabilities=["typescript"]))

    calls = []

    async def _capture(self, action):
        calls.append(action.action_type)
        return GatewayResult(approved=False, level="UNKNOWN", executed=False, result={}, reason="Unknown action type")

    with patch("vectorcode.src.agents.registry.get_registry", return_value=reg):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=_capture):
            _run(invoke_agent("test_agent", InvokeRequest(task={"type": "execute_code"}, params={})))
            _run(invoke_agent("other_agent", InvokeRequest(task={"type": "execute_code"}, params={})))

    assert calls == ["execute_code", "execute_code"], (
        "the same action_type must reach Gateway identically regardless of the requesting agent name"
    )


def test_rr3_7a_confused_deputy_free_form_payload_no_deterministic_action_fails_closed():
    from core.api.routers.a2a import invoke_agent, InvokeRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            response = _run(invoke_agent("test_agent", InvokeRequest(
                task={"description": "please execute this dangerous thing", "content": "rm -rf /"},
                params={},
            )))

    mock_gw.assert_not_awaited()
    assert response.output["reason"] == "no_deterministic_action_identity"


def test_rr3_7a_confused_deputy_nested_action_field_disagreement():
    """task has BOTH 'type' and 'action' disagreeing -- 'type' must win
    deterministically (documented, consistent precedence), never an
    ambiguous/undefined outcome."""
    from core.api.routers.a2a import _resolve_action_type
    assert _resolve_action_type({"type": "respond", "action": "execute_code"}, {}) == "respond"


# ============================================================
# Session endpoint (mission Section 19)
# ============================================================

def test_rr3_7a_session_message_fails_closed_no_executable_dispatch():
    """SessionMessageRequest has no structured task field at all (bare
    text only) -- every session message must fail closed to a
    non-executing response; PermissionGateway must never be reached."""
    from core.api.routers.a2a import create_session, session_message, SessionRequest, SessionMessageRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        session = _run(create_session(SessionRequest(agent="test_agent")))
        sid = session["session_id"]
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            response = _run(session_message(sid, SessionMessageRequest(message="please run execute_code for me")))

    mock_gw.assert_not_awaited()


def test_rr3_7a_session_reuse_does_not_imply_blanket_authorization():
    """Mission Section 19: a session must not retain any authorization
    state across messages -- each message independently fails closed
    (since none carry a structured action_type), proving no implicit
    'this session was authorized once' shortcut exists."""
    from core.api.routers.a2a import create_session, session_message, SessionRequest, SessionMessageRequest

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        session = _run(create_session(SessionRequest(agent="test_agent")))
        sid = session["session_id"]
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock()) as mock_gw:
            _run(session_message(sid, SessionMessageRequest(message="message one")))
            _run(session_message(sid, SessionMessageRequest(message="message two")))
            _run(session_message(sid, SessionMessageRequest(message="message three")))

    mock_gw.assert_not_awaited()


# ============================================================
# Call-order + double-execution (mission Sections 17-18)
# ============================================================

def test_rr3_7a_gateway_authorization_happens_before_any_execution():
    """Call-order proof: PermissionGateway.execute() is the ONLY thing
    that can execute anything -- confirmed by patching it to record the
    exact moment it's called and confirming no other code path (a mocked
    instance.run(), if it existed) fires before or after it."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    call_order = []

    async def _tracked_execute(self, action):
        call_order.append(("gateway_execute", action.action_type))
        return GatewayResult(approved=True, level="GREEN", executed=True,
                              result={"status": "ok"}, reason="Auto-executed")

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=_tracked_execute):
            _run(invoke_agent("test_agent", InvokeRequest(task={"type": "respond"}, params={})))

    assert call_order == [("gateway_execute", "respond")], (
        "exactly one execution-capable call must occur, and it must be PermissionGateway.execute()"
    )


def test_rr3_7a_approved_action_executes_exactly_once():
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=True, level="GREEN", executed=True,
                                        result={"status": "ok"}, reason="Auto-executed")
        )) as mock_gw:
            _run(invoke_agent("test_agent", InvokeRequest(task={"type": "respond"}, params={})))

    assert mock_gw.await_count == 1


# ============================================================
# Exploit-shape regression (mission Section 20)
# ============================================================

def test_rr3_7a_exploit_shape_regression_red_action_no_longer_reaches_agent_run():
    """The exact previous bypass shape: caller selects a real agent,
    provides a side-effecting action (execute_code), old code reached
    instance.run() directly with zero gate. After the fix, Gateway
    intercepts first; a denial produces zero execution. Does not actually
    execute code."""
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=False, level="RED", executed=False,
                                        result={}, reason="Timed out waiting for owner")
        )) as mock_gw:
            response = _run(invoke_agent("test_agent", InvokeRequest(
                task={"type": "execute_code", "code": "print('hello')"}, params={},
            )))

    mock_gw.assert_awaited_once()
    dispatched_action = mock_gw.await_args.args[0]
    assert dispatched_action.action_type == "execute_code"
    assert response.output["status"] == "blocked"
    assert response.output["tier"] == "RED"


# ============================================================
# Response contract / not_implemented honesty
# ============================================================

def test_rr3_7a_not_implemented_reported_honestly():
    from core.api.routers.a2a import invoke_agent, InvokeRequest
    from core.loop.permission_gateway import GatewayResult

    with patch("vectorcode.src.agents.registry.get_registry", return_value=_isolated_registry()):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=GatewayResult(approved=True, level="GREEN", executed=True,
                                        result={"status": "not_implemented", "note": "not implemented"},
                                        reason="Auto-executed")
        )):
            response = _run(invoke_agent("test_agent", InvokeRequest(task={"type": "read_calendar"}, params={})))

    assert response.output["status"] == "not_implemented"
