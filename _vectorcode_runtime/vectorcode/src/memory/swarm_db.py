"""
SwarmDatabase — complete reference v2/src/hive-mind/storage/DatabaseManager.ts absorption.

Absorbed:
  - Per-swarm SQLite database at ~/.vector/swarms/{swarm_id}.db
  - Tables: agents, tasks, decisions, metrics
  - save_agent_state() / load_agent_state() — persistent per-agent records
  - record_task() — task history with outcome, latency, agent
  - record_decision() — QueenDecision persistence
  - get_swarm_history() — full timeline for a swarm
  - purge_old_records() — TTL-based cleanup (reference cleanup strategy)
"""
from core.memory.db_utils import apply_pragmas
import sqlite3
import json
import re
import time
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

_DB_ROOT = Path.home() / ".vector" / "swarms"
_SWARM_ID_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    apply_pragmas(conn)
    return conn


class SwarmDatabase:
    """
    SQLite-backed persistent swarm storage.
    reference DatabaseManager.ts — adapted to Python + local-first architecture.
    Each swarm gets its own .db file scoped by swarm_id.
    """

    def __init__(self, swarm_id: str = "default"):
        if not isinstance(swarm_id, str) or not _SWARM_ID_RE.fullmatch(swarm_id):
            raise ValueError("swarm_id may contain only letters, numbers, '_' and '-'")
        self.swarm_id = swarm_id
        self._db_path = _DB_ROOT / f"{swarm_id}.db"
        self._lock = threading.RLock()
        self._conn    = _conn(self._db_path)
        self._init_schema()
        logger.info(f"[VECTOR][swarm_db] opened: {self._db_path}")

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id     TEXT PRIMARY KEY,
                agent_name   TEXT,
                agent_type   TEXT,
                hp           INTEGER DEFAULT 500,
                status       TEXT DEFAULT 'idle',
                current_task TEXT DEFAULT '',
                tasks_completed INTEGER DEFAULT 0,
                tasks_failed    INTEGER DEFAULT 0,
                spawned_at   REAL,
                last_seen    REAL,
                metadata     TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id           TEXT PRIMARY KEY,
                task_text    TEXT,
                agent_id     TEXT,
                domain       TEXT DEFAULT 'core',
                outcome      TEXT DEFAULT 'pending',
                reward       REAL DEFAULT 0.0,
                latency_ms   REAL DEFAULT 0.0,
                started_at   REAL,
                completed_at REAL,
                metadata     TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id           TEXT PRIMARY KEY,
                task_text    TEXT,
                subtasks     TEXT,
                assigned_to  TEXT,
                strategy     TEXT,
                created_at   REAL,
                metadata     TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           REAL,
                swarm_id     TEXT,
                active       INTEGER,
                idle         INTEGER,
                busy         INTEGER,
                topology     TEXT,
                extra        TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_agent    ON tasks(agent_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_outcome  ON tasks(outcome);
            CREATE INDEX IF NOT EXISTS idx_metrics_ts     ON metrics(ts);
            """)
            self._conn.commit()

    # ── Agent state ────────────────────────────────────────────────────────────

    def save_agent_state(self, agent_id: str, data: dict) -> None:
        """Upsert agent record. reference: DatabaseManager.saveAgentState()."""
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
            INSERT INTO agents (agent_id, agent_name, agent_type, hp, status,
                                current_task, tasks_completed, tasks_failed,
                                spawned_at, last_seen, metadata)
            VALUES (:id, :name, :type, :hp, :status, :task, :completed, :failed, :now, :now, :meta)
            ON CONFLICT(agent_id) DO UPDATE SET
                hp              = excluded.hp,
                status          = excluded.status,
                current_task    = excluded.current_task,
                tasks_completed = excluded.tasks_completed,
                tasks_failed    = excluded.tasks_failed,
                last_seen       = excluded.last_seen,
                metadata        = excluded.metadata
        """, {
            "id":        agent_id,
            "name":      data.get("name", "?"),
            "type":      data.get("type", "generic"),
            "hp":        data.get("hp", 500),
            "status":    data.get("status", "idle"),
            "task":      data.get("current_task", ""),
            "completed": data.get("tasks_completed", 0),
            "failed":    data.get("tasks_failed", 0),
            "now":       now,
            "meta":      json.dumps(data.get("metadata", {})),
            })
            self._conn.commit()

    def load_agent_state(self, agent_id: str) -> Optional[dict]:
        """Load agent record. reference: DatabaseManager.loadAgentState()."""
        with self._lock:
            cur = self._conn.cursor()
            row = cur.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def list_agents(self, status: Optional[str] = None) -> list[dict]:
        with self._lock:
            cur = self._conn.cursor()
            if status:
                rows = cur.execute(
                    "SELECT * FROM agents WHERE status = ? ORDER BY last_seen DESC", (status,)
                ).fetchall()
            else:
                rows = cur.execute(
                    "SELECT * FROM agents ORDER BY last_seen DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Task records ───────────────────────────────────────────────────────────

    def record_task(
        self,
        task_id: str,
        task_text: str,
        agent_id: str,
        *,
        domain: str = "core",
        outcome: str = "pending",
        reward: float = 0.0,
        latency_ms: float = 0.0,
        started_at: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Record or update a task. reference: DatabaseManager.recordTask()."""
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
            INSERT INTO tasks (id, task_text, agent_id, domain, outcome, reward,
                               latency_ms, started_at, completed_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                outcome      = excluded.outcome,
                reward       = excluded.reward,
                latency_ms   = excluded.latency_ms,
                completed_at = excluded.completed_at,
                metadata     = excluded.metadata
        """, (
            task_id, task_text, agent_id, domain, outcome, reward,
            latency_ms, now if started_at is None else started_at,
            now if outcome != "pending" else None,
            json.dumps(metadata or {}),
            ))
            self._conn.commit()

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_agent_tasks(self, agent_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE agent_id = ? ORDER BY started_at DESC LIMIT ?",
                (agent_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Decision records ───────────────────────────────────────────────────────

    def record_decision(self, decision_id: str, data: dict) -> None:
        """Persist a QueenDecision. reference: DatabaseManager.recordDecision()."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO decisions
                (id, task_text, subtasks, assigned_to, strategy, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            decision_id,
            data.get("task", ""),
            json.dumps(data.get("subtasks", [])),
            json.dumps(data.get("assigned_to", {})),
            data.get("strategy", "hierarchical"),
            data.get("created_at", time.time()),
            json.dumps(data.get("metadata", {})),
            ))
            self._conn.commit()

    def get_decision(self, decision_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["subtasks"]    = json.loads(d.get("subtasks", "[]"))
        d["assigned_to"] = json.loads(d.get("assigned_to", "{}"))
        return d

    # ── Metrics ────────────────────────────────────────────────────────────────

    def record_metric(self, active: int, idle: int, busy: int, topology: str, extra: Optional[dict] = None) -> None:
        with self._lock:
            self._conn.execute("""
                INSERT INTO metrics (ts, swarm_id, active, idle, busy, topology, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (time.time(), self.swarm_id, active, idle, busy, topology, json.dumps(extra or {})))
            self._conn.commit()

    # ── History ────────────────────────────────────────────────────────────────

    def get_swarm_history(self, limit: int = 50) -> dict:
        """Full swarm timeline — agents, tasks, decisions. reference: getSwarmHistory()."""
        with self._lock:
            agents = self.list_agents()
            tasks = [dict(r) for r in self._conn.execute(
                "SELECT * FROM tasks ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()]
            decisions = [dict(r) for r in self._conn.execute(
                "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()]
            metrics = [dict(r) for r in self._conn.execute(
                "SELECT ts, active, idle, busy, topology FROM metrics ORDER BY ts DESC LIMIT 20"
            ).fetchall()]
        return {
            "swarm_id":  self.swarm_id,
            "agents":    agents,
            "tasks":     tasks,
            "decisions": decisions,
            "metrics":   metrics,
        }

    # ── Cleanup (reference purge strategy) ────────────────────────────────────────

    def purge_old_records(self, older_than_days: int = 30) -> int:
        cutoff = time.time() - older_than_days * 86400
        with self._lock:
            cur = self._conn.cursor()
            deleted = 0
            for statement in (
                "DELETE FROM tasks WHERE completed_at IS NOT NULL AND completed_at < ?",
                "DELETE FROM metrics WHERE ts < ?",
                "DELETE FROM decisions WHERE created_at < ?",
            ):
                cur.execute(statement, (cutoff,))
                deleted += cur.rowcount
            self._conn.commit()
        logger.info(f"[VECTOR][swarm_db] purged {deleted} old records (>{older_than_days}d)")
        return deleted

    def close(self) -> None:
        with self._lock:
            self._conn.close()


if __name__ == "__main__":
    import tempfile, os, sys
    # Use temp dir for test isolation
    _DB_ROOT_orig = _DB_ROOT
    _mod = sys.modules[__name__]
    with tempfile.TemporaryDirectory() as tmp:
        _mod._DB_ROOT = Path(tmp)
        db = SwarmDatabase("test-swarm-001")

        # Save + load agent state
        db.save_agent_state("agent-1", {
            "name": "CoderAgent", "type": "coder", "hp": 600,
            "status": "idle", "current_task": "", "tasks_completed": 5
        })
        loaded = db.load_agent_state("agent-1")
        assert loaded is not None
        assert loaded["agent_name"] == "CoderAgent"
        assert loaded["hp"] == 600

        # Record task
        db.record_task("task-001", "write unit tests", "agent-1",
                       domain="core", outcome="completed", reward=0.8, latency_ms=1200)
        task = db.get_task("task-001")
        assert task is not None
        assert task["outcome"] == "completed"

        # Agent tasks
        agent_tasks = db.get_agent_tasks("agent-1")
        assert len(agent_tasks) == 1

        # Record decision
        db.record_decision("dec-001", {
            "task": "build auth system",
            "subtasks": [{"task": "write login", "domain": "core"}],
            "assigned_to": {"agent-1": "write login"},
            "strategy": "hierarchical",
        })
        dec = db.get_decision("dec-001")
        assert dec is not None
        assert dec["strategy"] == "hierarchical"
        assert len(dec["subtasks"]) == 1

        # Record metric
        db.record_metric(active=2, idle=1, busy=1, topology="hierarchical")

        # History
        history = db.get_swarm_history()
        assert history["swarm_id"] == "test-swarm-001"
        assert len(history["agents"]) == 1
        assert len(history["tasks"]) == 1

        # List agents
        agents = db.list_agents()
        assert len(agents) == 1

        # Purge (nothing old enough to delete)
        deleted = db.purge_old_records(older_than_days=30)
        assert isinstance(deleted, int)

        db.close()

    print("swarm_db.py OK — agents, tasks, decisions, metrics, history, purge")


