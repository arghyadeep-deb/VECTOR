"""Regression tests for OD-41 DigestStore SQLCipher migration."""
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3

import pytest

from vectorcode.src.vc_agents.digest_store import (
    _USE_SQLCIPHER,
    DigestArtifact,
    DigestStore,
)

pytestmark = pytest.mark.skipif(
    not _USE_SQLCIPHER, reason="sqlcipher3 not installed in this environment"
)


def _make_plaintext_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            audio_path TEXT NOT NULL,
            sections TEXT NOT NULL,
            sources_used TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            model_used TEXT NOT NULL,
            voice_used TEXT NOT NULL,
            quality_score REAL NOT NULL DEFAULT 0.0,
            evaluator_feedback TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """INSERT INTO digests
           (text, audio_path, sections, sources_used, generated_at, model_used,
            voice_used, quality_score, evaluator_feedback)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "Confidential acquisition digest",
            "private/digest.wav",
            '{"finance": "Quarterly plan"}',
            '["owner-mailbox"]',
            "2026-10-07T06:30:00+00:00",
            "vector-focus",
            "bf_emma",
            0.91,
            "Owner-only evaluation",
        ),
    )
    conn.commit()
    conn.close()


def test_fresh_digest_database_is_genuinely_encrypted(tmp_path):
    db_path = tmp_path / "fresh_digest.db"
    store = DigestStore(str(db_path))
    store.save(
        DigestArtifact(
            text="Sensitive morning strategy",
            audio_path=Path("private/morning.wav"),
            sections={"strategy": "Private launch"},
            sources_used=["owner-mailbox"],
            generated_at=datetime.now(UTC),
            model_used="vector-focus",
            voice_used="bf_emma",
        )
    )
    store.close()

    raw = db_path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert b"Sensitive morning strategy" not in raw


def test_plaintext_digest_database_migrates_once_and_preserves_backup(tmp_path):
    db_path = tmp_path / "digest.db"
    _make_plaintext_db(str(db_path))

    store = DigestStore(str(db_path))
    artifact = store.get_latest()
    store.close()

    assert artifact is not None
    assert artifact.text == "Confidential acquisition digest"
    assert artifact.audio_path == Path("private/digest.wav")
    assert artifact.sections == {"finance": "Quarterly plan"}
    assert artifact.sources_used == ["owner-mailbox"]
    assert artifact.generated_at.isoformat() == "2026-10-07T06:30:00+00:00"
    assert artifact.model_used == "vector-focus"
    assert artifact.voice_used == "bf_emma"
    assert artifact.quality_score == pytest.approx(0.91)
    assert artifact.evaluator_feedback == "Owner-only evaluation"
    assert db_path.read_bytes()[:16] != b"SQLite format 3\x00"

    backups = list(tmp_path.glob("digest.db.plaintext.bak.*"))
    assert len(backups) == 1
    backup_conn = sqlite3.connect(backups[0])
    row = backup_conn.execute(
        "SELECT text, evaluator_feedback FROM digests"
    ).fetchone()
    backup_conn.close()
    assert row == ("Confidential acquisition digest", "Owner-only evaluation")

    reopened = DigestStore(str(db_path))
    assert reopened.get_latest() is not None
    reopened.close()
    assert len(list(tmp_path.glob("digest.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
