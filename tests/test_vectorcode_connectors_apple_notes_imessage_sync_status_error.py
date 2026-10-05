"""Regression for vectorcode/src/connectors/{apple_notes,imessage}.py:

Same bug shape as the oura/weather/hackernews/granola fix: SyncStatus.state
defaults to "idle", which is also the value these connectors' sync()
produced on success, and neither wrapped its query/iteration body in
try/except. A mid-sync exception (locked DB, missing table from a macOS
schema change) left sync_status() permanently reporting state="idle" with
no error -- indistinguishable from "nothing synced yet".

Fixed: both sync() methods now set self._last_error on exception (re-raised
unchanged) and clear it to None on success; sync_status() surfaces it.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.apple_notes import AppleNotesConnector
from vectorcode.src.connectors.imessage import IMessageConnector


def _make_broken_db(path: Path) -> None:
    # A real, openable SQLite file that is missing the tables the
    # connector's SELECT statements expect -- triggers sqlite3.OperationalError
    # from *inside* the try block (table scan), not from connect() itself.
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()


def test_apple_notes_sync_failure_reports_error_status(tmp_path):
    db_path = tmp_path / "NoteStore.sqlite"
    _make_broken_db(db_path)
    connector = AppleNotesConnector(db_path=str(db_path))

    assert connector.sync_status().state == "idle"

    with __import__("pytest").raises(sqlite3.OperationalError):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error is not None


def test_imessage_sync_failure_reports_error_status(tmp_path):
    db_path = tmp_path / "chat.db"
    _make_broken_db(db_path)
    connector = IMessageConnector(db_path=str(db_path))

    with __import__("pytest").raises(sqlite3.OperationalError):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error is not None


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
