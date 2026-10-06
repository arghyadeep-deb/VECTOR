"""Regression for vectorcode/src/vc_security/subprocess_sandbox.py's
run_sandboxed(): when a process timed out AND survived being killed (e.g.
stuck in an uninterruptible syscall), proc.wait(timeout=5) raised a second,
uncaught subprocess.TimeoutExpired that propagated out of run_sandboxed()
entirely -- crashing the caller instead of returning a timed-out
SandboxResult like the function's own contract promises.
"""
from __future__ import annotations

import subprocess
from unittest import mock

from vectorcode.src.vc_security.subprocess_sandbox import run_sandboxed


def test_run_sandboxed_survives_a_process_that_outlives_the_kill(monkeypatch):
    fake_proc = mock.Mock()
    fake_proc.pid = 12345
    fake_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=30)
    fake_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)

    monkeypatch.setattr(
        "vectorcode.src.vc_security.subprocess_sandbox.subprocess.Popen",
        lambda *a, **k: fake_proc,
    )
    monkeypatch.setattr(
        "vectorcode.src.vc_security.subprocess_sandbox.kill_process_tree",
        lambda _pid: None,
    )

    result = run_sandboxed("sleep 999", timeout=0.01)

    assert result.timed_out is True
    assert result.killed is True
