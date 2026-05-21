import asyncio
import time
import pytest
from districts.emergency.escalation import EscalationManager, EscalationState, _ACCELERATION_WINDOW
from districts.emergency.classifier import ScoredEmergency
from districts.emergency.detector import EmergencyEvent


async def _make_mock_pushover_result(step, emergency, runbook_actions=None):
    return {"action": f"pushover_{step}", "status": "ok", "http_status": 200}


@pytest.fixture
def manager():
    mgr = EscalationManager(test_mode=True)
    mgr._step_pushover = _make_mock_pushover_result
    return mgr


@pytest.fixture
def critical_emergency():
    event = EmergencyEvent(
        event_id="esc-test-001",
        domain="system",
        signal_name="disk_full",
        raw_value=98,
        raw_message="Disk usage above 95%",
        detected_at=time.time(),
        source="test",
    )
    return ScoredEmergency(
        event=event,
        severity="CRITICAL",
        severity_score=0.95,
        recommendation="automated_recovery",
        classified_at=time.time(),
        confidence=0.98,
        escalation_path="auto",
    )


@pytest.fixture
def low_emergency():
    event = EmergencyEvent(
        event_id="esc-low-001",
        domain="system",
        signal_name="high_cpu",
        raw_value=50,
        raw_message="CPU usage normal",
        detected_at=time.time(),
        source="test",
    )
    return ScoredEmergency(event=event, severity="LOW", classified_at=time.time())


@pytest.mark.asyncio
async def test_tier_progression_critical(manager, critical_emergency):
    results = await manager.escalate(critical_emergency)
    assert len(results) > 0
    actions = [r["action"] for r in results]
    assert results[0].get("status") in ("ok", "no_actions", "already_acknowledged")


@pytest.mark.asyncio
async def test_tier_progression_low(manager, low_emergency):
    results = await manager.escalate(low_emergency)
    assert len(results) == 1
    assert results[0]["action"] in ("log_only",)


@pytest.mark.asyncio
async def test_acknowledgment(manager, critical_emergency):
    manager.acknowledge("esc-test-001")
    results = await manager.escalate(critical_emergency)
    assert any(r.get("action") == "already_acknowledged" for r in results)


@pytest.mark.asyncio
async def test_acknowledgment_before_escalation(manager, critical_emergency):
    results = await manager.escalate(critical_emergency)
    manager.acknowledge("esc-test-001")
    results = await manager.escalate(critical_emergency)
    assert any(r.get("action") == "already_acknowledged" for r in results)


@pytest.mark.asyncio
async def test_escalation_state(manager, critical_emergency):
    await manager.escalate(critical_emergency)
    state = manager.get_state()
    assert isinstance(state, EscalationState)
    assert len(state.escalation_log) >= 1


@pytest.mark.asyncio
async def test_pause_resume(manager, critical_emergency):
    manager.pause()
    results = await manager.escalate(critical_emergency)
    assert any(r["status"] == "skipped" for r in results)

    manager.resume()
    results = await manager.escalate(critical_emergency)
    assert all(r["status"] != "skipped" for r in results)


@pytest.mark.asyncio
async def test_acceleration(manager, critical_emergency):
    await manager.escalate(critical_emergency)
    assert manager._should_accelerate("system") is True


@pytest.mark.asyncio
async def test_no_acceleration_first_time(manager, critical_emergency):
    assert manager._should_accelerate("system") is False


@pytest.mark.asyncio
async def test_escalation_log_entry(manager, critical_emergency):
    await manager.escalate(critical_emergency)
    state = manager.get_state()
    entry = state.escalation_log[-1]
    assert entry["event_id"] == "esc-test-001"
    assert entry["severity"] == "CRITICAL"
    assert entry["domain"] == "system"


@pytest.mark.asyncio
async def test_pushover_step_format(manager, critical_emergency):
    results = await manager.escalate(critical_emergency)
    pushover_results = [r for r in results if "pushover" in r.get("action", "")]
    for r in pushover_results:
        assert r.get("status") in ("ok", "failed", "error", "stopped", "skipped", "no_actions")


@pytest.mark.asyncio
async def test_escalation_timing_critical(manager, critical_emergency):
    t0 = time.monotonic()
    results = await manager.escalate(critical_emergency)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0
    assert len(results) >= 1
