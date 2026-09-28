"""Regression test for a real bug an independent review found:
`core/api/routers/control.py`'s `pc_screenshot`/`pc_click`/`pc_type`/
`pc_launch_app` endpoints had NO real execution path at all.
`PermissionGateway._execute_action()` had no dedicated branch for any of
these 4 action types (they fell through to the generic "executed" shape
with no real handler), and `_dispatch_pc_action()` then called
`Governor.dispatch({"type": action_type, ...})` as a SEPARATE, second
attempt -- but Governor has no DISTRICT_TASK_MAP entry or agent-manifest
capability for any of these exact task types either, and the task dict
never carried the "action" field GUIAutomationAgent's `run()` requires.
Net effect: these endpoints could return an error, an unrelated
fallback-agent result, or an apparent success with no real click/type/
launch/screenshot ever occurring.

Fix: PermissionGateway._execute_action() now has real, dedicated
branches for all four (mirroring the pre-existing launch_app/
run_shell_command pattern), calling PCController directly, and
_dispatch_pc_action() returns `gate.result` -- the REAL result -- instead
of discarding it and dispatching a second time.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real `execute()`/`_classify()`/`_execute_action()`
flow end to end. The only thing mocked is the underlying OS-level
pyautogui/subprocess calls inside PCController itself (never a
VECTOR-internal boundary), to avoid actually moving the mouse or opening
a real process during CI.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.permission_gateway import Action, PermissionGateway


@pytest.mark.asyncio
async def test_pc_screenshot_reports_ok_only_when_a_real_file_was_saved(tmp_path):
    """Round-3 regression: take_screenshot() returns np.zeros(...) -- a
    non-empty ndarray -- as its OWN internal failure fallback, so
    checking "is it a non-empty ndarray" can never distinguish that
    fallback from a genuine capture. This drives the real
    PCController().take_screenshot() (only mss itself is mocked, to
    avoid a real screen capture in CI) so the save path genuinely
    writes a real file, and asserts status="ok" only actually happens
    then."""
    gw = PermissionGateway()
    assert gw._classify("pc_screenshot") == "YELLOW"
    save_path = tmp_path / "shot.png"

    import numpy as np
    fake_monitor = {"top": 0, "left": 0, "width": 4, "height": 4}

    class _FakeShot:
        bgra = bytes([0, 0, 0, 255] * 16)
        height = 4
        width = 4

    class _FakeMSS:
        monitors = [None, fake_monitor]
        def grab(self, monitor):
            return _FakeShot()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    with patch("core.control.pc_controller._MSS_AVAILABLE", True), \
         patch("core.control.pc_controller.mss") as mock_mss_mod, \
         patch("core.control.pc_controller._PIL_AVAILABLE", True):
        mock_mss_mod.mss.return_value = _FakeMSS()
        result = await gw.execute(Action(
            action_type="pc_screenshot",
            params={"save_path": str(save_path)},
            proposed_by="api_command",
        ))

    assert result.approved and result.executed
    assert result.result.get("status") == "ok"
    assert save_path.exists() and save_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_pc_screenshot_reports_error_when_capture_fails(tmp_path):
    """The other half of the same fix: a genuine capture failure (mss
    unavailable) must report status="error", not a phantom "ok"."""
    gw = PermissionGateway()
    save_path = tmp_path / "never_written.png"

    with patch("core.control.pc_controller._MSS_AVAILABLE", False):
        result = await gw.execute(Action(
            action_type="pc_screenshot",
            params={"save_path": str(save_path)},
            proposed_by="api_command",
        ))

    assert result.approved and result.executed
    assert result.result.get("status") == "error", (
        "a real capture failure must never report 'ok' -- this is the "
        "exact phantom-success bug an independent review found"
    )
    assert not save_path.exists()


@pytest.mark.asyncio
async def test_pc_screenshot_does_not_report_ok_on_a_stale_pre_existing_file(tmp_path):
    """Round-3, second pass -- an independent review reproduced this exact
    variant: if `save_path` already holds an OLDER screenshot from a
    prior successful call, and THIS capture fails, take_screenshot()
    leaves that stale file completely untouched. A naive "does the file
    exist with content" check still passes on a genuine failure. Must
    capture-to-temp-then-atomic-replace so a failed capture can never
    ride on a stale file's existence."""
    gw = PermissionGateway()
    save_path = tmp_path / "shot.png"
    save_path.write_bytes(b"stale screenshot bytes from a prior real success")
    stale_content = save_path.read_bytes()

    with patch("core.control.pc_controller._MSS_AVAILABLE", False):
        result = await gw.execute(Action(
            action_type="pc_screenshot",
            params={"save_path": str(save_path)},
            proposed_by="api_command",
        ))

    assert result.approved and result.executed
    assert result.result.get("status") == "error", (
        "a failed capture must report 'error' even when a stale file "
        "already sits at save_path -- this is the exact stale-file "
        "variant an independent review reproduced against the round-3 "
        "first-pass fix"
    )
    assert save_path.read_bytes() == stale_content, (
        "the stale file must be left completely untouched by a failed "
        "capture attempt -- no partial/empty overwrite either"
    )
    # No leftover temp file from the failed atomic-replace attempt.
    assert [p for p in tmp_path.iterdir() if p.name != "shot.png"] == []


@pytest.mark.asyncio
async def test_pc_click_actually_calls_pyautogui_click():
    gw = PermissionGateway()
    assert gw._classify("pc_click") == "RED"

    with patch("core.control.pc_controller._PYAUTOGUI_AVAILABLE", True), \
         patch("core.control.pc_controller.pyautogui") as mock_pyautogui:
        # pc_click is in RED_INTERACTIVE_TOOLS -- proposed_by="api_command"
        # is the real, sanctioned owner-initiated fast path (matches how
        # the owner's own typed/spoken command reaches this same branch
        # in production; execute() itself decides GREEN/YELLOW/RED and
        # issues the approval receipt _execute_action() then consumes).
        result = await gw.execute(Action(
            action_type="pc_click",
            params={"x": 42, "y": 99, "button": "left"},
            proposed_by="api_command",
        ))

    assert result.approved and result.executed
    assert result.result.get("status") == "ok"
    mock_pyautogui.click.assert_called_once_with(42, 99, button="left")


@pytest.mark.asyncio
async def test_pc_type_actually_calls_pyautogui_typewrite():
    gw = PermissionGateway()

    with patch("core.control.pc_controller._PYAUTOGUI_AVAILABLE", True), \
         patch("core.control.pc_controller.pyautogui") as mock_pyautogui:
        result = await gw.execute(Action(
            action_type="pc_type",
            params={"text": "hello vector", "delay_ms": 10},
            proposed_by="api_command",
        ))

    assert result.approved and result.executed
    assert result.result.get("status") == "ok"
    mock_pyautogui.typewrite.assert_called_once_with("hello vector", interval=0.01)


@pytest.mark.asyncio
async def test_pc_launch_app_actually_calls_popen():
    gw = PermissionGateway()
    assert gw._classify("pc_launch_app") == "RED"

    from unittest.mock import MagicMock
    fake_proc = MagicMock(pid=12345)

    with patch("core.control.pc_controller.shutil.which", return_value="C:\\fake\\notepad.exe"), \
         patch("core.control.pc_controller.subprocess.Popen", return_value=fake_proc) as mock_popen:
        result = await gw.execute(Action(
            action_type="pc_launch_app",
            params={"app_name": "notepad", "args": ""},
            proposed_by="api_command",
        ))

    assert result.approved and result.executed
    assert result.result.get("launched") is True
    assert result.result.get("pid") == 12345
    mock_popen.assert_called_once()


@pytest.mark.asyncio
async def test_control_router_no_longer_double_dispatches_to_governor(monkeypatch):
    """The exact regression this fix closes at the API layer: the router
    must never call Governor.dispatch() a second time after a real
    gateway execution -- it must return the gateway's own real result."""
    from core.api.routers import control
    from core.city import governor

    async def dispatch_should_not_run(self, task):
        raise AssertionError("Governor.dispatch() must never run for pc_click")

    monkeypatch.setattr(governor.GovernorCouncil, "dispatch", dispatch_should_not_run)

    # _dispatch_pc_action() hardcodes proposed_by="api.control" (not an
    # owner-trust marker), so this goes through the REAL RED-tier
    # Pushover wait -- patch _wait_for_confirmation itself (the exact
    # thing that real wait blocks on) to simulate the owner tapping
    # Approve, matching the established pattern from
    # tests/test_regression_vc_action_no_double_execution.py.
    async def _auto_confirm(self, action, pending_id=None):
        return True
    monkeypatch.setattr(PermissionGateway, "_wait_for_confirmation", _auto_confirm)

    with patch("core.control.pc_controller._PYAUTOGUI_AVAILABLE", True), \
         patch("core.control.pc_controller.pyautogui"):
        response = await control.pc_click(control.PcClickReq(x=1, y=2))

    assert response["status"] == "ok"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
