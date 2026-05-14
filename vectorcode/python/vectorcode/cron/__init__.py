# Ported from GitHub/NousResearch_hermes-agent/repo/hermes_cli/cron.py
"""Cron scheduler daemon — runs scheduled VectorCode tasks."""
import asyncio
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

_DB_PATH = Path.home() / ".vectorcode" / "cron.db"
_running = False
_thread: Optional[threading.Thread] = None


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


def _parse_cron(schedule: str, now: datetime) -> bool:
    """Simple cron expression check: '* * * * *' (min hour dom mon dow)."""
    try:
        parts = schedule.strip().split()
        if len(parts) != 5:
            return False
        minute, hour, dom, month, dow = parts

        def _match(field, value):
            if field == "*":
                return True
            if "," in field:
                return str(value) in field.split(",")
            if "-" in field:
                lo, hi = field.split("-")
                return int(lo) <= value <= int(hi)
            return int(field) == value

        return (
            _match(minute, now.minute) and
            _match(hour, now.hour) and
            _match(dom, now.day) and
            _match(month, now.month) and
            _match(dow, now.weekday())
        )
    except Exception:
        return False


def _run_job(job_id: int, prompt: str) -> None:
    """Execute a cron job by running the agent."""
    logger.info(f"[cron] Running job #{job_id}: {prompt[:60]}")
    try:
        from vectorcode.engine import AIAgent
        agent = AIAgent(model="", max_iterations=30)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(agent.run_conversation(prompt))
            logger.info(f"[cron] Job #{job_id} done: {result.get('status')}")
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[cron] Job #{job_id} failed: {e}")

    # Update last_run and run_count
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE cron_jobs SET last_run=datetime('now'), run_count=run_count+1 WHERE id=?",
            (job_id,)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _scheduler_loop() -> None:
    """Main scheduler loop — checks every 60 seconds."""
    global _running
    logger.info("[cron] Scheduler started")
    while _running:
        now = datetime.now()
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, schedule, prompt FROM cron_jobs WHERE enabled=1"
            ).fetchall()
            conn.close()
            for job_id, schedule, prompt in rows:
                if _parse_cron(schedule, now):
                    t = threading.Thread(target=_run_job, args=(job_id, prompt), daemon=True)
                    t.start()
        except Exception as e:
            logger.error(f"[cron] Scheduler error: {e}")
        # Sleep until next minute boundary
        time.sleep(60 - datetime.now().second)
    logger.info("[cron] Scheduler stopped")


def start_daemon() -> None:
    """Start the cron scheduler in a background thread."""
    global _running, _thread
    if _running:
        logger.warning("[cron] Scheduler already running")
        return
    _running = True
    _thread = threading.Thread(target=_scheduler_loop, daemon=True, name="vector-cron")
    _thread.start()
    logger.info("[cron] Daemon started")


def stop_daemon() -> None:
    """Stop the cron scheduler."""
    global _running
    _running = False
    logger.info("[cron] Daemon stop requested")
