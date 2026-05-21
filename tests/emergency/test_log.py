import time
import sqlite3
import tempfile
import os
import pytest
from districts.emergency.log import EmergencyLog, EmergencyLogEntry


@pytest.fixture
def log():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    el = EmergencyLog(db_path=tmp.name)
    yield el
    el._conn.close()
    os.unlink(tmp.name)


@pytest.fixture
def sample_entry():
    return EmergencyLogEntry(
        event_id="test-evt-001",
        severity="HIGH",
        domain="system",
        signal_name="high_cpu",
        detected_at=time.time(),
        classified_at=time.time(),
        severity_score=0.75,
        actions_taken=[{"name": "restart", "success": True}],
        escalation_path=["pushover"],
        acknowledged=False,
        resolved=False,
        outcome="escalated",
    )


def test_append_and_verify_chain(log, sample_entry):
    ok = log.append(sample_entry)
    assert ok is True
    assert log.verify_chain() is True


def test_append_duplicate(log, sample_entry):
    log.append(sample_entry)
    ok = log.append(sample_entry)
    assert ok is False


def test_summary_after_insert(log, sample_entry):
    log.append(sample_entry)
    summary = log.summary(days=7)
    assert summary["total_emergencies"] >= 1
    assert summary["chain_integrity"] is True
    assert "avg_response_time_seconds" in summary
    assert "avg_resolution_time_seconds" in summary
    assert "false_alarms" in summary


def test_get_recent(log, sample_entry):
    log.append(sample_entry)
    recent = log.get_recent(limit=10)
    assert len(recent) >= 1
    assert recent[0]["event_id"] == "test-evt-001"


def test_get_by_domain(log, sample_entry):
    log.append(sample_entry)
    entries = log.get_by_domain("system")
    assert len(entries) >= 1
    assert entries[0]["domain"] == "system"


def test_get_by_domain_no_match(log, sample_entry):
    log.append(sample_entry)
    entries = log.get_by_domain("health")
    assert len(entries) == 0


def test_chain_integrity_multiple_entries(log):
    e1 = EmergencyLogEntry(
        event_id="evt-1", severity="LOW", domain="test", signal_name="test1",
        detected_at=time.time(),
    )
    e2 = EmergencyLogEntry(
        event_id="evt-2", severity="MEDIUM", domain="test", signal_name="test2",
        detected_at=time.time() + 1,
    )
    log.append(e1)
    log.append(e2)
    assert log.verify_chain() is True


def test_chain_detects_tamper(log, sample_entry):
    log.append(sample_entry)
    cursor = log._conn.cursor()
    cursor.execute("UPDATE emergency_log SET severity = 'LOW' WHERE event_id = ?", (sample_entry.event_id,))
    log._conn.commit()
    assert log.verify_chain() is False


def test_wal_mode(log):
    cursor = log._conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode == "wal"


def test_summary_empty(log):
    summary = log.summary(days=7)
    assert summary["total_emergencies"] == 0
    assert summary["chain_integrity"] is True
    assert summary["false_alarms"] == 0
