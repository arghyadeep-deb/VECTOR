"""Regression tests for OD-20 email database encryption and migration."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.email.schema import get_connection, init_schema, _create_schema_on, _USE_SQLCIPHER

pytestmark = pytest.mark.skipif(not _USE_SQLCIPHER, reason="sqlcipher3 not installed")

_ADDRESS = "alice.od20@example.test"


def _make_plaintext_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    _create_schema_on(conn)
    conn.execute(
        "INSERT INTO emails (id, folder_id, subject, sender, recipient, date, body) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("mail-1", "inbox", "OD-20", _ADDRESS, "owner@example.test", "2026-10-07", "private body"),
    )
    conn.execute(
        "INSERT INTO attachments (id, email_id, filename, mimetype, size) VALUES (?, ?, ?, ?, ?)",
        ("att-1", "mail-1", "private.txt", "text/plain", 12),
    )
    conn.commit()
    conn.close()


def test_fresh_email_database_is_encrypted(tmp_path: Path) -> None:
    path = tmp_path / "email.db"
    init_schema(path)
    conn = get_connection(path)
    conn.execute(
        "INSERT INTO emails (id, folder_id, sender, recipient, body) VALUES (?, ?, ?, ?, ?)",
        ("mail-fresh", "inbox", _ADDRESS, "owner@example.test", "secret correspondence"),
    )
    conn.commit()
    conn.close()
    raw = path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert _ADDRESS.encode() not in raw


def test_plaintext_email_database_migrates_and_reopens_once(tmp_path: Path) -> None:
    path = tmp_path / "email.db"
    _make_plaintext_db(path)
    assert path.read_bytes()[:16] == b"SQLite format 3\x00"

    conn = get_connection(path)
    email = tuple(conn.execute("SELECT id, sender, body FROM emails").fetchone())
    attachment = tuple(conn.execute("SELECT id, filename, size FROM attachments").fetchone())
    conn.close()
    assert email == ("mail-1", _ADDRESS, "private body")
    assert attachment == ("att-1", "private.txt", 12)
    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
    backups = list(tmp_path.glob("email.db.plaintext.bak.*"))
    assert len(backups) == 1
    plain = sqlite3.connect(str(backups[0]))
    assert plain.execute("SELECT sender FROM emails").fetchone()[0] == _ADDRESS
    plain.close()

    reopened = get_connection(path)
    assert reopened.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 1
    reopened.close()
    assert len(list(tmp_path.glob("email.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
