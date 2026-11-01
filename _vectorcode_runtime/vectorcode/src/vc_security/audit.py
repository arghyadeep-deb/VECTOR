# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Audit logger — persist security events to SQLite with Merkle hash chain."""

from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import hashlib
import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

from loguru import logger

from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR
from vectorcode.src.vc_core.events import Event, EventBus, EventType
from vectorcode.src.vc_security.types import (
    ScanFinding,
    SecurityEvent,
    SecurityEventType,
    ThreatLevel,
)

try:
    import sqlcipher3 as sqlcipher
    _USE_SQLCIPHER = True
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher
        _USE_SQLCIPHER = True
    except ImportError:
        sqlcipher = None
        _USE_SQLCIPHER = False
        logger.error(
            "[VECTOR][security_audit] SQLCipher unavailable; persistent security "
            "audit logging is disabled and startup will fail closed"
        )


def _sql_literal(value: str) -> str:
    """Return a safely quoted SQL literal for a SQLCipher PRAGMA."""
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    """Use the owner-managed encryption key shared by VECTOR stores."""
    from core.memory.episodic import _get_db_key as _episodic_get_db_key
    return _episodic_get_db_key()


def _looks_like_plaintext_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as database:
            return database.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _configure_sqlcipher_connection(conn) -> None:
    conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
    # SQLCipher's default page-size setting is process-wide, so every
    # connection must explicitly select the page size used by VECTOR stores.
    conn.execute("PRAGMA cipher_page_size = 4096")
    apply_pragmas(conn)


def _open_sqlcipher_connection(path: Path):
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        conn.execute("SELECT count(*) FROM sqlite_master")
        return conn
    except Exception:
        conn.close()
        raise


def _migrate_plaintext_audit_db_to_sqlcipher(path: Path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = Path(f"{path}.plaintext.bak.{stamp}")
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning(
        "[VECTOR][security_audit] Migrating plaintext audit DB to SQLCipher; "
        "plaintext backup kept at {}",
        backup_path,
    )
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        AuditLogger._create_table_on(conn)
        # An unkeyed SQLCipher connection reads the legacy plaintext SQLite
        # backup without importing or falling back to stdlib sqlite3.
        plain_conn = sqlcipher.connect(str(backup_path), check_same_thread=False)
        try:
            columns = [
                row[1]
                for row in plain_conn.execute(
                    'PRAGMA table_info("security_events")'
                ).fetchall()
            ]
            if columns:
                quoted_columns = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(
                    f'SELECT {quoted_columns} FROM "security_events"'
                ).fetchall()
                if rows:
                    conn.executemany(
                        f'INSERT INTO "security_events" ({quoted_columns}) '
                        f'VALUES ({placeholders})',
                        rows,
                    )
            conn.commit()
        finally:
            plain_conn.close()
        logger.info(
            "[VECTOR][security_audit] SQLCipher migration completed, backup={}",
            backup_path,
        )
        return conn
    except Exception:
        conn.close()
        if path.exists():
            os.remove(path)
        shutil.copy2(backup_path, path)
        raise


class AuditLogger:
    """Append-only SQLite audit log for security events.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    bus:
        Optional event bus — if provided, subscribes to security events
        (``SECURITY_SCAN``, ``SECURITY_ALERT``, ``SECURITY_BLOCK``).
    """

    def __init__(
        self,
        db_path: Union[str, Path] = DEFAULT_CONFIG_DIR / "audit.db",
        bus: Optional[EventBus] = None,
    ) -> None:
        if not _USE_SQLCIPHER or sqlcipher is None:
            raise RuntimeError(
                "SQLCipher is required for the security audit store; "
                "plaintext fallback is forbidden"
            )
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        from vectorcode.src.vc_security.file_utils import secure_create

        secure_create(self._db_path)
        if _looks_like_plaintext_sqlite(self._db_path):
            self._conn = _migrate_plaintext_audit_db_to_sqlcipher(self._db_path)
        else:
            self._conn = _open_sqlcipher_connection(self._db_path)
        self._conn.row_factory = sqlcipher.Row
        with self._lock:
            self._create_table_on(self._conn)
            self._migrate_schema()

        if bus is not None:
            bus.subscribe(EventType.SECURITY_SCAN, self._on_event)
            bus.subscribe(EventType.SECURITY_ALERT, self._on_event)
            bus.subscribe(EventType.SECURITY_BLOCK, self._on_event)

    @staticmethod
    def _create_table_on(conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_events (
                id          INTEGER PRIMARY KEY,
                timestamp   REAL,
                event_type  TEXT,
                findings_json TEXT,
                content_preview TEXT,
                action_taken TEXT,
                row_hash    TEXT DEFAULT '',
                prev_hash   TEXT DEFAULT ''
            )
            """
        )
        conn.commit()

    def _migrate_schema(self) -> None:
        """Add row_hash/prev_hash columns if missing (schema migration)."""
        with self._lock:
            columns = {
                row[1]
                for row in self._conn.execute(
                    "PRAGMA table_info(security_events)"
                ).fetchall()
            }
            if "row_hash" not in columns:
                self._conn.execute(
                    "ALTER TABLE security_events ADD COLUMN row_hash TEXT DEFAULT ''"
                )
            if "prev_hash" not in columns:
                self._conn.execute(
                    "ALTER TABLE security_events ADD COLUMN prev_hash TEXT DEFAULT ''"
                )
            self._conn.commit()

    # -- public API ----------------------------------------------------------

    def log(self, event: SecurityEvent) -> None:
        """Insert a security event into the audit log with Merkle hash chain."""
        findings_json = json.dumps(
            [
                {
                    "pattern_name": f.pattern_name,
                    "matched_text": f.matched_text,
                    "threat_level": f.threat_level.value,
                    "start": f.start,
                    "end": f.end,
                    "description": f.description,
                }
                for f in event.findings
            ]
        )

        with self._lock:
            prev_hash = self.tail_hash()
            hash_input = (
                f"{prev_hash}|{event.timestamp}|{event.event_type.value}"
                f"|{findings_json}|{event.content_preview}|{event.action_taken}"
            )
            row_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            self._conn.execute(
                """
                INSERT INTO security_events
                    (timestamp, event_type, findings_json, content_preview,
                     action_taken, row_hash, prev_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
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
            self._conn.commit()

    def log_declassification(
        self,
        *,
        actor: str,
        label: str,
        reason: str,
        source: str,
        destination: str,
    ) -> None:
        """Atomically append an attributable taint-declassification event."""
        details = {
            "actor": actor,
            "label": label,
            "reason": reason,
            "source": source,
            "destination": destination,
        }
        self.log(
            SecurityEvent(
                event_type=SecurityEventType.DECLASSIFICATION,
                timestamp=time.time(),
                content_preview=source,
                action_taken=json.dumps(details, sort_keys=True),
            )
        )

    def query(
        self,
        *,
        event_type: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[SecurityEvent]:
        """Query logged security events with optional filters."""
        sql = (
            "SELECT timestamp, event_type, findings_json,"
            " content_preview, action_taken"
            " FROM security_events WHERE 1=1"
        )
        params: list = []

        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        if since is not None:
            sql += " AND timestamp >= ?"
            params.append(since)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        events: List[SecurityEvent] = []
        for row in rows:
            ts, etype, findings_json, preview, action = row
            findings_raw = json.loads(findings_json) if findings_json else []
            findings = [
                ScanFinding(
                    pattern_name=f["pattern_name"],
                    matched_text=f["matched_text"],
                    threat_level=ThreatLevel(f["threat_level"]),
                    start=f["start"],
                    end=f["end"],
                    description=f.get("description", ""),
                )
                for f in findings_raw
            ]
            events.append(
                SecurityEvent(
                    event_type=SecurityEventType(etype),
                    timestamp=ts,
                    findings=findings,
                    content_preview=preview or "",
                    action_taken=action or "",
                )
            )
        return events

    def tail_hash(self) -> str:
        """Return the hash of the last row in the chain, or empty string."""
        with self._lock:
            row = self._conn.execute(
                "SELECT row_hash FROM security_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row and row[0] else ""

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Verify the Merkle hash chain integrity.

        Returns
        -------
        tuple
            ``(True, None)`` if the chain is valid, or
            ``(False, row_id)`` where *row_id* is the first broken link.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, timestamp, event_type, findings_json,"
                " content_preview, action_taken, row_hash, prev_hash"
                " FROM security_events ORDER BY id"
            ).fetchall()

        expected_prev = ""
        for row in rows:
            rid, ts, etype, fj, preview, action, stored_hash, stored_prev = row
            # Skip rows that predate the Merkle upgrade
            if not stored_hash:
                continue
            # Verify prev_hash link
            if stored_prev != expected_prev:
                return False, rid
            # Verify row_hash
            hash_input = f"{stored_prev}|{ts}|{etype}|{fj}|{preview}|{action}"
            computed = hashlib.sha256(hash_input.encode()).hexdigest()
            if computed != stored_hash:
                return False, rid
            expected_prev = stored_hash

        return True, None

    def count(self) -> int:
        """Return the total number of logged security events."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM security_events").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self._conn.close()

    # -- EventBus handler ----------------------------------------------------

    def _on_event(self, event: Event) -> None:
        """Handle an event from the EventBus and log it."""
        data = event.data
        # Map EventType to SecurityEventType
        mapping = {
            EventType.SECURITY_SCAN: SecurityEventType.SECRET_DETECTED,
            EventType.SECURITY_ALERT: SecurityEventType.SECRET_DETECTED,
            EventType.SECURITY_BLOCK: SecurityEventType.SECRET_DETECTED,
        }
        event_type = mapping.get(event.event_type, SecurityEventType.SECRET_DETECTED)

        # Extract findings from event data if present
        findings: List[ScanFinding] = []
        for f in data.get("findings", []):
            findings.append(
                ScanFinding(
                    pattern_name=f.get("pattern", ""),
                    matched_text="",
                    threat_level=ThreatLevel(f.get("threat", "low")),
                    start=0,
                    end=0,
                    description=f.get("description", ""),
                )
            )

        sec_event = SecurityEvent(
            event_type=event_type,
            timestamp=event.timestamp,
            findings=findings,
            content_preview=data.get("content_preview", ""),
            action_taken=data.get("mode", ""),
        )
        self.log(sec_event)

__all__ = ["AuditLogger"]
