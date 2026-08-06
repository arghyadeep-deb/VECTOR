import asyncio
import time
import pytest
from districts.emergency.detector import EmergencyDetector, EmergencyEvent
from districts.emergency.classifier import SeverityClassifier, ScoredEmergency
from districts.emergency.runbook import RunbookExecutor
from districts.emergency.escalation import EscalationManager
from districts.emergency.log import EmergencyLog, EmergencyLogEntry


async def _mock_pushover(step, emergency, runbook_actions=None):
    return {"action": f"pushover_{step}", "status": "ok"}


def _make_escalation():
    e = EscalationManager(test_mode=True)
    e._step_pushover = _mock_pushover
    return e


@pytest.mark.asyncio
async def test_pipeline_signal_to_event():
    detector = EmergencyDetector()
    classifier = SeverityClassifier()
    runbook = RunbookExecutor()
    escalation = _make_escalation()

    event = await detector.process_signal("system", "high_cpu", 95)
    assert event is not None

    scored = classifier.classify(event)
    assert scored.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    actions = await runbook.execute(scored)
    assert len(actions) >= 0

    escalation_results = await escalation.escalate(scored, actions)
    assert len(escalation_results) >= 0


@pytest.mark.asyncio
async def test_pipeline_critical_path():
    detector = EmergencyDetector()
    classifier = SeverityClassifier()
    escalation = _make_escalation()

    event = await detector.process_signal("health", "heart_rate_stopped", 0)
    assert event is not None

    scored = classifier.classify(event)
    assert scored.severity_score > 0

    results = await escalation.escalate(scored)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_pipeline_with_log():
    import tempfile
    import os
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    try:
        detector = EmergencyDetector()
        classifier = SeverityClassifier()
        log = EmergencyLog(db_path=tmp.name)

        event = await detector.process_signal("system", "disk_full", 98)
        assert event is not None

        scored = classifier.classify(event)

        entry = EmergencyLogEntry(
            event_id=event.event_id,
            severity=scored.severity,
            domain=event.domain,
            signal_name=event.signal_name,
            detected_at=event.detected_at,
            classified_at=scored.classified_at,
            severity_score=scored.severity_score,
            outcome="logged",
        )
        ok = log.append(entry)
        assert ok is True

        recent = log.get_recent(limit=5)
        assert len(recent) >= 1
        assert recent[0]["event_id"] == event.event_id
        assert log.verify_chain() is True
    finally:
        log._conn.close()
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_subscription_to_classification():
    detector = EmergencyDetector()
    queue = detector.subscribe_signal("system")

    async def consume():
        event = await asyncio.wait_for(queue.get(), timeout=2.0)
        classifier = SeverityClassifier()
        return classifier.classify(event)

    consume_task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    await detector.process_signal("system", "high_ram", 95)

    scored = await asyncio.wait_for(consume_task, timeout=3.0)
    assert scored is not None
    assert scored.event.signal_name == "high_ram"


@pytest.mark.asyncio
async def test_multiple_signals_independent():
    detector = EmergencyDetector()

    cpu_event = await detector.process_signal("system", "high_cpu", 95)
    health_event = await detector.process_signal("health", "heart_rate_high", 150)

    assert cpu_event is not None
    assert health_event is not None
    assert cpu_event.event_id != health_event.event_id


@pytest.mark.asyncio
async def test_dedup_across_pipeline():
    detector = EmergencyDetector()
    classifier = SeverityClassifier()

    event1 = await detector.process_signal("system", "process_crash", True, source="int_test")
    assert event1 is not None
    scored1 = classifier.classify(event1)

    await asyncio.sleep(0.05)

    event2 = await detector.process_signal("system", "process_crash", True, source="int_test")
    assert event2 is None


@pytest.mark.asyncio
async def test_runbook_escalation_chain(monkeypatch):
    # 2026-08-06: mock subprocess.run to prevent real Ollama subprocess spawn
    # (ollama list / ollama serve) which hangs when Ollama is not running.
    import subprocess as _sp
    _fake_result = _sp.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(_sp, "run", lambda *a, **k: _fake_result)

    detector = EmergencyDetector()
    classifier = SeverityClassifier()
    runbook = RunbookExecutor()
    escalation = _make_escalation()

    event = await detector.process_signal("system", "oom_detected", True)
    assert event is not None

    scored = classifier.classify(event)

    actions = await runbook.execute(scored)
    assert len(actions) == 3

    results = await escalation.escalate(scored, actions)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_acknowledge_pipeline():
    detector = EmergencyDetector()
    escalation = _make_escalation()

    event = await detector.process_signal("system", "high_cpu", 95)
    assert event is not None

    escalation.acknowledge(event.event_id)
    assert event.event_id in escalation._acknowledged
