from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.runtime_paths import data_path

__all__ = ["PersonaEvolution"]

_DB_DIR = data_path("persona")


class PersonaEvolution:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DB_DIR / "evolution.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        apply_pragmas(self._conn)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS evolution_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_type TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trait_values (
                trait TEXT PRIMARY KEY,
                value REAL NOT NULL DEFAULT 0.5,
                updated_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def record_signal(self, signal_type: str, metadata: dict | None = None) -> None:
        import json
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO evolution_signals (signal_type, metadata, recorded_at) VALUES (?,?,?)",
                (signal_type, json.dumps(metadata or {}), now),
            )
            self._conn.commit()
            self._adjust_trait_from_signal(signal_type)
        logger.debug("[VECTOR][persona_evolution] signal recorded: {}", signal_type)

    def get_evolved_traits(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT trait, value FROM trait_values").fetchall()
        return {r["trait"]: r["value"] for r in rows}

    def should_deepen(self) -> bool:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM evolution_signals"
        ).fetchone()[0]
        return count > 0 and count % 50 == 0

    def get_evolution_level(self) -> float:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM evolution_signals"
        ).fetchone()[0]
        level = min(1.0, total / 500.0)
        return round(level, 3)

    def close(self) -> None:
        self._conn.close()

    def _adjust_trait_from_signal(self, signal_type: str) -> None:
        _SIGNAL_TRAIT_MAP: dict[str, str] = {
            "owner_interaction": "confidence",
            "correct_prediction": "confidence",
            "owner_correction": "adaptiveness",
            "task_completed": "reliability",
        }
        trait = _SIGNAL_TRAIT_MAP.get(signal_type)
        if not trait:
            return
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT value FROM trait_values WHERE trait=?", (trait,)
        ).fetchone()
        if existing:
            new_val = min(1.0, existing["value"] + 0.02)
            self._conn.execute(
                "UPDATE trait_values SET value=?, updated_at=? WHERE trait=?",
                (new_val, now, trait),
            )
        else:
            self._conn.execute(
                "INSERT INTO trait_values (trait, value, updated_at) VALUES (?,?,?)",
                (trait, 0.52, now),
            )
        self._conn.commit()
