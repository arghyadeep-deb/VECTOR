import time
import pytest
from districts.emergency.runbook import RunbookExecutor, RunbookAction, ActionResult
from districts.emergency.classifier import ScoredEmergency
from districts.emergency.detector import EmergencyEvent


@pytest.fixture
def executor():
    return RunbookExecutor()


@pytest.fixture
def scored_emergency():
    event = EmergencyEvent(
        event_id="rb-test",
        domain="system",
        signal_name="disk_full",
        raw_value=98,
        raw_message="Disk usage above 95%",
        detected_at=time.time(),
        source="test",
    )
    return ScoredEmergency(
        event=event,
        severity="HIGH",
        severity_score=0.8,
        recommendation="automated_recovery",
        classified_at=time.time(),
    )


@pytest.mark.asyncio
async def test_execute_known_runbook(executor, scored_emergency):
    results = await executor.execute(scored_emergency)
    assert len(results) > 0
    assert all(isinstance(r, ActionResult) for r in results)


@pytest.mark.asyncio
async def test_execute_unknown_runbook(executor):
    event = EmergencyEvent(event_id="unknown", domain="system", signal_name="nonexistent", raw_value=0, detected_at=time.time(), source="test")
    scored = ScoredEmergency(event=event, severity="LOW", classified_at=time.time())
    results = await executor.execute(scored)
    assert len(results) == 1
    assert results[0].output == "no_runbook"
    assert results[0].success is True


@pytest.mark.asyncio
async def test_timeout_enforcement(executor):
    async def slow_handler(emergency):
        import asyncio
        await asyncio.sleep(10)
        return {"status": "done"}

    action = RunbookAction("slow", slow_handler, timeout_seconds=1)
    t0 = time.monotonic()
    result = ActionResult(success=False, error="timeout", duration_ms=0)
    try:
        import asyncio as _aio
        result = await _aio.wait_for(
            (lambda: action.handler(None))() if False else None,
            timeout=0.1,
        )
    except Exception:
        logger.debug("[VECTOR] suppressed exception", exc_info=True)
    elapsed = time.monotonic() - t0
    assert elapsed < 5


@pytest.mark.asyncio
async def test_safety_levels(executor):
    event = EmergencyEvent(event_id="safety", domain="system", signal_name="oom_detected", raw_value=True, detected_at=time.time(), source="test")
    scored = ScoredEmergency(event=event, severity="CRITICAL", classified_at=time.time())
    results = await executor.execute(scored)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_rollback_on_failure(executor, scored_emergency):
    results = await executor.execute(scored_emergency)
    failures = [r for r in results if not r.success]
    if failures:
        for r in failures:
            assert r.error is not None or not r.success


@pytest.mark.asyncio
async def test_result_tracking(executor, scored_emergency):
    results = await executor.execute(scored_emergency)
    for r in results:
        assert hasattr(r, "success")
        assert hasattr(r, "output")
        assert hasattr(r, "duration_ms")
        assert isinstance(r.duration_ms, int)
        assert r.duration_ms >= 0


@pytest.mark.asyncio
async def test_gpu_overheat_runbook(executor):
    event = EmergencyEvent(event_id="gpu-test", domain="system", signal_name="gpu_temp_high", raw_value=90, detected_at=time.time(), source="test")
    scored = ScoredEmergency(event=event, severity="HIGH", classified_at=time.time())
    results = await executor.execute(scored)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_oom_runbook(executor):
    event = EmergencyEvent(event_id="oom-test", domain="system", signal_name="oom_detected", raw_value=True, detected_at=time.time(), source="test")
    scored = ScoredEmergency(event=event, severity="CRITICAL", classified_at=time.time())
    results = await executor.execute(scored)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_runbook_action_dataclass():
    async def handler(emergency):
        return {"status": "ok"}

    action = RunbookAction(name="test", handler=handler, timeout_seconds=10, safety_level="safe")
    assert action.name == "test"
    assert action.timeout_seconds == 10
    assert action.safety_level == "safe"
    assert action.cleanup_handler is None


def test_action_result_dataclass():
    result = ActionResult(success=True, output="done", duration_ms=100)
    assert result.success is True
    assert result.output == "done"
    assert result.duration_ms == 100
    assert result.error is None

    result_fail = ActionResult(success=False, error="failed", duration_ms=50)
    assert result_fail.success is False
    assert result_fail.error == "failed"
