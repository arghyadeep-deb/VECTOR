"""Regression tests for OD-20 persona evolution DB encryption and migration."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.persona.evolution import PersonaEvolution, _create_tables_on, _USE_SQLCIPHER

pytestmark = pytest.mark.skipif(not _USE_SQLCIPHER, reason="sqlcipher3 not installed")

_SENSITIVE = "owner-secret-correction-OD20"


def _make_plaintext_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    _create_tables_on(conn)
    conn.execute("INSERT INTO evolution_signals VALUES (?, ?, ?, ?)", (7, "owner_correction", '{"note":"' + _SENSITIVE + '"}', "2026-10-07"))
    conn.execute("INSERT INTO trait_values VALUES (?, ?, ?)", ("adaptiveness", 0.72, "2026-10-07"))
    conn.commit()
    conn.close()


def test_fresh_persona_evolution_database_is_encrypted(tmp_path: Path) -> None:
    path = tmp_path / "evolution.db"
    evolution = PersonaEvolution(path)
    evolution.record_signal("owner_interaction", {"note": _SENSITIVE})
    evolution.close()
    raw = path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert _SENSITIVE.encode() not in raw


def test_plaintext_persona_evolution_migrates_and_reopens_once(tmp_path: Path) -> None:
    path = tmp_path / "evolution.db"
    _make_plaintext_db(path)
    evolution = PersonaEvolution(path)
    assert evolution.get_evolved_traits() == {"adaptiveness": pytest.approx(0.72)}
    assert evolution._conn.execute("SELECT id, metadata FROM evolution_signals").fetchone()[0] == 7
    evolution.close()
    backups = list(tmp_path.glob("evolution.db.plaintext.bak.*"))
    assert len(backups) == 1
    plain = sqlite3.connect(str(backups[0]))
    assert _SENSITIVE in plain.execute("SELECT metadata FROM evolution_signals").fetchone()[0]
    plain.close()
    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
    PersonaEvolution(path).close()
    assert len(list(tmp_path.glob("evolution.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
