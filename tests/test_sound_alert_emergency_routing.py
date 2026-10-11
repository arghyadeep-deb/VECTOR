"""FL-029 — sound_classifier's alert_sound signal must reach a real,
governed emergency escalation, not just a mocked receiver.

core/sensing/sound_classifier.py emits domain="environment",
signal_name="alert_sound" via districts/emergency/main.py's module-level
_emit(). Before this fix:
  1. districts/emergency/detector.py's EmergencyDetector had no rule for
     ("environment", "alert_sound"), so process_signal() always returned
     None for it regardless of value -- the signal was silently dropped
     before it could even reach a queue.
  2. EmergencyResponseSystem.start() never subscribed to the "environment"
     domain, so even a matching rule's queued event would never be
     drained/escalated by _process_queue().

tests/test_sound_classifier_emergency_signal.py already covers the asyncio
scheduling bug in SoundClassifier._emit_emergency_signal() itself (that the
coroutine runs at all) by mocking districts.emergency.main._emit directly --
it does NOT prove the real EmergencyDetector/EmergencyResponseSystem
actually routes the event anywhere. This file exercises the real,
unmocked detector + a running EmergencyResponseSystem instead.
"""
from __future__ import annotations

import asyncio

import pytest

from districts.emergency.detector import EmergencyDetector
from districts.emergency.main import EmergencyResponseSystem


@pytest.mark.asyncio
async def test_detector_has_a_rule_for_alert_sound():
    detector = EmergencyDetector()
    rules = detector.get_rules()
    assert any(
        r["domain"] == "environment" and r["signal_name"] == "alert_sound"
        for r in rules
    )


@pytest.mark.asyncio
async def test_detector_process_signal_triggers_for_alert_sound():
    detector = EmergencyDetector()
    event = await detector.process_signal(
        "environment", "alert_sound", True, source="test_sound_alert_routing"
    )
    assert event is not None
    assert event.domain == "environment"
    assert event.signal_name == "alert_sound"


@pytest.mark.asyncio
async def test_running_system_escalates_exactly_once_and_debounces_repeat():
    system = EmergencyResponseSystem(test_mode=True)
    processed: list = []

    async def _record(event):
        processed.append(event)

    system._process_event = _record  # avoid real DB/escalation side effects
    await system.start()
    try:
        source = "test_sound_alert_routing_e2e"

        first = await system.emit_signal(
            "environment", "alert_sound", True, source=source
        )
        assert first is not None

        # Give the real background queue-consumer task (started by
        # system.start(), now including the "environment" domain) a chance
        # to actually dequeue and process the event.
        for _ in range(20):
            if processed:
                break
            await asyncio.sleep(0.05)
        assert len(processed) == 1
        assert processed[0].domain == "environment"
        assert processed[0].signal_name == "alert_sound"

        # Same source within the 60s dedup window -- detector must not
        # trigger a second escalation for the repeated event.
        second = await system.emit_signal(
            "environment", "alert_sound", True, source=source
        )
        assert second is None
        await asyncio.sleep(0.1)
        assert len(processed) == 1  # still exactly one, debounced
    finally:
        await system.stop()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
