
import json
from unittest.mock import AsyncMock, patch

import pytest
import asyncio

from districts.coding.vectorcode_bridge import VectorCodeBridge


@pytest.fixture
def bridge():
    b = VectorCodeBridge()
    b._vc_available = True
    return b


def _mock_proc(stdout: bytes, retcode: int = 0):
    """Helper to create a mock async subprocess that returns given stdout/retcode."""
    p = AsyncMock()
    p.communicate.return_value = (stdout, b"")
    p.returncode = retcode
    return p


@pytest.mark.asyncio
async def test_success_returns_ok(bridge):
    expected = json.dumps({"status": "ok", "output": "task output", "exit_code": 0}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected)):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "ok"
    assert result["output"] == "task output"
    assert result["exit_code"] == 0
    assert result["task"] == "Fix the bug"


@pytest.mark.asyncio
async def test_error_nonzero_exit(bridge):
    expected = json.dumps({"status": "error", "output": "something failed", "exit_code": 1}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected, retcode=1)):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "error"
    assert "something failed" in result["output"]
    assert result["exit_code"] == 1


@pytest.mark.asyncio
async def test_timeout_returns_timeout_status(bridge):
    proc = AsyncMock()
    proc.communicate.side_effect = asyncio.TimeoutError()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=proc):
        result = await bridge.run_task("Fix the bug", timeout=10)

    assert result["status"] == "timeout"
    assert "timed out" in result["output"]
    assert result["exit_code"] == -1


@pytest.mark.asyncio
async def test_unavailable_when_vc_missing():
    bridge = VectorCodeBridge()
    bridge._vc_available = False
    result = await bridge.run_task("Fix the bug")

    assert result["status"] == "unavailable"
    assert result["exit_code"] == -1


@pytest.mark.asyncio
async def test_empty_task_returns_error(bridge):
    result = await bridge.run_task("")
    assert result["status"] == "error"
    assert "Empty" in result["output"]
    assert result["exit_code"] == -1
    assert result["task"] == ""


@pytest.mark.asyncio
async def test_non_string_task_returns_error(bridge):
    result = await bridge.run_task(123)
    assert result["status"] == "error"
    assert "Empty" in result["output"]
    assert result["exit_code"] == -1


@pytest.mark.asyncio
async def test_invalid_mode_defaults_to_run(bridge):
    expected = json.dumps({"status": "ok", "output": "ok", "exit_code": 0}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected)) as mock:
        await bridge.run_task("Fix the bug", mode="invalid")

    cmd = mock.call_args[0]
    assert "run" in cmd
    assert "--ipc" in cmd


@pytest.mark.asyncio
async def test_correct_command_structure(bridge):
    expected = json.dumps({"status": "ok", "output": "ok", "exit_code": 0}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected)) as mock:
        await bridge.run_task("Fix the bug", mode="auto")

    cmd = mock.call_args[0]
    assert cmd[0].endswith("python.exe")
    assert cmd[-1] == "--ipc"
    # payload should be valid JSON
    call_kwargs = mock.call_args[1]
    payload = call_kwargs["stdin"]


@pytest.mark.asyncio
async def test_exception_during_run_returns_error(bridge):
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               side_effect=RuntimeError("subprocess crashed")):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "error"
    assert "subprocess crashed" in result["output"]
    assert result["exit_code"] == -1


@pytest.mark.asyncio
@patch("core.memory.episodic.EpisodicMemory")
async def test_memory_failure_does_not_crash(mock_mem, bridge):
    mock_mem.return_value.store.side_effect = Exception("memory full")
    expected = json.dumps({"status": "ok", "output": "output", "exit_code": 0}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected)):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "ok"
    assert result["output"] == "output"


@pytest.mark.asyncio
async def test_long_task_not_truncated(bridge):
    long_task = "a" * 3000
    expected = json.dumps({"status": "ok", "output": "ok", "exit_code": 0}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected)):
        result = await bridge.run_task(long_task)

    assert len(result["task"]) == 3000  # no longer truncated


@pytest.mark.asyncio
async def test_null_bytes_stripped_from_task(bridge):
    expected = json.dumps({"status": "ok", "output": "ok", "exit_code": 0}).encode()
    with patch("districts.coding.vectorcode_bridge.asyncio.create_subprocess_exec",
               return_value=_mock_proc(expected)):
        result = await bridge.run_task("Fix \x00bug")

    assert "\x00" not in result["task"]
    assert "Fix bug" in result["task"]
