"""Regression tests for OD-52 audit-log encryption and migration."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_security.audit import AuditLogger, _USE_SQLCIPHER
from vectorcode.src.vc_security.types import (
    ScanFinding,
    SecurityEvent,
    SecurityEventType,
    ThreatLevel,
)

pytestmark = pytest.mark.skipif(
    not _USE_SQLCIPHER, reason="sqlcipher3 not installed in this environment"
)

_FAKE_SECRET = "sk-FAKE-TOKEN-FOR-TEST-ONLY-1234567890"


def _event(timestamp: float, matched_text: str, preview: str) -> SecurityEvent:
    return SecurityEvent(
        event_type=SecurityEventType.SECRET_DETECTED,
        timestamp=timestamp,
        findings=[
            ScanFinding(
                pattern_name="api_key",
                matched_text=matched_text,
                threat_level=ThreatLevel.CRITICAL,
                start=7,
                end=7 + len(matched_text),
                description="test secret",
            )
        ],
        content_preview=preview,
        action_taken="blocked",
    )


def _make_plaintext_db(path: Path) -> list[SecurityEvent]:
    events = [
        _event(1_700_000_001.25, "sk-PLAINTEXT-MIGRATION-ONE", "first preview"),
        _event(1_700_000_002.5, "pii@example.test", "second preview"),
        _event(1_700_000_003.75, "+91-99999-00000", "third preview"),
    ]
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE security_events (
            id INTEGER PRIMARY KEY,
            timestamp REAL,
            event_type TEXT,
            findings_json TEXT,
            content_preview TEXT,
            action_taken TEXT,
            row_hash TEXT DEFAULT '',
            prev_hash TEXT DEFAULT ''
        )
        """
    )
    prev_hash = ""
    for event in events:
        findings_json = json.dumps(
            [
                {
                    "pattern_name": finding.pattern_name,
                    "matched_text": finding.matched_text,
                    "threat_level": finding.threat_level.value,
                    "start": finding.start,
                    "end": finding.end,
                    "description": finding.description,
                }
                for finding in event.findings
            ]
        )
        hash_input = (
            f"{prev_hash}|{event.timestamp}|{event.event_type.value}"
            f"|{findings_json}|{event.content_preview}|{event.action_taken}"
        )
        row_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        conn.execute(
            """INSERT INTO security_events
               (timestamp, event_type, findings_json, content_preview,
                action_taken, row_hash, prev_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event.timestamp,
                event.event_type.value,
                findings_json,
                event.content_preview,
                event.action_taken,
                row_hash,
                prev_hash,
            ),
        )
        prev_hash = row_hash
    conn.commit()
    conn.close()
    return events


def test_fresh_audit_database_is_genuinely_encrypted(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh_audit.db"
    audit = AuditLogger(db_path)
    try:
        audit.log(_event(1_700_000_000.0, _FAKE_SECRET, f"token={_FAKE_SECRET}"))
    finally:
        audit.close()

    raw = db_path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert _FAKE_SECRET.encode() not in raw


def test_plaintext_audit_database_migrates_with_chain_and_events_intact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "audit.db"
    expected = _make_plaintext_db(db_path)
    assert db_path.read_bytes()[:16] == b"SQLite format 3\x00"

    audit = AuditLogger(db_path)
    try:
        assert audit.verify_chain() == (True, None)
        actual = list(reversed(audit.query(limit=10)))
    finally:
        audit.close()

    assert actual == expected
    assert db_path.read_bytes()[:16] != b"SQLite format 3\x00"
    backups = list(tmp_path.glob("audit.db.plaintext.bak.*"))
    assert len(backups) == 1

    backup_conn = sqlite3.connect(str(backups[0]))
    try:
        backup_rows = backup_conn.execute(
            "SELECT timestamp, event_type, findings_json, content_preview, "
            "action_taken, row_hash, prev_hash FROM security_events ORDER BY id"
        ).fetchall()
    finally:
        backup_conn.close()
    assert len(backup_rows) == len(expected)
    assert backup_rows[0][2].find("sk-PLAINTEXT-MIGRATION-ONE") != -1


def test_encrypted_audit_database_is_not_migrated_twice(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    _make_plaintext_db(db_path)

    first = AuditLogger(db_path)
    first.close()
    assert len(list(tmp_path.glob("audit.db.plaintext.bak.*"))) == 1

    second = AuditLogger(db_path)
    try:
        assert second.verify_chain() == (True, None)
        assert second.count() == 3
    finally:
        second.close()
    assert len(list(tmp_path.glob("audit.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

