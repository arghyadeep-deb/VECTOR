"""The 'another loop is live' guard must ignore a heartbeat left by a DEAD process.

Found 2026-09-25 while restarting VECTOR: the API refuses to start its in-process brain
when the loop heartbeat is fresh and owned by another pid ("Running two brains doubles
Ollama/DB contention"). But a process killed a few seconds earlier leaves a still-fresh
heartbeat (10s window), so a restart inside that window logged
"NOT starting in-process brain -- another loop is already live in PID <the dead one>"
and VECTOR ran for minutes with an API and NO autonomous loop.
"""
import os
import subprocess
import sys

import pytest

from core.api import app as app_module


def _dead_pid() -> int:
    """A pid that verifiably belonged to a process that has exited."""
    import psutil

    # Windows recycles pids quickly, and under a busy full-suite run a freshly exited pid can be handed to a new process
    # before the assertion runs (seen once in the 2026-09-26 sharded run). Only accept a pid that is still free.
    for _ in range(20):
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        if not psutil.pid_exists(p.pid):
            return p.pid
    pytest.skip("could not obtain a pid that stays free")


def test_other_live_loop_is_reported():
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        rt = {"running": True, "pid": other.pid, "tick_count": 5}
        assert app_module._other_loop_pid(rt, os.getpid()) == other.pid
    finally:
        other.kill()
        other.wait()


def test_dead_owner_does_not_block_startup():
    rt = {"running": True, "pid": _dead_pid(), "tick_count": 5}
    assert app_module._other_loop_pid(rt, os.getpid()) is None


def test_own_pid_is_not_another_loop():
    rt = {"running": True, "pid": os.getpid(), "tick_count": 5}
    assert app_module._other_loop_pid(rt, os.getpid()) is None


@pytest.mark.parametrize("rt", [
    {"running": False, "pid": 4242, "tick_count": 0},
    {"running": True, "pid": None, "tick_count": 3},
    {},
])
def test_no_running_loop_means_no_other_loop(rt):
    assert app_module._other_loop_pid(rt, os.getpid()) is None
