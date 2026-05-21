from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest

from districts.health.emergency_detector import HealthEmergencyDetector
from districts.health.metrics_store import MetricsStore


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".db")
    ms = MetricsStore(db_path=tmp, retention_days=90)
    yield ms
    ms.close()
    Path(tmp).unlink(missing_ok=True)


@pytest.fixture
def detector(store: MetricsStore):
    return HealthEmergencyDetector(store=store)


class TestDetectionRules:
    def test_sustained_high_hr(self, detector: HealthEmergencyDetector):
        events = detector._rule_sustained_high_hr(150.0, datetime.datetime.now().isoformat())
        assert len(events) >= 1
        assert events[0]["event_type"] == "sustained_high_hr"
        assert events[0]["severity"] >= 7

    def test_sustained_low_hr(self, detector: HealthEmergencyDetector):
        events = detector._rule_sustained_low_hr(35.0, datetime.datetime.now().isoformat())
        assert len(events) >= 1
        assert events[0]["event_type"] == "sustained_low_hr"
        assert events[0]["severity"] >= 9

    def test_high_stress_sustained(self, detector: HealthEmergencyDetector):
        events = detector._rule_high_stress_sustained(0.85, datetime.datetime.now().isoformat())
        assert len(events) == 0

    def test_low_spo2_critical(self, detector: HealthEmergencyDetector):
        events = detector._rule_low_spo2(85.0, datetime.datetime.now().isoformat())
        assert len(events) >= 1
        assert events[0]["event_type"] == "low_spo2"
        assert events[0]["severity"] == 10

    def test_no_movement_long(self, detector: HealthEmergencyDetector):
        events = detector._rule_no_movement_long(False, datetime.datetime.now().isoformat())
        assert len(events) == 0

    def test_sleep_apnea_pattern(self, detector: HealthEmergencyDetector):
        events = detector._rule_sleep_apnea_pattern(6.0, datetime.datetime.now().isoformat())
        assert len(events) == 0

    def test_hrv_crash(self, detector: HealthEmergencyDetector):
        events = detector._rule_hrv_crash(12.0, datetime.datetime.now().isoformat())
        assert len(events) == 0

    def test_none_values_return_empty(self, detector: HealthEmergencyDetector):
        assert detector._rule_sustained_high_hr(None, "") == []
        assert detector._rule_sustained_low_hr(None, "") == []
        assert detector._rule_low_spo2(None, "") == []


class TestDurationTracking:
    def test_duration_not_triggered_on_first_shot(self, detector: HealthEmergencyDetector):
        assert detector._check_duration("test_key", True, sustain_minutes=1) is False

    def test_duration_triggers_after_sustained(self, detector: HealthEmergencyDetector):
        detector._duration_tracker["test_key2"] = {"start": 0, "alerted": False}
        assert detector._check_duration("test_key2", True, sustain_minutes=0) is True

    def test_duration_clears_on_inactive(self, detector: HealthEmergencyDetector):
        detector._duration_tracker["test_key3"] = {"start": 0, "alerted": False}
        detector._check_duration("test_key3", False, sustain_minutes=1)
        assert "test_key3" not in detector._duration_tracker

    def test_duration_does_not_repeat(self, detector: HealthEmergencyDetector):
        detector._duration_tracker["test_key4"] = {"start": 0, "alerted": True}
        assert detector._check_duration("test_key4", True, sustain_minutes=0) is False


class TestIntegrationCheck:
    def test_check_returns_list(self, detector: HealthEmergencyDetector):
        metrics = {"heart_rate": 150.0, "spo2": 85.0}
        events = detector.check(metrics)
        assert isinstance(events, list)

    def test_check_empty_metrics(self, detector: HealthEmergencyDetector):
        events = detector.check({})
        assert events == []

    def test_check_heart_rate_only(self, detector: HealthEmergencyDetector):
        events = detector.check_heart_rate_only(35.0)
        assert len(events) >= 1
        assert events[0]["event_type"] == "sustained_low_hr"

    def test_check_oxygen_only(self, detector: HealthEmergencyDetector):
        events = detector.check_oxygen_only(85.0)
        assert len(events) >= 1
        assert events[0]["event_type"] == "low_spo2"
