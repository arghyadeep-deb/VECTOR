"""VectorCode v3 Memory backends — SQLite, Hybrid, AgentDB persistence."""

from core.memory.db_utils import apply_pragmas
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional


class SQLiteBackend:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".vector" / "v3_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        apply_pragmas(self._conn)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, namespace TEXT, key TEXT,
                value TEXT, created_at REAL, updated_at REAL,
                ttl REAL DEFAULT 0
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_namespace ON memories(namespace)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key)")
        self._conn.commit()

    async def store(self, namespace: str, key: str, value: Any, ttl: float = 0):
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memories (id, namespace, key, value, created_at, updated_at, ttl) VALUES (?,?,?,?,?,?,?)",
                (f"{namespace}:{key}", namespace, key, json.dumps(value), now, now, ttl),
            )
            self._conn.commit()

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value, ttl, created_at FROM memories WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
        if not row: return None
        if row[1] > 0 and time.time() - row[2] > row[1]: return None
        return json.loads(row[0])

    async def search(self, namespace: str, query: str = "") -> list[dict]:
        with self._lock:
            if query:
                rows = self._conn.execute(
                    "SELECT key, value, updated_at FROM memories WHERE namespace=? AND (key LIKE ? OR value LIKE ?) ORDER BY updated_at DESC LIMIT 50",
                    (namespace, f"%{query}%", f"%{query}%"),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT key, value, updated_at FROM memories WHERE namespace=? ORDER BY updated_at DESC LIMIT 50",
                    (namespace,),
                ).fetchall()
        return [{"key": r[0], "value": json.loads(r[1]), "updated_at": r[2]} for r in rows]


class HybridBackend:
    def __init__(self, sqlite_path: Optional[Path] = None):
        self.sqlite = SQLiteBackend(sqlite_path)
        self._cache: dict[str, Any] = {}

    async def store(self, namespace: str, key: str, value: Any, ttl: float = 0):
        self._cache[f"{namespace}:{key}"] = value
        await self.sqlite.store(namespace, key, value, ttl)

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        cached = self._cache.get(f"{namespace}:{key}")
        if cached is not None: return cached
        return await self.sqlite.get(namespace, key)

    async def search(self, namespace: str, query: str = "") -> list[dict]:
        return await self.sqlite.search(namespace, query)


class AgentDBBackend:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".vector" / "agent_db.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        apply_pragmas(self._conn)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY, type TEXT, status TEXT,
                capabilities TEXT, metadata TEXT, created_at REAL, last_active REAL
            )
        """)
        self._conn.commit()

    async def save_agent(self, agent_id: str, agent_type: str, status: str = "idle",
                         capabilities: Optional[list] = None, metadata: Optional[dict] = None):
        with self._lock:
            now = time.time()
            self._conn.execute(
                "INSERT OR REPLACE INTO agents VALUES (?,?,?,?,?,?,?)",
                (agent_id, agent_type, status, json.dumps(capabilities or []),
                 json.dumps(metadata or {}), now, now),
            )
            self._conn.commit()

    async def get_agent(self, agent_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if not row: return None
        return {"id": row[0], "type": row[1], "status": row[2],
                "capabilities": json.loads(row[3]), "metadata": json.loads(row[4])}

    async def list_agents(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM agents ORDER BY last_active DESC").fetchall()
        return [{"id": r[0], "type": r[1], "status": r[2]} for r in rows]
