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


def test_sense_tick_polls_phone_when_enabled(monkeypatch):
    """Task B.2: PhoneController (ADB bridge) exists but was never an
    observe source — nothing in the loop ever called it. Gated by a new
    sensing.phone_enabled flag (default off, owner-hardware-dependent)."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["sensing"], "camera_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "screen_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "phone_enabled", True)

    class _FakePhoneController:
        def is_connected(self):
            return True

        def get_notifications(self):
            return [{"package": "com.whatsapp", "title": "Mom", "text": "call me", "time": "123"}]

    monkeypatch.setattr("core.control.phone_controller.PhoneController", _FakePhoneController)

    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())

    snap = get_sense_cache_snapshot()
    assert snap["phone"]["connected"] is True
    assert snap["phone"]["notification_count"] == 1
    assert snap["phone"]["recent"][0]["package"] == "com.whatsapp"


def test_sense_tick_phone_disabled_by_default_no_crash():
    """phone_enabled defaults False (owner-hardware-dependent) — _sense_tick
    must not crash or attempt ADB calls when it's off."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    assert CONFIG["sensing"].get("phone_enabled") is False
    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())  # must not raise


def test_sense_tick_phone_enabled_no_device_degrades_gracefully(monkeypatch):
    """Graceful when no device — PhoneController already returns
    is_connected()=False / get_notifications()=[] without a device; the
    sense cache should reflect that, not crash or hang."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["sensing"], "camera_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "screen_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "phone_enabled", True)

    class _NoDevicePhoneController:
        def is_connected(self):
            return False

        def get_notifications(self):
            return []

    monkeypatch.setattr("core.control.phone_controller.PhoneController", _NoDevicePhoneController)

    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())

    snap = get_sense_cache_snapshot()
    assert snap["phone"]["connected"] is False
    assert snap["phone"]["notification_count"] == 0


def test_phone_state_propagates_into_context_engine_world_state():
    update_sense_cache(
        screen_summary="", presence="present",
        phone={"connected": True, "notification_count": 3, "recent": []},
    )
    state = ContextEngine().get_world_state()
    assert state["phone_connected"] is True
    assert state["phone_notification_count"] == 3


def test_sense_tick_polls_wearable_when_enabled(monkeypatch):
    """Task B.3: architecture names wearable (HR/sleep/steps) as a core
    observe source; districts/health/wearable_connector.py already exists
    and degrades gracefully with no sources, but nothing ever polled it
    from the loop. Gated by sensing.wearable_enabled (default off,
    owner-hardware-dependent)."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["sensing"], "camera_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "screen_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "phone_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "wearable_enabled", True)

    class _FakeWearableConnector:
        async def poll_all(self):
            return [{"source": "oura", "heart_rate": 62, "sleep_hours": 7.5}]

    monkeypatch.setattr("districts.health.wearable_connector.WearableConnector", _FakeWearableConnector)

    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())

    snap = get_sense_cache_snapshot()
    assert snap["wearable"]["available"] is True
    assert snap["wearable"]["data"][0]["heart_rate"] == 62


def test_sense_tick_wearable_disabled_by_default_no_crash():
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    assert CONFIG["sensing"].get("wearable_enabled") is False
    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())  # must not raise


def test_sense_tick_wearable_no_sources_degrades_gracefully(monkeypatch):
    """Graceful when no wearable configured — the real WearableConnector
    with zero enabled_sources should produce an empty poll, not a crash."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["sensing"], "camera_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "screen_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "phone_enabled", False)
    monkeypatch.setitem(CONFIG["sensing"], "wearable_enabled", True)
    monkeypatch.setitem(CONFIG.setdefault("health", {}), "wearable_sources", [])

    loop = AutonomousLoop()
    asyncio.run(loop._sense_tick())

    snap = get_sense_cache_snapshot()
    assert snap["wearable"]["available"] is False
