"""Regression tests for OD-20 contacts database encryption and migration."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.relationships.schema import get_connection, init_schema, _create_tables_on, _USE_SQLCIPHER

pytestmark = pytest.mark.skipif(not _USE_SQLCIPHER, reason="sqlcipher3 not installed")

_PHONE = "+91-90000-OD20"


def _make_plaintext_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    _create_tables_on(conn)
    conn.execute("INSERT INTO contacts VALUES (?, ?, ?, ?, ?, ?, ?)", ("Alice", _PHONE, "alice@example.test", "private", "a", "b", 1))
    conn.execute("INSERT INTO interactions (contact_name, interaction_type, content, timestamp) VALUES (?, ?, ?, ?)", ("Alice", "call", "private discussion", "c"))
    conn.commit()
    conn.close()


def test_fresh_contacts_database_is_encrypted(tmp_path: Path) -> None:
    path = tmp_path / "contacts.db"
    init_schema(path)
    conn = get_connection(path)
    conn.execute("INSERT INTO contacts (name, phone) VALUES (?, ?)", ("Alice", _PHONE))
    conn.commit()
    conn.close()
    raw = path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert _PHONE.encode() not in raw


def test_plaintext_contacts_database_migrates_and_reopens_once(tmp_path: Path) -> None:
    path = tmp_path / "contacts.db"
    _make_plaintext_db(path)
    conn = get_connection(path)
    assert tuple(conn.execute("SELECT name, phone, contact_count FROM contacts").fetchone()) == ("Alice", _PHONE, 1)
    assert tuple(conn.execute("SELECT contact_name, content FROM interactions").fetchone()) == ("Alice", "private discussion")
    conn.close()
    backups = list(tmp_path.glob("contacts.db.plaintext.bak.*"))
    assert len(backups) == 1
    plain = sqlite3.connect(str(backups[0]))
    assert plain.execute("SELECT phone FROM contacts").fetchone()[0] == _PHONE
    plain.close()
    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
    reopened = get_connection(path)
    reopened.close()
    assert len(list(tmp_path.glob("contacts.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
