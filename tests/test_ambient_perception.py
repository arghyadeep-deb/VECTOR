"""Part B (plans/governor-wiring-and-ambient-perception.md) — the "always-on
JARVIS" gap. Screen + camera-presence already reached context_engine; fatigue,
ADB-phone, and wearable did not despite docstring claims they would.
"""
import asyncio

import pytest

from core.loop.context_engine import ContextEngine, update_sense_cache, get_sense_cache_snapshot


@pytest.fixture(autouse=True)
def _reset_sense_cache():
    """update_sense_cache mutates module-level shared state — reset around
    each test so these don't bleed into other test files in the same
    pytest session (see tests/test_predictive_analytics_run.py for the
    cautionary tale of NOT doing this for a different kind of global)."""
    import core.loop.context_engine as ce
    before = dict(ce._SENSE_CACHE)
    yield
    with ce._SENSE_CACHE_LOCK:
        ce._SENSE_CACHE.clear()
        ce._SENSE_CACHE.update(before)


def test_update_sense_cache_accepts_nested_face_dict():
    """update_sense_cache's flat-merge (`data.update(extra)`) means a bare
    `update_sense_cache(fatigue=...)` call would set a top-level "fatigue"
    key, not the nested "face": {"fatigue": ...} structure the read side
    (ContextEngine.get_world_state) actually expects. Callers must pass the
    whole nested dict as the `face` kwarg."""
    update_sense_cache(screen_summary="", presence="present", face={"detected": True, "fatigue": 7.5})
    snap = get_sense_cache_snapshot()
    assert snap["face"]["fatigue"] == 7.5


def test_fatigue_score_propagates_into_context_engine_world_state():
    update_sense_cache(screen_summary="", presence="present", face={"detected": True, "identity": "owner", "fatigue": 6.2})
    state = ContextEngine().get_world_state()
    assert state["fatigue_score"] == 6.2, (
        f"expected real fatigue score to reach world state, got {state['fatigue_score']}"
    )


def test_sense_tick_calls_health_monitor_and_writes_real_fatigue(monkeypatch):
    """Task B.1: _sense_tick() must call HealthMonitor (EAR-based,
    core/sensing/health_monitor.py) and write the result into the sense
    cache's nested face.fatigue — not leave it at the 0.0 default forever."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["sensing"], "camera_enabled", True)
    monkeypatch.setitem(CONFIG["sensing"], "screen_enabled", False)

    class _FakeFaceDetector:
        def capture_and_scan(self):
            return [{"name": "owner"}]

    class _FakeHealthMonitor:
        def get_fatigue_score(self):
            return 8.4

    monkeypatch.setattr("core.sensing.camera.FaceDetector", _FakeFaceDetector)
    monkeypatch.setattr("core.sensing.health_monitor.HealthMonitor", _FakeHealthMonitor)

    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())

    snap = get_sense_cache_snapshot()
    assert snap.get("face", {}).get("fatigue") == 8.4, (
        f"expected real HealthMonitor fatigue score in sense cache, got {snap.get('face')}"
    )

    state = ContextEngine().get_world_state()
    assert state["fatigue_score"] == 8.4
