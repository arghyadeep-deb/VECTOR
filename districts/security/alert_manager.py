
from core.memory.db_utils import apply_pragmas
import sys
from pathlib import Path

import asyncio
import datetime
import json
import sqlite3
import uuid
import threading
from collections import defaultdict
from typing import Any

import httpx

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from pydantic import BaseModel, Field

from core.config import CONFIG
from core.city.agent_base import AgentBase

class Alert(BaseModel):
    id: str
    rule_name: str
    severity: int
    target: str = ""
    message: str
    status: str = "NEW"
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    resolved_at: datetime.datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

_STATUSES = {"NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"}

class AlertManager(AgentBase):
    def __init__(self, db_path: str | None = None):
        super().__init__(str(uuid.uuid4()), "AlertManager", "security")
        self.capabilities = ["RESOLVED", "acknowledge", "alert", "digest", "escalate", "list_alerts", "resolve", "security", "security_scan", "stats"]
        from core.runtime_paths import data_path

        self._db_path = db_path or str(data_path("security", "alerts.db"))
        self._lock = threading.RLock()
        self._dedup_cache: dict[str, float] = {}
        self._dedup_ttl: float = 300.0
        self._pushover_token: str = CONFIG.get("api_keys", {}).get("pushover_token", "") or CONFIG.get("pushover_token", "")
        self._pushover_user: str = CONFIG.get("api_keys", {}).get("pushover_user", "") or CONFIG.get("pushover_user", "")
        self._incident_queue: asyncio.Queue[dict] | None = None
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(self._db_path, timeout=5, check_same_thread=False)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    rule_name TEXT NOT NULL,
                    severity INTEGER NOT NULL,
                    target TEXT DEFAULT '',
                    message TEXT NOT NULL,
                    status TEXT DEFAULT 'NEW',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    evidence TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_rule_target ON alerts(rule_name, target)")
            conn.commit()
            conn.close()
            logger.info("[VECTOR][alert_manager] SQLite ready at {}", self._db_path)
        except Exception as e:
            logger.error("[VECTOR][alert_manager] DB init: {}", e)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        apply_pragmas(conn)
        return conn

    def _dedup_key(self, rule_name: str, target: str) -> str:
        return f"{rule_name}:{target}"

    def set_incident_queue(self, queue: asyncio.Queue[dict]) -> None:
        self._incident_queue = queue

    def create_alert(self, rule_match: Any) -> Alert | None:
        rule_name = getattr(rule_match, "rule_name", "unknown")
        severity = getattr(rule_match, "severity", 5)
        evidence = getattr(rule_match, "evidence", {})
        target = evidence.get("target", "") if isinstance(evidence, dict) else ""
        dkey = self._dedup_key(rule_name, target)
        now = datetime.datetime.now(datetime.timezone.utc)
        if dkey in self._dedup_cache:
            if (now.timestamp() - self._dedup_cache[dkey]) < self._dedup_ttl:
                logger.debug("[VECTOR][alert_manager] dedup: {} already alerted", dkey)
                return None
        alert = Alert(
            id=str(uuid.uuid4()),
            rule_name=rule_name,
            severity=severity,
            target=target,
            message=getattr(rule_match, "suggested_action", "") or f"{rule_name} triggered",
            evidence=evidence,
        )
        if not self._store_alert(alert):
            logger.error(
                "[VECTOR][alert_manager] alert {} not created because persistence failed",
                alert.id[:8],
            )
            return None
        self._dedup_cache[dkey] = now.timestamp()
        logger.info("[VECTOR][alert_manager] alert created: {} (sev={})", alert.id[:8], severity)
        if severity >= 7:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._send_pushover(alert))
            except RuntimeError:
                logger.warning("[VECTOR][alert_manager] no event loop for pushover")
        if self._incident_queue and severity >= 8:
            try:
                self._incident_queue.put_nowait({
                    "rule_name": rule_name,
                    "evidence": evidence,
                    "alert_id": alert.id,
                })
            except asyncio.QueueFull:
                logger.warning("[VECTOR][alert_manager] incident queue full")
        return alert

    def _store_alert(self, alert: Alert) -> bool:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO alerts (id, rule_name, severity, target, message, status, created_at, resolved_at, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (alert.id, alert.rule_name, alert.severity, alert.target, alert.message,
                 alert.status, alert.created_at.isoformat(), None, json.dumps(alert.evidence)),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("[VECTOR][alert_manager] store error: {}", e)
            return False

    async def _send_pushover(self, alert: Alert) -> None:
        if not self._pushover_token or not self._pushover_user:
            logger.warning("[VECTOR][alert_manager] Pushover not configured")
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.pushover.net/1/messages.json",
                    data={
                        "token": self._pushover_token,
                        "user": self._pushover_user,
                        "title": f"VECTOR Alert: {alert.rule_name} (sev={alert.severity})",
                        "message": alert.message[:500],
                        "priority": 1 if alert.severity >= 9 else 0,
                    },
                )
                logger.info("[VECTOR][alert_manager] Pushover sent: {}", resp.status_code)
        except Exception as e:
            logger.error("[VECTOR][alert_manager] Pushover failed: {}", e)

    def acknowledge(self, alert_id: str) -> bool:
        return self._update_status(alert_id, "ACKNOWLEDGED")

    def resolve(self, alert_id: str) -> bool:
        return self._update_status(alert_id, "RESOLVED")

    def escalate(self, alert_id: str) -> bool:
        return self._update_status(alert_id, "INVESTIGATING")

    def _update_status(self, alert_id: str, status: str) -> bool:
        if status not in _STATUSES:
            return False
        try:
            conn = self._get_conn()
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if status in ("RESOLVED", "CLOSED"):
                conn.execute("UPDATE alerts SET status = ?, resolved_at = ? WHERE id = ?", (status, now, alert_id))
            else:
                conn.execute("UPDATE alerts SET status = ? WHERE id = ?", (status, alert_id))
            conn.commit()
            affected = conn.total_changes
            conn.close()
            return affected > 0
        except Exception as e:
            logger.error("[VECTOR][alert_manager] update status error: {}", e)
            return False

    def get_alerts(self, status: str | None = None, severity_ge: int | None = None, limit: int = 100) -> list[dict]:
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if status:
                clauses.append("status = ?")
                params.append(status.upper())
            if severity_ge is not None:
                clauses.append("severity >= ?")
                params.append(severity_ge)
            where = " AND ".join(clauses) if clauses else "1=1"
            conn = self._get_conn()
            cursor = conn.execute(
                f"SELECT * FROM alerts WHERE {where} ORDER BY created_at DESC LIMIT ?",
                (*params, limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error("[VECTOR][alert_manager] query error: {}", e)
            return []

    def get_stats(self) -> dict:
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT severity, COUNT(*) as count FROM alerts GROUP BY severity")
            by_severity = {str(row[0]): row[1] for row in cursor.fetchall()}
            cursor = conn.execute("SELECT status, COUNT(*) as count FROM alerts GROUP BY status")
            by_status = {row[0]: row[1] for row in cursor.fetchall()}
            cursor = conn.execute("SELECT COUNT(*) FROM alerts")
            total = cursor.fetchone()[0]
            conn.close()
            return {"total": total, "by_severity": by_severity, "by_status": by_status}
        except Exception as e:
            logger.error("[VECTOR][alert_manager] stats error: {}", e)
            return {"total": 0, "by_severity": {}, "by_status": {}}

    def get_digest(self, hours: int = 24) -> dict:
        try:
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT rule_name, severity, COUNT(*) as count FROM alerts WHERE created_at >= ? GROUP BY rule_name, severity ORDER BY count DESC",
                (cutoff,),
            )
            top_rules = [{"rule": row[0], "severity": row[1], "count": row[2]} for row in cursor.fetchall()]
            cursor = conn.execute("SELECT COUNT(*) FROM alerts WHERE created_at >= ?", (cutoff,))
            total = cursor.fetchone()[0]
            conn.close()
            return {"hours": hours, "total_alerts": total, "top_rules": top_rules[:10]}
        except Exception as e:
            logger.error("[VECTOR][alert_manager] digest error: {}", e)
            return {"hours": hours, "total_alerts": 0, "top_rules": []}

    async def run(self, task: dict | None = None) -> dict:
        task = task or {}
        task_type = task.get("type") or "stats"
        params = task.get("params") or {}
        supported = ["acknowledge", "digest", "escalate", "list_alerts", "resolve", "stats"]

        if task_type in ("stats", "get_stats"):
            return {"status": "ok", **self.get_stats()}
        if task_type in ("list_alerts", "get_alerts"):
            return {"status": "ok", "alerts": self.get_alerts(**params)}
        if task_type == "digest":
            return {"status": "ok", "digest": self.get_digest(**params)}
        if task_type == "acknowledge":
            return {"status": "ok", "updated": self.acknowledge(params.get("alert_id", ""))}
        if task_type == "resolve":
            return {"status": "ok", "updated": self.resolve(params.get("alert_id", ""))}
        if task_type == "escalate":
            return {"status": "ok", "updated": self.escalate(params.get("alert_id", ""))}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "are there any security alerts I should know about right now?"
        # previously hit the bare "unhandled type" error stub. Route it to
        # the READ-ONLY, no-required-argument list_alerts/digest/stats
        # capabilities — never acknowledge/resolve/escalate a real alert
        # from unmatched free text.
        query = (
            params.get("query") or params.get("content")
            or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            if any(w in q for w in ("digest", "last 24", "past day", "today")):
                return {"status": "ok", "digest": self.get_digest()}
            if any(w in q for w in ("alert", "know about", "should i")):
                return {"status": "ok", "alerts": self.get_alerts(limit=params.get("limit", 20))}
            return {"status": "ok", **self.get_stats()}

        return {
            "status": "error",
            "error": f"unhandled type: {task_type}",
            "supported": supported,
        }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile
    from dataclasses import dataclass
    @dataclass
    class FakeMatch:
        rule_name: str
        severity: int
        evidence: dict
        suggested_action: str = ""

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    am = AlertManager(db_path=tmp.name)
    m = FakeMatch(rule_name="test_rule", severity=8, evidence={"target": "1.2.3.4"})
    a = am.create_alert(m)
    stats = am.get_stats()
    tmp.close()
    Path(tmp.name).unlink(missing_ok=True)
    print(f"AlertManager OK — alert={'created' if a else 'deduped'}, stats={stats}")
    print("alert_manager.py OK")
