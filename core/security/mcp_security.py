"""
VECTOR MCP Security Middleware — tool classification, rate limiting, auditing.

Intercepts all MCP tool calls from district agents to:
  1. Classify tool risk (low / medium / critical)
  2. Enforce per-district and global rate limits
  3. Detect anomalous calls (unusual district-tool combinations)
  4. Audit every call to SQLite for forensics
"""
from __future__ import annotations

import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger


AUDIT_DB_PATH = Path(__file__).parent / "mcp_audit.db"
RATE_LIMIT_DISTRICT = 100
RATE_LIMIT_GLOBAL = 500
RATE_WINDOW = 60


@dataclass
class ToolCallRecord:
    tool_name: str
    source_district: str
    params: dict[str, Any]
    timestamp: float
    allowed: bool
    risk_level: str


class MCPSecurityMiddleware:
    """
    Security middleware for MCP tool calls.

    Usage:
        middleware = MCPSecurityMiddleware()
        risk = middleware.classify_tool("bash_exec")
        if middleware.check_rate_limit("district_alpha", "bash_exec"):
            middleware.audit_call(ToolCallRecord(...))
    """

    def __init__(self, db_path: str | Path = AUDIT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._risk_map: dict[str, str] = {}
        self._district_counts: dict[str, list[float]] = defaultdict(list)
        self._global_counts: list[float] = []
        self._conn: sqlite3.Connection | None = None
        self._init_db()
        self._build_risk_map()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        return self._conn

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    source_district TEXT NOT NULL,
                    params TEXT DEFAULT '{}',
                    timestamp REAL NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 1,
                    risk_level TEXT NOT NULL DEFAULT 'low'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_district
                ON mcp_audit_log(source_district)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON mcp_audit_log(timestamp)
            """)
            conn.commit()
        except Exception as e:
            logger.warning("[VECTOR][mcp] audit db init failed: {}", e)

    def _build_risk_map(self) -> None:
        self._risk_map = {
            "read": "low",
            "read_file": "low",
            "list_files": "low",
            "search_files": "low",
            "grep": "low",
            "glob": "low",
            "fetch_url": "low",
            "web_search": "low",
            "get_weather": "low",
            "get_time": "low",
            "query_memory": "low",
            "read_db": "low",
            "get_schema": "low",
            "embed_text": "low",
            "vector_search": "low",
            "translate": "low",
            "chat": "low",
            "ask_llm": "low",
            "summarize": "low",
            "paraphrase": "low",
            "write_file": "medium",
            "edit_file": "medium",
            "create_file": "medium",
            "append_file": "medium",
            "delete_file": "medium",
            "mkdir": "medium",
            "mv": "medium",
            "cp": "medium",
            "run_python": "medium",
            "run_shell": "medium",
            "npm_install": "medium",
            "pip_install": "medium",
            "git_commit": "medium",
            "git_push": "medium",
            "git_branch": "medium",
            "http_post": "medium",
            "http_put": "medium",
            "http_delete": "medium",
            "send_email": "medium",
            "post_message": "medium",
            "bash_exec": "critical",
            "shell_exec": "critical",
            "exec_command": "critical",
            "admin_exec": "critical",
            "sudo_run": "critical",
            "drop_db": "critical",
            "delete_volume": "critical",
            "rm_rf": "critical",
            "shutdown": "critical",
            "restart": "critical",
            "overwrite_config": "critical",
            "modify_policy": "critical",
            "grant_access": "critical",
            "revoke_access": "critical",
        }

    def classify_tool(self, tool_name: str) -> str:
        if tool_name in self._risk_map:
            return self._risk_map[tool_name]
        for prefix, risk in [("read_", "low"), ("get_", "low"), ("list_", "low"),
                              ("write_", "medium"), ("create_", "medium"),
                              ("delete_", "medium"), ("exec_", "critical"),
                              ("admin_", "critical"), ("sudo_", "critical")]:
            if tool_name.startswith(prefix):
                return risk
        return "medium"

    def check_rate_limit(self, source_district: str, tool_name: str) -> bool:
        now = time.time()
        cutoff = now - RATE_WINDOW

        self._district_counts[source_district] = [
            t for t in self._district_counts[source_district] if t > cutoff
        ]
        self._global_counts = [t for t in self._global_counts if t > cutoff]

        if len(self._district_counts[source_district]) >= RATE_LIMIT_DISTRICT:
            logger.warning(
                "[VECTOR][mcp] rate limit district {} ({} calls/{})",
                source_district, RATE_LIMIT_DISTRICT, RATE_WINDOW,
            )
            return False

        if len(self._global_counts) >= RATE_LIMIT_GLOBAL:
            logger.warning(
                "[VECTOR][mcp] global rate limit ({} calls/{})",
                RATE_LIMIT_GLOBAL, RATE_WINDOW,
            )
            return False

        self._district_counts[source_district].append(now)
        self._global_counts.append(now)
        return True

    def detect_anomalous_call(
        self,
        tool_name: str,
        source_district: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        risk = self.classify_tool(tool_name)

        if risk == "critical":
            try:
                conn = self._get_conn()
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM mcp_audit_log "
                    "WHERE source_district = ? AND tool_name = ? AND timestamp > ?",
                    (source_district, tool_name, time.time() - 3600),
                ).fetchone()
                if row and row[0] == 0:
                    logger.warning(
                        "[VECTOR][mcp] anomalous: {} ({}) first critical call from {}",
                        tool_name, risk, source_district,
                    )
                    return True
            except Exception as e:
                logger.warning("[VECTOR][mcp] anomaly check failed: {}", e)

        if risk == "low":
            return False

        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM mcp_audit_log "
                "WHERE source_district = ? AND timestamp > ?",
                (source_district, time.time() - 86400),
            ).fetchone()
            total_calls = row[0] if row else 0
            if total_calls < 5 and risk in ("medium", "critical"):
                logger.warning(
                    "[VECTOR][mcp] anomalous: {} from young district {} ({} total calls)",
                    tool_name, source_district, total_calls,
                )
                return True
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

        return False

    def audit_call(self, record: ToolCallRecord) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO mcp_audit_log "
                "(tool_name, source_district, params, timestamp, allowed, risk_level) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.tool_name,
                    record.source_district,
                    str(record.params),
                    record.timestamp,
                    1 if record.allowed else 0,
                    record.risk_level,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning("[VECTOR][mcp] audit call failed: {}", e)

    def get_recent_calls(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM mcp_audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("[VECTOR][mcp] get_recent_calls failed: {}", e)
            return []

    def get_anomaly_report(self) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        try:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT source_district, tool_name, risk_level, COUNT(*) as cnt
                FROM mcp_audit_log
                WHERE timestamp > ?
                GROUP BY source_district, tool_name
                HAVING cnt > 20
                ORDER BY cnt DESC
                LIMIT 10
            """, (time.time() - 3600,)).fetchall()
            for r in rows:
                anomalies.append({
                    "type": "high_volume",
                    "district": r["source_district"],
                    "tool": r["tool_name"],
                    "risk": r["risk_level"],
                    "count": r["cnt"],
                })

            rows2 = conn.execute("""
                SELECT source_district, risk_level, COUNT(*) as cnt
                FROM mcp_audit_log
                WHERE timestamp > ?
                AND risk_level = 'critical'
                AND allowed = 1
                GROUP BY source_district
                ORDER BY cnt DESC
                LIMIT 10
            """, (time.time() - 3600,)).fetchall()
            for r in rows2:
                anomalies.append({
                    "type": "critical_call_cluster",
                    "district": r["source_district"],
                    "risk": r["risk_level"],
                    "count": r["cnt"],
                })
        except Exception as e:
            logger.warning("[VECTOR][mcp] anomaly report failed: {}", e)
        return anomalies


_middleware: MCPSecurityMiddleware | None = None


def get_mcp_security() -> MCPSecurityMiddleware:
    global _middleware
    if _middleware is None:
        _middleware = MCPSecurityMiddleware()
    return _middleware


if __name__ == "__main__":
    mw = MCPSecurityMiddleware(db_path=":memory:")

    assert mw.classify_tool("read_file") == "low"
    assert mw.classify_tool("write_file") == "medium"
    assert mw.classify_tool("bash_exec") == "critical"
    assert mw.classify_tool("unknown_tool") == "medium"

    ok = mw.check_rate_limit("test_district", "read_file")
    assert ok is True

    record = ToolCallRecord(
        tool_name="read_file",
        source_district="test_district",
        params={"path": "/etc/hosts"},
        timestamp=time.time(),
        allowed=True,
        risk_level="low",
    )
    mw.audit_call(record)

    recent = mw.get_recent_calls(limit=5)
    assert len(recent) >= 1
    assert recent[0]["tool_name"] == "read_file"

    anomalies = mw.get_anomaly_report()
    assert isinstance(anomalies, list)

    anomalous = mw.detect_anomalous_call("read_file", "test_district", {})
    assert anomalous is False

    print("OK mcp_security.py — classification, rate limit, audit, anomaly detection verified")
