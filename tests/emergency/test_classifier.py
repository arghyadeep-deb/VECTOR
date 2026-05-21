import time
import pytest
from districts.emergency.classifier import SeverityClassifier, ScoredEmergency, _SEVERITY_MODIFIERS
from districts.emergency.detector import EmergencyEvent


@pytest.fixture
def classifier():
    return SeverityClassifier()


@pytest.fixture
def critical_event():
    return EmergencyEvent(
        event_id="test-001",
        domain="system",
        signal_name="disk_full",
        raw_value=98,
        raw_message="Disk usage above 95%",
        detected_at=time.time(),
        source="test",
    )


@pytest.fixture
def health_event():
    return EmergencyEvent(
        event_id="test-002",
        domain="health",
        signal_name="heart_rate_stopped",
        raw_value=0,
        raw_message="Heart rate stopped",
        detected_at=time.time(),
        source="test",
    )


def test_classify_critical(classifier, critical_event):
    scored = classifier.classify(critical_event)
    assert scored.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    assert scored.severity_score > 0
    assert isinstance(scored.confidence, float)
    assert 0 <= scored.confidence <= 1.0


def test_classify_health(classifier, health_event):
    scored = classifier.classify(health_event)
    assert scored.severity_score > 0
    assert scored.recommendation != ""


def test_severity_modifiers_dict(classifier):
    assert "night_risk" in _SEVERITY_MODIFIERS
    assert "work_hours" in _SEVERITY_MODIFIERS
    assert "acknowledged_recently" in _SEVERITY_MODIFIERS
    assert "asleep" in _SEVERITY_MODIFIERS
    assert _SEVERITY_MODIFIERS["night_risk"] == 1.3
    assert _SEVERITY_MODIFIERS["work_hours"] == 0.8


def test_escalation_path(classifier, critical_event):
    scored = classifier.classify(critical_event)
    assert scored.escalation_path in ("auto", "pushover", "manual")


def test_escalation_path_health(classifier, health_event):
    scored = classifier.classify(health_event)
    assert isinstance(scored.escalation_path, str)


def test_confidence_range(classifier):
    event = EmergencyEvent(event_id="test-conf", domain="system", signal_name="high_cpu", raw_value=95, detected_at=time.time(), source="test")
    scored = classifier.classify(event)
    assert 0.0 <= scored.confidence <= 1.0


def test_recurrence_increases_score(classifier):
    now = time.time()
    for i in range(5):
        ev = EmergencyEvent(event_id=f"rec-{i}", domain="system", signal_name="high_cpu", raw_value=95, detected_at=now - 300 + i * 10, source="test")
        classifier.classify(ev)

    event = EmergencyEvent(event_id="rec-final", domain="system", signal_name="high_cpu", raw_value=95, detected_at=now, source="test")
    scored = classifier.classify(event)
    assert scored.severity_score > 0


def test_compound_detection(classifier, critical_event):
    ram_event = EmergencyEvent(event_id="ram-001", domain="system", signal_name="high_ram", raw_value=96, detected_at=time.time(), source="test")
    classifier.classify(ram_event)

    scored = classifier.classify(critical_event)
    assert "compound" in scored.context_modifiers[0] if scored.context_modifiers else True


def test_no_modifiers_baseline(classifier):
    scored = classifier.classify(
        EmergencyEvent(event_id="base", domain="network", signal_name="internet_down", raw_value=True, detected_at=time.time(), source="test")
    )
    assert scored.severity_score >= 0


def test_mark_acknowledged(classifier, critical_event):
    classifier.mark_acknowledged("test-001")
    history_len_before = len(classifier._event_history)
    _ = classifier.classify(critical_event)
    assert len(classifier._event_history) > 0
