"""Versioned schema migrations for the VECTOR collections engine.

Python reimplementation of PocketBase's migration runner (core/migrations_runner.go):
versioned up/down migrations tracked in a `_migrations` table, applied in id order on
bootstrap, reversible. Generalizes the PRAGMA table_info + ALTER pattern already used
one-off in vectorcode/src/migrations/v1_to_v10.py into a reusable registry.

Migrations may be registered programmatically (register / @migration) or loaded from a
directory of .py files, each defining `up(conn)` and optional `down(conn)`.
"""

from __future__ import annotations

import sys

__all__ = [
    "Migration",
    "MigrationRunner",
    "migration",
    "get_runner",
    "add_column_if_missing",
    "table_exists",
    "column_exists",
]

from pathlib import Path

import importlib.util
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from loguru import logger
from core.config import CONFIG  # noqa: F401


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── schema helpers (reusable migration primitives) ───────────────────────────
def table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f'PRAGMA table_info("{table}")'))


def add_column_if_missing(conn, table: str, column: str, col_type: str) -> bool:
    """Idempotent ALTER TABLE ADD COLUMN. Returns True if the column was added.

    `column` and `col_type` come from trusted migration code, never user input.
    """
    if column_exists(conn, table, column):
        return False
    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_type}')
    logger.debug(f"[VECTOR][migrations] added {table}.{column} {col_type}")
    return True


@dataclass
class Migration:
    id: str                              # sortable, e.g. "0001_init"
    up: Callable                         # up(conn) -> None
    down: Callable | None = None         # down(conn) -> None (optional)
    description: str = ""


# Global registry — modules import this file and call register()/@migration.
_REGISTRY: dict[str, Migration] = {}


def migration(mig_id: str, description: str = ""):
    """Decorator registering an up() function as a migration. down() can be attached
    via the returned object's .down, or registered separately."""
    def _wrap(up_fn: Callable) -> Migration:
        m = Migration(id=mig_id, up=up_fn, description=description)
        _REGISTRY[mig_id] = m
        return m
    return _wrap


class MigrationRunner:
    def __init__(self, conn=None, registry: dict[str, Migration] | None = None):
        if conn is None:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
        self.conn = conn
        self.registry = registry if registry is not None else _REGISTRY
        self._ensure_table()

    def _ensure_table(self):
        with self.conn:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS _migrations ("
                "  id TEXT PRIMARY KEY,"
                "  applied_at TEXT NOT NULL"
                ")"
            )

    def register(self, mig: Migration) -> None:
        self.registry[mig.id] = mig

    def applied_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT id FROM _migrations")}

    def pending(self) -> list[Migration]:
        done = self.applied_ids()
        return [self.registry[k] for k in sorted(self.registry) if k not in done]

    def apply_pending(self) -> list[str]:
        applied = []
        for mig in self.pending():
            try:
                with self.conn:                       # one transaction per migration
                    mig.up(self.conn)
                    self.conn.execute(
                        "INSERT INTO _migrations (id, applied_at) VALUES (?, ?)",
                        (mig.id, _now()),
                    )
                applied.append(mig.id)
                logger.info(f"[VECTOR][migrations] applied {mig.id} ({mig.description})")
            except Exception as e:
                logger.error(f"[VECTOR][migrations] FAILED {mig.id}: {e} - halting (earlier ones kept)")
                raise
        if not applied:
            logger.debug("[VECTOR][migrations] nothing to apply - schema current")
        return applied

    def revert(self, steps: int = 1) -> list[str]:
        """Revert the last `steps` applied migrations (most recent first)."""
        done = [r[0] for r in self.conn.execute(
            "SELECT id FROM _migrations ORDER BY applied_at DESC, id DESC"
        )]
        reverted = []
        for mig_id in done[:max(0, steps)]:
            mig = self.registry.get(mig_id)
            if mig is None or mig.down is None:
                logger.warning(f"[VECTOR][migrations] no down() for {mig_id} - skipping revert")
                continue
            with self.conn:
                mig.down(self.conn)
                self.conn.execute("DELETE FROM _migrations WHERE id = ?", (mig_id,))
            reverted.append(mig_id)
            logger.info(f"[VECTOR][migrations] reverted {mig_id}")
        return reverted

    def load_dir(self, directory: str | Path) -> int:
        """Load migration modules from a directory. Each .py file must define up(conn)
        and may define down(conn); the file stem becomes the migration id."""
        directory = Path(directory)
        if not directory.is_dir():
            return 0
        count = 0
        for path in sorted(directory.glob("*.py")):
            if path.stem.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(f"_vec_mig_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "up"):
                logger.warning(f"[VECTOR][migrations] {path.name} has no up() — skipped")
                continue
            self.register(Migration(
                id=path.stem,
                up=mod.up,
                down=getattr(mod, "down", None),
                description=getattr(mod, "DESCRIPTION", ""),
            ))
            count += 1
        return count


def get_runner(conn=None) -> MigrationRunner:
    return MigrationRunner(conn)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import sqlite3
    ok = True

    conn = sqlite3.connect(":memory:")
    reg: dict[str, Migration] = {}
    runner = MigrationRunner(conn, registry=reg)

    # 0001 — create a base table
    runner.register(Migration(
        id="0001_create_widgets",
        up=lambda c: c.execute("CREATE TABLE widgets (id TEXT PRIMARY KEY)"),
        down=lambda c: c.execute("DROP TABLE widgets"),
        description="create widgets",
    ))
    # 0002 — add a column using the reusable helper
    runner.register(Migration(
        id="0002_add_color",
        up=lambda c: add_column_if_missing(c, "widgets", "color", "TEXT"),
        down=lambda c: None,   # no-op (SQLite drop-column varies by version)
        description="add widgets.color",
    ))

    applied = runner.apply_pending()
    assert applied == ["0001_create_widgets", "0002_add_color"], applied
    assert table_exists(conn, "widgets")
    assert column_exists(conn, "widgets", "color")
    assert runner.applied_ids() == {"0001_create_widgets", "0002_add_color"}

    # idempotent — re-running applies nothing
    assert runner.apply_pending() == []

    # revert last → 0002 removed from ledger (down is no-op), table still there
    reverted = runner.revert(steps=1)
    assert reverted == ["0002_add_color"], reverted
    assert "0002_add_color" not in runner.applied_ids()

    # re-apply → back to current
    assert runner.apply_pending() == ["0002_add_color"]

    # full revert of 0001 drops the table
    runner.revert(steps=2)
    assert not table_exists(conn, "widgets")

    conn.close()
    print("✅ migrations.py OK" if ok else "❌ FAILED")
