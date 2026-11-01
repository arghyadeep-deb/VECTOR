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

from loguru import logger
from pydantic import BaseModel, Field

from core.config import CONFIG
from core.city.agent_base import AgentBase


class LogEvent(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    service: str
    correlation_id: str | None = None
    level: str = "INFO"
    message: str
    module: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "timestamp": self.timestamp.isoformat(),
            "service": self.service,
            "correlation_id": self.correlation_id or "",
            "level": self.level,
            "message": self.message,
            "module": self.module,
            "extra": json.dumps(self.extra),
        }


class LogAggregator(AgentBase):
    def __init__(self, db_path: str | None = None):
        super().__init__(str(uuid.uuid4()), "LogAggregator", "security")
        self.capabilities = ["WARNING", "audit_log", "audit_search", "audit_tail", "log", "prune_retention", "query", "security", "stats"]
        from core.runtime_paths import data_path

        self._db_path = db_path or str(data_path("security", "logs.db"))
        self._lock = threading.RLock()
        self._queue: asyncio.Queue[LogEvent] = asyncio.Queue(maxsize=10000)
        self._forward_queue: asyncio.Queue[LogEvent] | None = None
        self._running = False
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(self._db_path, timeout=5, check_same_thread=False)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    correlation_id TEXT DEFAULT '',
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT DEFAULT '',
                    extra TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_service ON logs(service)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
            conn.commit()
            conn.close()
            logger.info("[VECTOR][log_aggregator] SQLite DB ready at {}", self._db_path)
        except Exception as e:
            logger.error("[VECTOR][log_aggregator] DB init failed: {}", e)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        apply_pragmas(conn)
        return conn

    def make_sink(self) -> Any:
        def sink(message) -> None:
            try:
                record = message.record
                event = LogEvent(
                    service=record.get("name", "unknown"),
                    level=record["level"].name,
                    message=record["message"],
                    module=record.get("module", ""),
                    extra=record.get("extra", {}),
                )
                self._queue.put_nowait(event)
            except Exception:
                logger.opt(exception=True).debug("[VECTOR][log_aggregator] sink rejected log event")
        return sink

    def ingest(self, event: LogEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("[VECTOR][log_aggregator] queue full — dropping event")

    async def process_loop(self) -> None:
        self._running = True
        logger.info("[VECTOR][log_aggregator] process loop started")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                self._store_event(event)
                if self._forward_queue and event.level in ("WARNING", "ERROR", "CRITICAL"):
                    try:
                        self._forward_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.opt(exception=True).debug(
                            "[VECTOR][log_aggregator] forward queue full; event not forwarded"
                        )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("[VECTOR][log_aggregator] process error: {}", e)

    def _store_event(self, event: LogEvent) -> None:
        try:
            row = event.to_row()
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO logs (id, timestamp, service, correlation_id, level, message, module, extra) "
                "VALUES (:id, :timestamp, :service, :correlation_id, :level, :message, :module, :extra)",
                row,
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("[VECTOR][log_aggregator] store error: {}", e)

    def set_forward_queue(self, queue: asyncio.Queue[LogEvent]) -> None:
        self._forward_queue = queue

    def query(
        self,
        start: str | None = None,
        end: str | None = None,
        level: str | None = None,
        service: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        try:
            clauses: list[str] = []
            params: dict[str, Any] = {}
            if start:
                clauses.append("timestamp >= :start")
                params["start"] = start
            if end:
                clauses.append("timestamp <= :end")
                params["end"] = end
            if level:
                clauses.append("level = :level")
                params["level"] = level.upper()
            if service:
                clauses.append("service = :service")
                params["service"] = service
            where = " AND ".join(clauses) if clauses else "1=1"
            conn = self._get_conn()
            cursor = conn.execute(
                f"SELECT * FROM logs WHERE {where} ORDER BY timestamp DESC LIMIT ?",
                (*params.values(), limit),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error("[VECTOR][log_aggregator] query error: {}", e)
            return []

    def get_stats(self) -> dict:
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT level, COUNT(*) as count FROM logs GROUP BY level")
            by_level = {row[0]: row[1] for row in cursor.fetchall()}
            cursor = conn.execute("SELECT service, COUNT(*) as count FROM logs GROUP BY service ORDER BY count DESC LIMIT 10")
            by_service = {row[0]: row[1] for row in cursor.fetchall()}
            cursor = conn.execute("SELECT COUNT(*) FROM logs")
            total = cursor.fetchone()[0]
            conn.close()
            return {"total": total, "by_level": by_level, "by_service": by_service}
        except Exception as e:
            logger.error("[VECTOR][log_aggregator] stats error: {}", e)
            return {"total": 0, "by_level": {}, "by_service": {}}

    def prune_retention(self, days: int = 30) -> int:
        try:
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM logs WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            if deleted:
                logger.info("[VECTOR][log_aggregator] pruned {} logs older than {} days", deleted, days)
            return deleted
        except Exception as e:
            logger.error("[VECTOR][log_aggregator] prune error: {}", e)
            return 0

    def stop(self) -> None:
        self._running = False

    async def run(self, task: dict | None = None) -> dict:
        task = task or {}
        task_type = task.get("type") or "stats"
        params = task.get("params") or {}
        supported = ["prune_retention", "query", "stats"]

        if task_type in ("stats", "get_stats"):
            return {"status": "ok", **self.get_stats()}
        if task_type == "query":
            return {"status": "ok", "logs": self.query(**params)}
        if task_type == "prune_retention":
            return {"status": "ok", "deleted": self.prune_retention(**params)}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "show me the recent error logs from the system" previously hit the
        # bare "unhandled type" error stub. Route it to the READ-ONLY,
        # no-required-argument query()/stats() capabilities — never prune
        # (deletes real log rows) from unmatched free text.
        query = (
            params.get("query") or params.get("content")
            or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            level = "ERROR" if "error" in q else "WARNING" if "warn" in q else None
            return {"status": "ok", "logs": self.query(level=level, limit=params.get("limit", 100))}

        return {
            "status": "error",
            "error": f"unhandled type: {task_type}",
            "supported": supported,
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    agg = LogAggregator(db_path=tmp.name)
    event = LogEvent(service="test", level="INFO", message="hello")
    agg._store_event(event)
    stats = agg.get_stats()
    tmp.close()
    Path(tmp.name).unlink(missing_ok=True)
    print(f"LogAggregator OK — {stats['total']} events, levels={stats['by_level']}")
    print("log_aggregator.py OK")
