"""/status must report the real loop state, the same one /health uses.

Found 2026-09-25: with the autonomous loop ticking (/health: loop ok, tick 76),
/status still said `loop_running: false` because `_get_loop_running()` was a stub
that unconditionally returned False.
"""
import pytest

from core.api.routers import status as status_router
from core.loop import loop_state


@pytest.mark.parametrize("runtime,expected", [
    ({"tick_count": 0, "running": False, "start_time": None, "pid": 1}, False),
    ({"tick_count": 5, "running": True, "start_time": 1.0, "pid": 1}, True),
    ({"tick_count": 76, "running": False, "start_time": None, "pid": 2}, True),  # loop in another process (heartbeat)
])
def test_status_loop_running_follows_the_real_loop_state(monkeypatch, runtime, expected):
    monkeypatch.setattr(loop_state, "get_runtime", lambda: runtime)
    assert status_router._get_loop_running() is expected


def test_status_survives_loop_state_errors(monkeypatch):
    def boom():
        raise RuntimeError("heartbeat unreadable")

    monkeypatch.setattr(loop_state, "get_runtime", boom)
    assert status_router._get_loop_running() is False
