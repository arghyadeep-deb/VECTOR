"""Regression for vectorcode/src/vc_tools/code_interpreter_docker.py:

execute()'s try/finally called container.remove(force=True) in the finally
block with no exception handling of its own. If container.wait(timeout=...)
raised a timeout (the container still running past the deadline) and the
subsequent cleanup container.remove(force=True) then also raised (daemon
busy, container already gone, etc.), the CLEANUP exception replaced the
original timeout exception -- the caller saw a confusing generic "Docker
execution error" instead of the correct "Execution timed out after N
seconds." message the except block is specifically designed to produce.

Fixed: the remove() call is now wrapped in its own try/except that logs and
swallows cleanup failures, letting the original exception from the try
block propagate to the outer except Exception as exc: handler unchanged.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_tools.code_interpreter_docker import DockerCodeInterpreterTool


class _FakeTimeoutError(Exception):
    def __str__(self) -> str:
        return "Read timed out."


def _install_fake_docker_module(monkeypatch, *, wait_side_effect, remove_side_effect=None):
    container = MagicMock()
    container.id = "fake-container-id"
    container.wait.side_effect = wait_side_effect
    container.logs.return_value = b""
    if remove_side_effect is not None:
        container.remove.side_effect = remove_side_effect

    client = MagicMock()
    client.containers.run.return_value = container

    fake_docker = types.ModuleType("docker")
    fake_docker.from_env = MagicMock(return_value=client)
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    return container


def test_wait_timeout_survives_cleanup_failure(monkeypatch):
    """The real timeout message must win even if cleanup itself raises."""
    _install_fake_docker_module(
        monkeypatch,
        wait_side_effect=_FakeTimeoutError(),
        remove_side_effect=RuntimeError("container already removed"),
    )

    tool = DockerCodeInterpreterTool(timeout=5)
    result = tool.execute(code="import time; time.sleep(100)")

    assert result.success is False
    assert "timed out after 5 seconds" in result.content
    assert "already removed" not in result.content


def test_wait_timeout_without_cleanup_failure_still_reports_timeout(monkeypatch):
    _install_fake_docker_module(monkeypatch, wait_side_effect=_FakeTimeoutError())

    tool = DockerCodeInterpreterTool(timeout=5)
    result = tool.execute(code="import time; time.sleep(100)")

    assert result.success is False
    assert "timed out after 5 seconds" in result.content


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
