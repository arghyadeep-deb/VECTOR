"""Regression tests for OD-41 KnowledgeStore SQLCipher migration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest

from vectorcode.src.connectors.store import (
    _CREATE_FTS_TABLE,
    _CREATE_INDEXES,
    _CREATE_MAIN_TABLE,
    _CREATE_TRIGGERS,
    _USE_SQLCIPHER,
    KnowledgeStore,
)

pytestmark = pytest.mark.skipif(
    not _USE_SQLCIPHER, reason="sqlcipher3 not installed in this environment"
)


def _make_plaintext_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        _CREATE_MAIN_TABLE + _CREATE_FTS_TABLE + _CREATE_TRIGGERS + _CREATE_INDEXES
    )
    conn.execute(
        """INSERT INTO knowledge_chunks
           (id, doc_id, content, source, doc_type, title, author, participants,
            timestamp, thread_id, url, metadata, chunk_index, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "chunk-1",
            "doc-1",
            "Project Nightingale confidential roadmap",
            "owner-notes",
            "memo",
            "Nightingale",
            "Arghyadeep",
            '["owner"]',
            "2026-10-07T00:00:00+00:00",
            "thread-1",
            "https://example.invalid/private",
            '{"classification": "sensitive"}',
            3,
            1791331200.5,
        ),
    )
    conn.commit()
    conn.close()


def test_fresh_knowledge_database_is_genuinely_encrypted(tmp_path):
    db_path = tmp_path / "fresh_knowledge.db"
    store = KnowledgeStore(db_path)
    store.store(
        "Sensitive connector intelligence",
        source="owner-mailbox",
        doc_type="email",
        title="Private intelligence",
    )
    store.close()

    raw = db_path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert b"Sensitive connector intelligence" not in raw


def test_plaintext_knowledge_database_migrates_with_trigger_rebuilt_fts(tmp_path):
    db_path = tmp_path / "knowledge.db"
    _make_plaintext_db(str(db_path))

    store = KnowledgeStore(db_path)
    row = store._conn.execute("SELECT * FROM knowledge_chunks WHERE id='chunk-1'").fetchone()
    fts_row = store._conn.execute(
        "SELECT rowid, content, title, author FROM knowledge_fts WHERE knowledge_fts MATCH ?",
        ("Nightingale",),
    ).fetchone()
    results = store.retrieve("Nightingale")
    store.close()

    assert dict(row) == {
        "id": "chunk-1",
        "doc_id": "doc-1",
        "content": "Project Nightingale confidential roadmap",
        "source": "owner-notes",
        "doc_type": "memo",
        "title": "Nightingale",
        "author": "Arghyadeep",
        "participants": '["owner"]',
        "timestamp": "2026-10-07T00:00:00+00:00",
        "thread_id": "thread-1",
        "url": "https://example.invalid/private",
        "metadata": '{"classification": "sensitive"}',
        "chunk_index": 3,
        "created_at": 1791331200.5,
    }
    assert tuple(fts_row)[1:] == (
        "Project Nightingale confidential roadmap",
        "Nightingale",
        "Arghyadeep",
    )
    assert [result.content for result in results] == [
        "Project Nightingale confidential roadmap"
    ]
    assert db_path.read_bytes()[:16] != b"SQLite format 3\x00"

    backups = list(tmp_path.glob("knowledge.db.plaintext.bak.*"))
    assert len(backups) == 1
    backup_conn = sqlite3.connect(backups[0])
    assert backup_conn.execute("SELECT content FROM knowledge_chunks").fetchone()[0] == row["content"]
    backup_conn.close()

    reopened = KnowledgeStore(db_path)
    assert reopened.count() == 1
    reopened.close()
    assert len(list(tmp_path.glob("knowledge.db.plaintext.bak.*"))) == 1


def test_in_memory_knowledge_store_remains_supported():
    store = KnowledgeStore(":memory:")
    store.store("Transient searchable knowledge", source="test")
    assert store.count() == 1
    assert store.retrieve("Transient")[0].content == "Transient searchable knowledge"
    store.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
