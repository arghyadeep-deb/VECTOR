"""Fault-injection regressions for VECTOR's safety-critical execution gates."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
@pytest.mark.parametrize("action_type", ["commit_code", "execute_code"])
async def test_gateway_exception_in_api_caller_never_dispatches(action_type: str) -> None:
    """A real caller must not route around a failed YELLOW/RED gateway."""
    from core.api.routers import websocket as websocket_module
    from core.api.routers.websocket import WSCommandRequest

    request = WSCommandRequest(text="perform risky operation", priority="normal", source="test")
    with patch(
        "core.city.governor.classify_chat_intent",
        new=AsyncMock(return_value={"type": action_type, "district": None}),
    ), patch(
        "core.loop.permission_gateway.PermissionGateway.execute",
        new=AsyncMock(side_effect=RuntimeError("gateway unavailable")),
    ), patch("core.city.governor.Governor.dispatch", new=AsyncMock()) as dispatch:
        response = await websocket_module.ws_command_http(request)

    dispatch.assert_not_awaited()
    assert response.success is False


@pytest.mark.asyncio
async def test_unknown_and_malformed_action_types_are_blocked() -> None:
    from core.loop.permission_gateway import Action, PermissionGateway

    gateway = PermissionGateway()
    assert gateway.classify("not_registered_anywhere") == "UNKNOWN"
    assert gateway.classify("") == "UNKNOWN"
    assert gateway.classify(None) == "UNKNOWN"

    result = await gateway.execute(Action("not_registered_anywhere", {}, "fault_test"))
    assert result.approved is False
    assert result.executed is False
    assert result.level == "UNKNOWN"


def _red_candidate():
    from core.loop.decision_engine import Candidate

    return Candidate(
        action_type="delete_files",
        params={"path": "never-execute"},
        confidence=0.9,
        urgency=0.9,
        source="think_loop",
    )


def _isolated_soft_gate(red_team) -> object:
    from core.loop.autonomous_loop import AutonomousLoop

    loop = object.__new__(AutonomousLoop)
    loop._get_red_team = lambda: red_team
    loop._scan_threats = lambda *_args, **_kwargs: False
    loop._record_external_rejection = MagicMock()
    return loop


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        asyncio.TimeoutError("red-team timeout"),
        RuntimeError("red-team crashed"),
        {"verdict": "indeterminate", "reason": "no parseable verdict"},
    ],
    ids=["timeout", "exception", "unparseable"],
)
async def test_autonomous_red_team_faults_block_red_action(monkeypatch, fault) -> None:
    import core.memory.counterfactual as counterfactual_module

    monkeypatch.setattr(
        counterfactual_module.CounterfactualMemory,
        "should_avoid",
        lambda _self, _proposal, threshold: (False, 0.0, ""),
    )
    reviewer = MagicMock()
    if isinstance(fault, BaseException):
        reviewer.attack_plan = AsyncMock(side_effect=fault)
    else:
        reviewer.attack_plan = AsyncMock(return_value=fault)
    loop = _isolated_soft_gate(reviewer)

    allowed = await loop._run_soft_safety_checks(_red_candidate())

    assert allowed is False
    loop._record_external_rejection.assert_called_once()


def test_unparseable_red_team_model_response_is_blocked_by_agent() -> None:
    from core.brain.red_team_agent import _parse_verdict

    assert _parse_verdict("The review ended without a decision token.") == "BLOCKED"


def test_empty_mount_allowlist_refuses_every_mount(tmp_path: Path) -> None:
    from core.sandbox.mount_security import MountAllowlist, validate_mounts

    candidate = tmp_path / "workspace"
    candidate.mkdir()
    with pytest.raises(ValueError, match="not under any allowed root"):
        validate_mounts([str(candidate)], MountAllowlist())


@pytest.mark.parametrize("fault", ["missing", "corrupt", "unreadable"])
def test_container_runner_refuses_mounts_when_allowlist_initialization_fails(
    tmp_path: Path, fault: str, monkeypatch
) -> None:
    from core.sandbox.runner import ContainerRunner

    allowlist = tmp_path / "mount-allowlist.json"
    if fault == "corrupt":
        allowlist.write_text("{not-json", encoding="utf-8")
    elif fault == "unreadable":
        allowlist.write_text("{}", encoding="utf-8")
        original_read_text = Path.read_text

        def denied(path, *args, **kwargs):
            if path == allowlist:
                raise PermissionError("simulated unreadable allowlist")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)

    with pytest.raises((FileNotFoundError, PermissionError, ValueError)):
        ContainerRunner(mount_allowlist_path=str(allowlist))


@pytest.mark.asyncio
async def test_autonomous_loop_blocks_yellow_action_when_gateway_is_unavailable(monkeypatch) -> None:
    """Regression for the genuine autonomous-loop direct-dispatch bypass."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from vectorcode.src.skills.manager import SkillManager

    loop = object.__new__(AutonomousLoop)
    loop._active_task_count = 0
    loop._current_action_type = ""
    loop._publish_event = AsyncMock()
    loop._run_soft_safety_checks = AsyncMock(return_value=True)
    loop._get_gateway = lambda: None
    governor = MagicMock()
    governor.dispatch = AsyncMock(return_value={"status": "ok"})
    loop._get_governor = lambda: governor
    monkeypatch.setattr(SkillManager, "match", lambda *_args, **_kwargs: [])

    winner = Candidate(
        action_type="commit_code",
        params={"message": "must not commit"},
        source="think_loop",
    )
    await loop._act_on(winner)

    governor.dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_audit_failure_blocks_action_before_handler_runs(monkeypatch) -> None:
    from core.loop.permission_gateway import Action, PermissionGateway

    gateway = PermissionGateway()
    handler = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(gateway, "_execute_action", handler)
    monkeypatch.setattr(gateway, "_persist_audit", lambda _entry: False)

    result = await gateway.execute(Action("respond", {"text": "hello"}, "fault_test"))

    handler.assert_not_awaited()
    assert result.approved is False
    assert result.executed is False
    assert "audit trail unavailable" in result.reason


def test_live_auto_commit_hook_does_not_stage_secret_file(tmp_path: Path) -> None:
    """The live .claude hook must not bypass secret checks via auto-commit."""
    hooks_dir = Path(__file__).parent.parent / ".claude" / "hooks"
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Safety Test"], cwd=tmp_path, check=True)
    (tmp_path / ".env").write_text("API_KEY=must-not-commit\n", encoding="utf-8")

    hook = subprocess.run(
        [sys.executable, str(hooks_dir / "auto_commit.py")],
        input=json.dumps({"file_path": ".env"}),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    assert hook.returncode == 0
    assert ".env" not in staged.stdout.splitlines()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
