"""Audit phase 3 — districts/emergency: false-delivered / false-clear fixes."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.emergency import main as em_main
from districts.emergency.classifier import SeverityClassifier
from districts.emergency.detector import EmergencyDetector, EmergencyEvent
from districts.emergency.escalation import EscalationManager
from districts.emergency.runbook import RunbookExecutor
from districts.emergency.classifier import ScoredEmergency


def _scored(signal: str, domain: str, severity: str = "CRITICAL", eid: str = "t1") -> ScoredEmergency:
    ev = EmergencyEvent(event_id=eid, domain=domain, signal_name=signal, raw_message="m", detected_at=time.time())
    return ScoredEmergency(event=ev, severity=severity, severity_score=0.95, classified_at=time.time())


def test_heart_stopped_not_dampened_to_log_only_in_work_hours(monkeypatch):
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time((2026, 1, 1, 12, 0, 0, 3, 1, 0)))
    det = EmergencyDetector()
    ev = asyncio.run(det.process_signal("health", "heart_rate_stopped", 0))
    assert ev is not None
    scored = SeverityClassifier().classify(ev)
    assert scored.severity == "CRITICAL"


def test_low_rule_without_explicit_severity_unchanged(monkeypatch):
    monkeypatch.setattr(time, "localtime", lambda *a: time.struct_time((2026, 1, 1, 12, 0, 0, 3, 1, 0)))
    det = EmergencyDetector()
    ev = asyncio.run(det.process_signal("system", "high_cpu", 95))
    assert SeverityClassifier().classify(ev).severity == "LOW"


@pytest.mark.parametrize("signal,domain", [("heart_rate_stopped", "health"), ("battery_critical", "battery")])
def test_runbook_does_not_claim_notification_sent(signal, domain):
    res = asyncio.run(RunbookExecutor().execute(_scored(signal, domain)))
    assert res[0].success is False


def test_gpu_runbook_reports_nvidia_smi_failure(monkeypatch):
    import subprocess

    class R:
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    res = asyncio.run(RunbookExecutor().execute(_scored("gpu_temp_high", "system", "HIGH")))
    assert res[0].success is False


def test_escalation_runbook_step_not_ok_when_actions_failed():
    from districts.emergency.runbook import ActionResult
    em = EscalationManager(test_mode=True)
    r = asyncio.run(em._step_runbook("auto_runbook", _scored("x", "system"), [ActionResult(success=False, error="e")]))
    assert r["status"] != "ok"


def test_outcome_not_escalated_when_nothing_delivered():
    sc = _scored("heart_rate_stopped", "health")
    failed = [{"action": "runbook_executed", "status": "failed"}, {"action": "pushover_pushover_emergency", "status": "skipped"}]
    assert em_main.EmergencyResponseSystem._outcome(sc, failed) == "escalation_failed"
    ok = failed + [{"action": "pushover_pushover_emergency", "status": "ok"}]
    assert em_main.EmergencyResponseSystem._outcome(sc, ok) == "escalated"


def test_emit_logs_when_system_not_started():
    from loguru import logger
    msgs: list[str] = []
    hid = logger.add(lambda m: msgs.append(str(m)), level="WARNING")
    em_main.set_instance(None)
    try:
        assert asyncio.run(em_main._emit("health", "heart_rate_stopped", 0, "t")) is None
    finally:
        logger.remove(hid)
    assert any("DROPPED" in m for m in msgs)


def test_bad_sensor_value_rule_failure_is_visible():
    from loguru import logger
    msgs: list[str] = []
    hid = logger.add(lambda m: msgs.append(str(m)), level="WARNING")
    try:
        assert asyncio.run(EmergencyDetector().process_signal("health", "heart_rate_critical", "abc")) is None
    finally:
        logger.remove(hid)
    assert any("rule check failed" in m for m in msgs)


def _patch_httpx(monkeypatch):
    import httpx
    sent: list[dict] = []

    class Resp:
        status_code = 200

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, data=None, **k):
            sent.append(data)
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    from districts.emergency import escalation as esc
    monkeypatch.setitem(esc.CONFIG, "pushover_token", "tok")
    monkeypatch.setitem(esc.CONFIG, "pushover_user", "usr")
    return sent


def test_pushover_storm_is_rate_limited(monkeypatch):
    sent = _patch_httpx(monkeypatch)
    em = EscalationManager(test_mode=False)
    sc = _scored("x", "system", "MEDIUM")

    async def go():
        return [await em._step_pushover("pushover_normal", sc) for _ in range(50)]

    res = asyncio.run(go())
    assert len(sent) <= 20
    assert any(r["status"] == "rate_limited" for r in res)


def test_pushover_disabled_in_config_is_honored(monkeypatch):
    sent = _patch_httpx(monkeypatch)
    from districts.emergency import escalation as esc
    monkeypatch.setitem(esc.CONFIG["emergency"], "pushover_enabled", False)
    r = asyncio.run(EscalationManager(test_mode=False)._step_pushover("pushover_normal", _scored("x", "system", "MEDIUM")))
    assert r["status"] == "skipped" and not sent
