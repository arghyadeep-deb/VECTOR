"""Regression test for a real, multi-round-review-confirmed architectural
gap: `Governor.dispatch()` (core/city/governor.py) accepted direct calls
for ANY task_type, including YELLOW/RED-tier ones (run_shell_command,
gui_task, hand_browser, ...), with zero PermissionGateway authorization
check at all. Over 100 direct call sites project-wide (API routers,
autonomous_loop.py, hands/runner.py, mcp_server_stdio.py) could reach a
real, dangerous district-agent capability with no owner approval, relying
only on whatever the CALLER's own layer happened to enforce.

Fixed at the single choke point every caller shares: `Governor.dispatch()`
itself now classifies `task_type` via the real, unmocked
`PermissionGateway._classify()` and, for YELLOW/RED, requires a real,
gateway-issued, one-shot approval receipt (the same mechanism
`grant_control()` already uses) before proceeding.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real classify()/receipt implementation directly.
`Governor.dispatch()` itself is also real and unmocked; only the eventual
district-agent `run()` call (reached after authorization passes) is
avoided by using a task_type this repo has no registered capability for,
so the test asserts on the authorization decision itself, not on a real
agent's side effect.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.city.governor import Governor
from core.loop.permission_gateway import PermissionGateway


@pytest.mark.asyncio
async def test_red_task_type_dispatched_directly_is_refused(isolated_vector_db):
    gw = PermissionGateway()
    assert gw._classify("run_shell_command") == "RED"

    result = await Governor().dispatch({
        "type": "run_shell_command",
        "params": {"command": "echo should never run"},
    })

    assert result.get("status") == "blocked", (
        "a RED-tier task_type dispatched directly to Governor with no "
        "real gateway approval must be refused -- this is the exact "
        "authorization-boundary gap a multi-round independent review "
        "found live"
    )
    assert "PermissionGateway" in result.get("reason", "")


@pytest.mark.asyncio
async def test_red_task_type_with_a_real_receipt_is_authorized(isolated_vector_db):
    """The legitimate pattern: PermissionGateway._execute_action() issues
    a receipt for the exact task_type it's about to dispatch, right
    before calling Governor.dispatch() itself (see its own hand_/
    _PLAN_COMPOSABLE_ACTION_TYPES/_OWNER_READONLY_DISPATCH_ACTION_TYPES
    branches). Prove that receipt is what actually authorizes it -- not
    a bypass, a genuine consumed proof."""
    gw = PermissionGateway()
    gw._issue_approval_receipt("run_shell_command", purpose="governor_dispatch")

    result = await Governor().dispatch({
        "type": "run_shell_command",
        "params": {"command": "echo ok"},
    })

    # Authorization passed (no "blocked" refusal) -- what happens next
    # (routing/agent dispatch) is a separate concern this test doesn't
    # need to exercise.
    assert result.get("status") != "blocked" or "PermissionGateway" not in result.get("reason", "")

    # The receipt must be one-shot -- a second direct dispatch without a
    # fresh receipt must be refused again.
    result2 = await Governor().dispatch({
        "type": "run_shell_command",
        "params": {"command": "echo should also never run"},
    })
    assert result2.get("status") == "blocked", (
        "a single approval receipt must not authorize more than one "
        "Governor.dispatch() call"
    )


@pytest.mark.asyncio
async def test_green_task_type_is_never_blocked(isolated_vector_db):
    """GREEN task types (the overwhelming majority of real dispatch
    traffic -- ~60+ API endpoints, every real Hand routing) must see zero
    behavior change -- no receipt needed, ever."""
    gw = PermissionGateway()
    assert gw._classify("play_music") == "GREEN"

    result = await Governor().dispatch({"type": "play_music", "params": {}})

    assert not (result.get("status") == "blocked" and "PermissionGateway" in result.get("reason", ""))


@pytest.mark.asyncio
async def test_unknown_task_type_is_never_blocked(isolated_vector_db):
    """The ~60 hardcoded, untiered API-router task types (budget_analyze,
    track_sleep, generate_docs, ...) audited this session must see zero
    behavior change -- this fix only refuses CONFIRMED YELLOW/RED types,
    never speculatively blocks unclassified ones."""
    gw = PermissionGateway()
    assert gw._classify("budget_analyze") == "UNKNOWN"

    result = await Governor().dispatch({"type": "budget_analyze", "params": {}})

    assert not (result.get("status") == "blocked" and "PermissionGateway" in result.get("reason", ""))


@pytest.mark.asyncio
async def test_grant_control_receipt_does_not_authorize_governor_dispatch(isolated_vector_db):
    """Round 4 (independent review finding -- HIGH): receipts are now
    scoped by (purpose, action_type), not action_type alone. A receipt
    issued for grant_control() must never authorize an unrelated
    Governor.dispatch() call for the same action_type, and vice versa --
    they serve genuinely different real approvals."""
    gw = PermissionGateway()
    gw._issue_approval_receipt("run_shell_command")  # default purpose="grant_control"

    result = await Governor().dispatch({
        "type": "run_shell_command",
        "params": {"command": "echo should never run"},
    })

    assert result.get("status") == "blocked", (
        "a grant_control-purpose receipt must not authorize "
        "Governor.dispatch() for the same action_type"
    )


@pytest.mark.asyncio
async def test_forbidden_task_type_is_always_blocked(isolated_vector_db):
    """Round 4 (independent review finding -- HIGH): the original check
    only gated YELLOW/RED, leaving FORBIDDEN task types to sail through
    Governor.dispatch() completely untouched."""
    gw = PermissionGateway()
    assert gw._classify("format_drive") == "FORBIDDEN"

    result = await Governor().dispatch({"type": "format_drive", "params": {}})

    assert result.get("status") == "blocked"
    assert "FORBIDDEN" in result.get("reason", "")


@pytest.mark.asyncio
async def test_web_task_alias_is_now_gated(isolated_vector_db):
    """Round 4 (independent review finding -- HIGH): "web_task" is a
    real, live alias GUIAutomationAgent treats identically to the
    already-RED "browser_task" (same capability, same district), but it
    was never classified anywhere, leaving it UNKNOWN and able to reach
    real browser automation completely unclassified. Now RED."""
    gw = PermissionGateway()
    assert gw._classify("web_task") == "RED", (
        "web_task must be classified the same as its sibling browser_task"
    )

    result = await Governor().dispatch({
        "type": "web_task",
        "params": {"action": "browser_task", "instruction": "should never run"},
    })

    assert result.get("status") == "blocked"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
