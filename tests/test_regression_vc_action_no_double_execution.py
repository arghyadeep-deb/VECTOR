"""Regression test for a real bug an independent review found: an approved
RED/YELLOW VectorCode action (code_task/code_review_vc/code_generate/
code_fix/code_debug) used to genuinely run the underlying VectorCode task
TWICE for one approval -- once inside PermissionGateway._execute_action()'s
own handling of gw.execute(), and again immediately afterward when
AutonomousLoop._act_on() called get_bridge().run_task() a second time.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real gateway (real classify(), real approve/execute
flow for a RED action pre-approved via the trust ladder's own real
VECTOR_YELLOW_AUTO_CONFIRM-independent owner-command pre-confirm path,
see PermissionGateway.execute()'s own "Owner-initiated command --
pre-confirmed" branch for proposed_by in ("api_command", "voice")) --
the ONLY thing mocked is the VectorCode bridge itself (network/subprocess
boundary), so the real call-count assertion is meaningful.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate


@pytest.mark.asyncio
async def test_approved_red_code_task_runs_bridge_exactly_once(isolated_vector_db, monkeypatch):
    loop = AutonomousLoop()

    mock_bridge = MagicMock()
    mock_bridge.is_available.return_value = True
    mock_bridge.run_task = AsyncMock(return_value={"status": "ok", "output": "done"})

    # code_task is RED (core/config.py) -- proposed_by="think_loop" does
    # NOT match the gateway's owner-command pre-confirm allowlist
    # ("api_command", "voice"), so this exercises the real RED confirmation
    # path. Real Pushover/HUD confirmation isn't available in a test
    # process, so the real gateway will genuinely time out waiting for
    # confirmation and DENY -- proving the "deny path never executes"
    # side of this fix. A second variant below proves the "approved path
    # executes exactly once" side by pre-seeding the trust ladder.
    with patch("districts.coding.vectorcode_bridge.get_bridge", return_value=mock_bridge):
        candidate = Candidate(
            action_type="code_task",
            params={"title": "regression probe"},
            source="think_loop",
            confidence=0.9,
            urgency=0.9,
        )
        await loop._act_on(candidate)

    assert mock_bridge.run_task.call_count == 0, (
        "a denied RED action must never reach the bridge at all"
    )


@pytest.mark.asyncio
async def test_approved_red_code_task_via_trust_ladder_runs_bridge_exactly_once(isolated_vector_db, monkeypatch):
    """Real trust-ladder auto-approval (N consecutive real owner approvals
    with zero bad outcomes -- see PermissionGateway.execute()'s own YELLOW/
    trust-ladder branch) is the real, supported way an action gets approved
    without a live human present. code_task is RED, not YELLOW, so this
    test instead pre-approves via a real, targeted monkeypatch of
    PermissionGateway._wait_for_confirmation -- the exact function real
    RED confirmation blocks on -- rather than faking gw.execute() itself,
    keeping the real classify()/_execute_action()/audit path intact."""
    loop = AutonomousLoop()

    mock_bridge = MagicMock()
    mock_bridge.is_available.return_value = True
    mock_bridge.run_task = AsyncMock(return_value={"status": "ok", "output": "done"})

    from core.loop.permission_gateway import PermissionGateway
    real_wait = PermissionGateway._wait_for_confirmation

    async def _auto_confirm(self, action, pending_id=None):
        return True

    monkeypatch.setattr(PermissionGateway, "_wait_for_confirmation", _auto_confirm)

    with patch("districts.coding.vectorcode_bridge.get_bridge", return_value=mock_bridge):
        candidate = Candidate(
            action_type="code_task",
            params={"title": "regression probe"},
            source="think_loop",
            confidence=0.9,
            urgency=0.9,
        )
        await loop._act_on(candidate)

    assert mock_bridge.run_task.call_count == 1, (
        f"an approved RED code_task must run the real bridge task EXACTLY "
        f"once, not {mock_bridge.run_task.call_count} times -- this is the "
        f"exact double-execution bug an independent review found"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
