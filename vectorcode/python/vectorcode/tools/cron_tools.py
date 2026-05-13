# Ported from GitHub/NousResearch_hermes-agent/repo/tools/cronjob_tools.py
"""Cron job management tools."""
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from .registry import registry

_DB_PATH = Path.home() / ".vectorcode" / "cron.db"
_lock = threading.Lock()


def _get_conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS cron_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        schedule TEXT NOT NULL,
        prompt TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        last_run TEXT,
        run_count INTEGER DEFAULT 0
    )""")
    conn.commit()
    return conn


def cron_add(schedule: str, prompt: str, context: Any = None) -> str:
    """Add a cron job. Schedule is a cron expression (e.g. '0 9 * * *')."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute("INSERT INTO cron_jobs (schedule, prompt) VALUES (?, ?)", (schedule, prompt))
        conn.commit()
        job_id = cur.lastrowid
        conn.close()
    return json.dumps({"success": True, "id": job_id, "schedule": schedule})


def cron_list(context: Any = None) -> str:
    """List all cron jobs."""
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT id, schedule, prompt, enabled, last_run, run_count FROM cron_jobs").fetchall()
        conn.close()
    jobs = [{"id": r[0], "schedule": r[1], "prompt": r[2], "enabled": bool(r[3]),
             "last_run": r[4], "run_count": r[5]} for r in rows]
    return json.dumps({"jobs": jobs, "count": len(jobs)})


def cron_remove(id: int, context: Any = None) -> str:
    """Remove a cron job by ID."""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM cron_jobs WHERE id = ?", (id,))
        conn.commit()
        conn.close()
    return json.dumps({"success": True, "id": id})


registry.register(
    name="cron_add",
    handler=cron_add,
    schema={
        "description": "Schedule a recurring task using cron syntax.",
        "parameters": {
            "type": "object",
            "properties": {
                "schedule": {"type": "string", "description": "Cron expression (e.g. '0 9 * * *' for 9am daily)"},
                "prompt": {"type": "string", "description": "Task to run on schedule"},
            },
            "required": ["schedule", "prompt"],
        },
    },
    toolset="full",
    risk_level="medium",
    emoji="⏰",
)

registry.register(
    name="cron_list",
    handler=cron_list,
    schema={
        "description": "List all scheduled cron jobs.",
        "parameters": {"type": "object", "properties": {}},
    },
    toolset="full",
    risk_level="safe",
    emoji="📅",
)

registry.register(
    name="cron_remove",
    handler=cron_remove,
    schema={
        "description": "Remove a scheduled cron job by ID.",
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "integer", "description": "Job ID to remove"}},
            "required": ["id"],
        },
    },
    toolset="full",
    risk_level="medium",
    emoji="🗑️",
)
