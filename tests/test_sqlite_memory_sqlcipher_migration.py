"""Regression tests for OD-41 SQLiteMemory SQLCipher migration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest

from vectorcode.src.vc_tools.storage.sqlite import _USE_SQLCIPHER, SQLiteMemory

pytestmark = pytest.mark.skipif(
    not _USE_SQLCIPHER, reason="sqlcipher3 not installed in this environment"
)


def _make_plaintext_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE documents (
            id       TEXT PRIMARY KEY,
            content  TEXT NOT NULL,
            source   TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE VIRTUAL TABLE documents_fts
        USING fts5(content, source, tokenize='porter unicode61');
        """
    )
    conn.execute(
        "INSERT INTO documents (id, content, source, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            "doc-sensitive",
            "Orchid launch credentials and private notes",
            "owner-journal",
            '{"classification": "sensitive"}',
            1791331200.25,
        ),
    )
    conn.execute(
        "INSERT INTO documents_fts(rowid, content, source) "
        "SELECT rowid, content, source FROM documents"
    )
    conn.commit()
    conn.close()


def test_fresh_sqlite_memory_database_is_genuinely_encrypted(tmp_path):
    db_path = tmp_path / "fresh_memory.db"
    memory = SQLiteMemory(db_path)
    memory.store("Sensitive semantic memory", source="owner-journal")
    memory.close()

    raw = db_path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert b"Sensitive semantic memory" not in raw


def test_plaintext_sqlite_memory_migrates_with_explicit_fts_rebuild(tmp_path):
    db_path = tmp_path / "memory.db"
    _make_plaintext_db(str(db_path))

    memory = SQLiteMemory(db_path)
    row = memory._conn.execute("SELECT * FROM documents WHERE id='doc-sensitive'").fetchone()
    fts_row = memory._conn.execute(
        "SELECT rowid, content, source FROM documents_fts WHERE documents_fts MATCH ?",
        ("Orchid",),
    ).fetchone()
    results = memory.retrieve("Orchid")
    memory.close()

    assert dict(row) == {
        "id": "doc-sensitive",
        "content": "Orchid launch credentials and private notes",
        "source": "owner-journal",
        "metadata": '{"classification": "sensitive"}',
        "created_at": 1791331200.25,
    }
    assert tuple(fts_row)[1:] == (
        "Orchid launch credentials and private notes",
        "owner-journal",
    )
    assert [result.content for result in results] == [
        "Orchid launch credentials and private notes"
    ]
    assert db_path.read_bytes()[:16] != b"SQLite format 3\x00"

    backups = list(tmp_path.glob("memory.db.plaintext.bak.*"))
    assert len(backups) == 1
    backup_conn = sqlite3.connect(backups[0])
    assert backup_conn.execute("SELECT content FROM documents").fetchone()[0] == row["content"]
    backup_conn.close()

    reopened = SQLiteMemory(db_path)
    assert reopened.count() == 1
    reopened.close()
    assert len(list(tmp_path.glob("memory.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
