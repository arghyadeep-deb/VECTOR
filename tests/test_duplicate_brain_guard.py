"""
Regression tests for the 2026-08-05 duplicate-autonomous-loop guard.

Measured live: an orphaned `python run_vector.py loop` process (PID 44684,
alive ~17h, started by nothing that manages it) was running concurrently
with the `run_vector.py api` process. Between them they held 90 simultaneous
ESTABLISHED connections to an Ollama backend configured
OLLAMA_MAX_LOADED_MODELS=1 — dozens of requests queued against a backend
that serves one at a time — plus two writers contending for the same
SQLCipher file and the same process-wide _write_lock.

This only became load-bearing once scripts/vector_watchdog.ps1 began setting
VECTOR_API_RUN_LOOP=1 (2026-08-04). Before that, a watchdog restart produced
an API with NO brain, so a stray `loop` process was the only brain and
nothing collided. After it, every watchdog restart would have started a
second brain alongside the orphan.

vector_autostart.bat's existing guard only checks "is port 8000 listening",
which by construction cannot detect a loop-only process — it never binds a
port. That is exactly how the orphan survived unnoticed.

The guard in core/api/app.py uses the heartbeat file's pid + 10s freshness
window. These tests pin the two halves that make it work:
  1. get_runtime() must actually report a pid (it did NOT before this fix —
     the guard would have read None and silently never fired, the same
     invisible no-op class as the restore_agent_hp bug).
  2. The pid must distinguish "running here" from "running elsewhere".
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.loop.loop_state as loop_state  # noqa: E402
from core.loop.loop_state import get_runtime  # noqa: E402


def test_get_runtime_reports_pid_when_running_in_this_process(monkeypatch):
    """The in-process branch must report OUR pid.

    Without this the app.py guard cannot tell self from other and would
    either never fire or refuse to start its own legitimate loop.
    """
    monkeypatch.setattr(loop_state, "_rt_running", True, raising=False)
    monkeypatch.setattr(loop_state, "_rt_tick_count", 42, raising=False)

    rt = get_runtime()
    assert rt["running"] is True
    assert rt["pid"] == os.getpid()


def test_get_runtime_reports_foreign_pid_from_heartbeat(monkeypatch):
    """The cross-process branch must surface the OTHER process's pid.

    This is the case that matters: the API process is starting up, its own
    in-memory state says "not running", but a live heartbeat from a separate
    loop process exists. The guard must see that foreign pid.
    """
    monkeypatch.setattr(loop_state, "_rt_running", False, raising=False)
    monkeypatch.setattr(
        loop_state,
        "_read_heartbeat",
        lambda: {"tick_count": 7, "running": True, "start_time": "t", "pid": 44684},
    )

    rt = get_runtime()
    assert rt["running"] is True
    assert rt["pid"] == 44684
    assert rt["pid"] != os.getpid(), "must be distinguishable from this process"


def test_guard_condition_fires_for_foreign_pid(monkeypatch):
    """The exact boolean core/api/app.py evaluates, for a foreign live loop."""
    monkeypatch.setattr(loop_state, "_rt_running", False, raising=False)
    monkeypatch.setattr(
        loop_state,
        "_read_heartbeat",
        lambda: {"tick_count": 1, "running": True, "start_time": "t", "pid": 44684},
    )

    rt = get_runtime()
    should_block = bool(rt.get("running") and rt.get("pid") and rt["pid"] != os.getpid())
    assert should_block is True


def test_guard_condition_does_not_fire_for_own_loop(monkeypatch):
    """Must NOT block when the only running loop is this process's own."""
    monkeypatch.setattr(loop_state, "_rt_running", True, raising=False)

    rt = get_runtime()
    should_block = bool(rt.get("running") and rt.get("pid") and rt["pid"] != os.getpid())
    assert should_block is False


def test_guard_condition_does_not_fire_when_no_loop_running(monkeypatch):
    """Clean start: nothing running anywhere => start normally."""
    monkeypatch.setattr(loop_state, "_rt_running", False, raising=False)
    monkeypatch.setattr(loop_state, "_read_heartbeat", lambda: None)

    rt = get_runtime()
    should_block = bool(rt.get("running") and rt.get("pid") and rt["pid"] != os.getpid())
    assert should_block is False


def test_stale_heartbeat_does_not_block_startup(monkeypatch):
    """A dead process's stale heartbeat must not permanently wedge startup.

    _read_heartbeat() already returns None for anything older than
    _HEARTBEAT_MAX_AGE_SEC; this pins that a stale file means "start
    normally" rather than "block forever", which would otherwise be a
    self-inflicted outage after any unclean loop exit.
    """
    monkeypatch.setattr(loop_state, "_rt_running", False, raising=False)
    monkeypatch.setattr(loop_state, "_read_heartbeat", lambda: None)  # stale => None

    rt = get_runtime()
    assert rt["running"] is False
    should_block = bool(rt.get("running") and rt.get("pid") and rt["pid"] != os.getpid())
    assert should_block is False
