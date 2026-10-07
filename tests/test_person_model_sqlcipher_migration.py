"""
Regression guard for owner-decision-backlog item OD-19:
core/brain/person_model.py was opening a plain, unencrypted sqlite3
connection to store real third-party PII (name, email, relationship_type,
trust_score, free-text beliefs/preferences/interaction summaries) for every
real person VECTOR interacts with. Fixed by routing through SQLCipher
(same AES-256 scheme and key as core.memory.episodic) with an automatic,
backup-preserving, one-time migration of any pre-existing plaintext
database.

These tests prove, against real files on disk (no mocks), that:
1. A fresh PersonModel database is genuinely encrypted (header + raw bytes).
2. An existing plaintext database is migrated automatically on open.
3. Migration preserves every row exactly.
4. The original plaintext file is never deleted -- only backed up.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import tempfile

import pytest

from core.brain.person_model import PersonModel, _USE_SQLCIPHER

pytestmark = pytest.mark.skipif(
    not _USE_SQLCIPHER, reason="sqlcipher3 not installed in this environment"
)


def _make_plaintext_db(path: str) -> None:
    """Build a plaintext DB using PersonModel's own schema, bypassing the
    SQLCipher path entirely -- simulates a pre-fix database on disk."""
    conn = sqlite3.connect(path)
    PersonModel._create_tables_on(conn)
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """INSERT INTO persons (id, name, email, relationship_type, trust_score, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("bob_002", "Bob Jones", "bob@example.com", "acquaintance", 0.6, "{}", now, now),
    )
    conn.execute(
        """INSERT INTO person_beliefs (id, person_id, topic, belief, confidence, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("belief_1", "bob_002", "privacy", "cares about data protection", 0.8, now),
    )
    conn.commit()
    conn.close()


def test_fresh_database_is_genuinely_encrypted(tmp_path):
    db_path = str(tmp_path / "fresh_person_models.db")
    pm = PersonModel(db_path)
    pm.add_person("alice_001", "Alice Smith", "colleague", email="alice@example.com")
    pm.close()

    with open(db_path, "rb") as f:
        header = f.read(16)
        f.seek(0)
        raw = f.read()

    assert header != b"SQLite format 3\x00", "file is still plaintext SQLite -- encryption did not apply"
    assert b"Alice Smith" not in raw, "name leaked into raw file bytes"
    assert b"alice@example.com" not in raw, "email leaked into raw file bytes"


def test_plaintext_database_is_migrated_automatically_on_open(tmp_path):
    db_path = str(tmp_path / "person_models.db")
    _make_plaintext_db(db_path)

    with open(db_path, "rb") as f:
        assert f.read(16) == b"SQLite format 3\x00", "setup helper did not produce a plaintext DB"

    pm = PersonModel(db_path)
    try:
        model = pm.get_model("bob_002")
        assert model is not None, "data lost during migration"
        assert model["name"] == "Bob Jones"
        assert model["email"] == "bob@example.com"
        assert model["relationship_type"] == "acquaintance"
        assert model["trust_score"] == pytest.approx(0.6)
        assert model["beliefs"]["privacy"]["belief"] == "cares about data protection"
    finally:
        pm.close()

    with open(db_path, "rb") as f:
        assert f.read(16) != b"SQLite format 3\x00", "main file was not encrypted after migration"

    backups = list(tmp_path.glob("person_models.db.plaintext.bak.*"))
    assert len(backups) == 1, "expected exactly one plaintext backup to be preserved"

    backup_conn = sqlite3.connect(str(backups[0]))
    row = backup_conn.execute("SELECT name, email FROM persons WHERE id='bob_002'").fetchone()
    backup_conn.close()
    assert row == ("Bob Jones", "bob@example.com"), "original plaintext backup was altered or deleted"


def test_migration_is_only_triggered_once(tmp_path):
    db_path = str(tmp_path / "person_models.db")
    _make_plaintext_db(db_path)

    pm1 = PersonModel(db_path)
    pm1.close()
    backups_after_first_open = list(tmp_path.glob("person_models.db.plaintext.bak.*"))
    assert len(backups_after_first_open) == 1

    pm2 = PersonModel(db_path)
    try:
        assert pm2.get_model("bob_002") is not None
    finally:
        pm2.close()

    backups_after_second_open = list(tmp_path.glob("person_models.db.plaintext.bak.*"))
    assert len(backups_after_second_open) == 1, "re-opening an already-encrypted DB must not re-migrate"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
