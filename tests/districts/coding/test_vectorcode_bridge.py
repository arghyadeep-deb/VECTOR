import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from unittest.mock import AsyncMock, patch

import pytest
import asyncio

from districts.coding.vectorcode_bridge import VectorCodeBridge


@pytest.fixture
def bridge():
    b = VectorCodeBridge()
    b._vc_available = True
    return b


@pytest.mark.asyncio
async def test_success_returns_ok(bridge):
    mock_run = AsyncMock(return_value=(b"task output", b"", 0))
    with patch.object(bridge, "_run_subprocess", mock_run):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "ok"
    assert result["output"] == "task output"
    assert result["exit_code"] == 0
    assert result["task"] == "Fix the bug"


@pytest.mark.asyncio
async def test_error_nonzero_exit(bridge):
    mock_run = AsyncMock(return_value=(b"", b"something failed", 1))
    with patch.object(bridge, "_run_subprocess", mock_run):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "error"
    assert "something failed" in result["output"]
    assert result["exit_code"] == 1
    assert result["task"] == "Fix the bug"


@pytest.mark.asyncio
async def test_timeout_returns_timeout_status(bridge):
    mock_run = AsyncMock(side_effect=asyncio.TimeoutError())
    with patch.object(bridge, "_run_subprocess", mock_run):
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
    result = await bridge.run_task(123)  # type: ignore

    assert result["status"] == "error"
    assert "Empty" in result["output"]
    assert result["exit_code"] == -1


@pytest.mark.asyncio
async def test_invalid_mode_defaults_to_run(bridge):
    mock_run = AsyncMock(return_value=(b"ok", b"", 0))
    with patch.object(bridge, "_run_subprocess", mock_run) as mock:
        await bridge.run_task("Fix the bug", mode="invalid")

    cmd = mock.call_args[0][0]
    assert "run" in cmd


@pytest.mark.asyncio
async def test_correct_command_structure(bridge):
    mock_run = AsyncMock(return_value=(b"ok", b"", 0))
    with patch.object(bridge, "_run_subprocess", mock_run) as mock:
        await bridge.run_task("Fix the bug", mode="auto")

    cmd = mock.call_args[0][0]
    assert len(cmd) == 4
    assert "auto" in cmd
    assert "Fix the bug" in cmd[-1]


@pytest.mark.asyncio
async def test_exception_during_run_returns_error(bridge):
    mock_run = AsyncMock(side_effect=RuntimeError("subprocess crashed"))
    with patch.object(bridge, "_run_subprocess", mock_run):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "error"
    assert "subprocess crashed" in result["output"]
    assert result["exit_code"] == -1


@pytest.mark.asyncio
@patch("core.memory.episodic.EpisodicMemory")
async def test_memory_failure_does_not_crash(mock_mem, bridge):
    mock_mem.return_value.store.side_effect = Exception("memory full")
    mock_run = AsyncMock(return_value=(b"output", b"", 0))
    with patch.object(bridge, "_run_subprocess", mock_run):
        result = await bridge.run_task("Fix the bug")

    assert result["status"] == "ok"
    assert result["output"] == "output"


@pytest.mark.asyncio
async def test_task_truncated_to_2000_chars(bridge):
    long_task = "a" * 3000
    mock_run = AsyncMock(return_value=(b"ok", b"", 0))
    with patch.object(bridge, "_run_subprocess", mock_run) as mock:
        await bridge.run_task(long_task)

    cmd = mock.call_args[0][0]
    assert len(cmd[-1]) == 2000


@pytest.mark.asyncio
async def test_null_bytes_stripped_from_task(bridge):
    mock_run = AsyncMock(return_value=(b"ok", b"", 0))
    with patch.object(bridge, "_run_subprocess", mock_run) as mock:
        await bridge.run_task("Fix \x00bug")

    cmd = mock.call_args[0][0]
    assert "\x00" not in cmd[-1]
    assert "Fix bug" in cmd[-1]
