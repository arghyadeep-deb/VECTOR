"""Regression tests for OD-20 MCP audit database encryption and migration."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security.mcp_security import MCPSecurityMiddleware, ToolCallRecord, _create_tables_on, _USE_SQLCIPHER

pytestmark = pytest.mark.skipif(not _USE_SQLCIPHER, reason="sqlcipher3 not installed")

_SECRET = "api_key=sk-OD20-FAKE-SECRET"


def _make_plaintext_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    _create_tables_on(conn)
    conn.execute("INSERT INTO mcp_audit_log VALUES (?, ?, ?, ?, ?, ?, ?)", (9, "run_shell", "district_test", "{'secret':'" + _SECRET + "'}", 1700000000.5, 1, "medium"))
    conn.commit()
    conn.close()


def test_fresh_mcp_audit_database_is_encrypted(tmp_path: Path) -> None:
    path = tmp_path / "mcp_audit.db"
    middleware = MCPSecurityMiddleware(path)
    middleware.audit_call(ToolCallRecord("run_shell", "district_test", {"secret": _SECRET}, 1700000000.0, True, "medium"))
    middleware.close()
    raw = path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert _SECRET.encode() not in raw


def test_plaintext_mcp_audit_database_migrates_and_reopens_once(tmp_path: Path) -> None:
    path = tmp_path / "mcp_audit.db"
    _make_plaintext_db(path)
    middleware = MCPSecurityMiddleware(path)
    calls = middleware.get_recent_calls()
    middleware.close()
    assert calls[0]["id"] == 9
    assert _SECRET in calls[0]["params"]
    backups = list(tmp_path.glob("mcp_audit.db.plaintext.bak.*"))
    assert len(backups) == 1
    plain = sqlite3.connect(str(backups[0]))
    assert _SECRET in plain.execute("SELECT params FROM mcp_audit_log").fetchone()[0]
    plain.close()
    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
    MCPSecurityMiddleware(path).close()
    assert len(list(tmp_path.glob("mcp_audit.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
