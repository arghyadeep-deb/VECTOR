"""Regression for vectorcode/src/vc_mcp/transport.py's StdioTransport.close():

close() called proc.terminate() then proc.wait(timeout=5) with no handling
for subprocess.TimeoutExpired. A subprocess that ignores SIGTERM (common for
misbehaving MCP servers) made close() raise TimeoutExpired uncaught instead
of force-killing it, and left self._process referencing the dead transport
object rather than being cleared.
"""
from __future__ import annotations

import subprocess

import pytest

from vectorcode.src.vc_mcp.transport import StdioTransport


class _FakeProcess:
    def __init__(self, *, hangs: bool) -> None:
        self._hangs = hangs
        self.terminated = False
        self.killed = False
        self.stdin = None
        self.stdout = None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        if self._hangs and not self.killed:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout or 0)
        return 0


def _make_transport(proc: _FakeProcess) -> StdioTransport:
    transport = StdioTransport.__new__(StdioTransport)
    transport._command = ["fake"]
    transport._process = proc
    return transport


def test_close_kills_a_process_that_ignores_terminate() -> None:
    proc = _FakeProcess(hangs=True)
    transport = _make_transport(proc)

    transport.close()  # must not raise

    assert proc.terminated is True
    assert proc.killed is True


def test_close_clears_process_reference_on_clean_exit() -> None:
    proc = _FakeProcess(hangs=False)
    transport = _make_transport(proc)

    transport.close()

    assert transport._process is None
    assert proc.killed is False
