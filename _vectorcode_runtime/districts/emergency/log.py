from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from loguru import logger


@dataclass
class EmergencyLogEntry:
    event_id: str = ""
    severity: str = "LOW"
    domain: str = ""
    signal_name: str = ""
    detected_at: float = 0.0
    classified_at: float | None = None
    severity_score: float = 0.0
    actions_taken: list[dict] = field(default_factory=list)
    escalation_path: list[str] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_at: float | None = None
    resolved: bool = False
    resolved_at: float | None = None
    duration_seconds: float | None = None
    outcome: str = "unresolved"
    false_alarm: bool = False


class EmergencyLog:
    def __init__(self, db_path: str | None = None):
        from core.memory.db_utils import configured_db_path
        self._db_path = db_path or str(configured_db_path())
        self._lock = threading.RLock()
        self._conn = self._open_conn(self._db_path)
        self._conn.row_factory = self._row_class(self._conn)
        self._enable_wal()
        self._ensure_table()

    @staticmethod
    def _row_class(conn):
        """sqlite3.Row rejects sqlcipher cursors — pick the driver's own Row."""
        mod = type(conn).__module__
        if mod.startswith("sqlcipher3"):
            from sqlcipher3 import dbapi2
            return dbapi2.Row
        if mod.startswith("pysqlcipher3"):
            from pysqlcipher3 import dbapi2
            return dbapi2.Row
        return sqlite3.Row

    @staticmethod
    def _open_conn(db_path: str) -> sqlite3.Connection:
        """Own connection (private row_factory) — SQLCipher-keyed when active."""
        try:
            from core.memory import episodic
            if getattr(episodic, "_USE_SQLCIPHER", False):
                return episodic._open_sqlcipher_connection(db_path)
        except Exception as e:
            logger.warning("[EmergencyLog] SQLCipher open failed, plain sqlite: {}", e)
        return sqlite3.connect(db_path, check_same_thread=False)

    def _enable_wal(self) -> None:
        try:
            with self._lock:
                apply_pragmas(self._conn)
        except Exception as e:
            logger.warning("[EmergencyLog] WAL mode not available: {}", e)

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute("""
            CREATE TABLE IF NOT EXISTS emergency_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                severity TEXT NOT NULL,
                domain TEXT NOT NULL,
                signal_name TEXT NOT NULL,
                detected_at REAL NOT NULL,
                classified_at REAL,
                severity_score REAL,
                actions_taken TEXT,
                escalation_path TEXT,
                acknowledged INTEGER DEFAULT 0,
                acknowledged_at REAL,
                resolved INTEGER DEFAULT 0,
                resolved_at REAL,
                duration_seconds REAL,
                outcome TEXT,
                false_alarm INTEGER DEFAULT 0,
                prev_hash TEXT,
                entry_hash TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
            self._conn.commit()

    def append(self, entry: EmergencyLogEntry) -> bool:
        conn = self._conn
        try:
            with self._lock:
                prev_hash = conn.execute(
                    "SELECT entry_hash FROM emergency_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = prev_hash[0] if prev_hash else ""

                data_str = (
                    entry.event_id + entry.severity + entry.domain + str(entry.detected_at)
                    + json.dumps(entry.actions_taken, sort_keys=True) + prev_hash
                )
                entry_hash = hashlib.sha256(data_str.encode()).hexdigest()

                conn.execute(
                    """INSERT INTO emergency_log
                   (event_id, severity, domain, signal_name, detected_at, classified_at,
                    severity_score, actions_taken, escalation_path, acknowledged,
                    acknowledged_at, resolved, resolved_at, duration_seconds, outcome,
                    false_alarm, prev_hash, entry_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.event_id, entry.severity, entry.domain, entry.signal_name,
                    entry.detected_at, entry.classified_at, entry.severity_score,
                    json.dumps(entry.actions_taken), json.dumps(entry.escalation_path),
                    int(entry.acknowledged), entry.acknowledged_at,
                    int(entry.resolved), entry.resolved_at,
                    entry.duration_seconds, entry.outcome,
                    int(entry.false_alarm),
                    prev_hash, entry_hash,
                ),
                )
                self._conn.commit()
            return True
        except Exception as e:
            # sqlcipher3's IntegrityError is not a subclass of sqlite3's
            if type(e).__name__ != "IntegrityError":
                raise
            logger.warning("[EmergencyLog] duplicate event_id: {}", entry.event_id)
            return False

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM emergency_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_by_domain(self, domain: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM emergency_log WHERE domain = ? ORDER BY id DESC LIMIT ?", (domain, limit)
            ).fetchall()
        return [dict(row) for row in rows]

    def verify_chain(self) -> bool:
        with self._lock:
            rows = self._conn.execute(
                "SELECT entry_hash, prev_hash, event_id, severity, domain, detected_at, actions_taken "
                "FROM emergency_log ORDER BY id ASC"
            ).fetchall()
        expected_prev = ""
        for row in rows:
            entry_hash, prev_hash, event_id, severity, domain, detected_at, actions_taken = row
            if prev_hash != expected_prev:
                logger.error("[EmergencyLog] hash chain broken at {}", event_id)
                return False
            data_str = event_id + severity + domain + str(detected_at) + (actions_taken or "[]") + prev_hash
            expected = hashlib.sha256(data_str.encode()).hexdigest()
            if entry_hash != expected:
                logger.error("[EmergencyLog] tampered entry: {}", event_id)
                return False
            expected_prev = entry_hash
        return True

    def summary(self, days: int = 7) -> dict[str, Any]:
        cutoff = time.time() - days * 86400
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM emergency_log WHERE detected_at >= ?", (cutoff,)
            ).fetchone()[0]
            by_severity = dict(self._conn.execute(
                "SELECT severity, COUNT(*) FROM emergency_log WHERE detected_at >= ? GROUP BY severity", (cutoff,)
            ).fetchall())
            by_domain = dict(self._conn.execute(
                "SELECT domain, COUNT(*) FROM emergency_log WHERE detected_at >= ? GROUP BY domain", (cutoff,)
            ).fetchall())
            outcomes = dict(self._conn.execute(
                "SELECT outcome, COUNT(*) FROM emergency_log WHERE detected_at >= ? GROUP BY outcome", (cutoff,)
            ).fetchall())
            avg_response = self._conn.execute(
                "SELECT AVG(duration_seconds) FROM emergency_log WHERE detected_at >= ? AND resolved = 1 AND duration_seconds IS NOT NULL", (cutoff,)
            ).fetchone()[0]
            avg_resolution = self._conn.execute(
                "SELECT AVG(duration_seconds) FROM emergency_log WHERE detected_at >= ? AND resolved = 1 AND duration_seconds IS NOT NULL", (cutoff,)
            ).fetchone()[0]
            false_alarms = self._conn.execute(
                "SELECT COUNT(*) FROM emergency_log WHERE detected_at >= ? AND false_alarm = 1", (cutoff,)
            ).fetchone()[0]

        return {
            "total_emergencies": total,
            "by_severity": by_severity,
            "by_domain": by_domain,
            "outcomes": outcomes,
            "chain_integrity": self.verify_chain(),
            "avg_response_time_seconds": round(avg_response, 2) if avg_response else 0.0,
            "avg_resolution_time_seconds": round(avg_resolution, 2) if avg_resolution else 0.0,
            "false_alarms": false_alarms,
        }
