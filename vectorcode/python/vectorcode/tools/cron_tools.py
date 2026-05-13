"""Scheduled task manager — APScheduler backed, survives restarts."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode pkg parent
from loguru import logger

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

# ── APScheduler availability ──────────────────────────────────────────────────
_SCHEDULER_AVAILABLE = False
try:
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
    from apscheduler.triggers.cron import CronTrigger  # type: ignore
    from apscheduler.triggers.interval import IntervalTrigger  # type: ignore
    _SCHEDULER_AVAILABLE = True
except ImportError:
    logger.warning(
        "[VECTOR][cron] APScheduler not installed — scheduling disabled. "
        "Run: pip install apscheduler"
    )
    BackgroundScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore
    IntervalTrigger = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────

_INTERVAL_RE = re.compile(r"^every\s+(\d+)(m|h|d)$", re.IGNORECASE)


def _parse_schedule(schedule: str):
    """
    Return an APScheduler trigger for the given schedule string, or None if
    APScheduler is unavailable.

    Accepted formats:
      "every 30m"  → IntervalTrigger(minutes=30)
      "every 2h"   → IntervalTrigger(hours=2)
      "every 1d"   → IntervalTrigger(days=1)
      "0 2 * * *"  → CronTrigger (standard 5-field cron)
    """
    if not _SCHEDULER_AVAILABLE:
        return None

    m = _INTERVAL_RE.match(schedule.strip())
    if m:
        value, unit = int(m.group(1)), m.group(2).lower()
        kwargs: dict = {}
        if unit == "m":
            kwargs["minutes"] = value
        elif unit == "h":
            kwargs["hours"] = value
        else:
            kwargs["days"] = value
        return IntervalTrigger(**kwargs)

    # treat as 5-field cron string
    parts = schedule.strip().split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )

    raise ValueError(
        f"Unrecognised schedule format '{schedule}'. "
        "Use 'every Xm/Xh/Xd' or a 5-field cron string."
    )


# ─────────────────────────────────────────────────────────────────────────────

class CronManager:
    """APScheduler-backed cron manager that persists jobs across restarts."""

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage = storage_path or (Path.home() / ".vector" / "cron_jobs.json")
        self._storage.parent.mkdir(parents=True, exist_ok=True)

        # Raw job metadata (persisted)
        # {name: {"name", "schedule", "command", "enabled", "created_at", "last_run"}}
        self._jobs: dict[str, dict] = {}

        self._scheduler = BackgroundScheduler() if _SCHEDULER_AVAILABLE else None
        self._started = False
        self._load()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler and re-register all persisted enabled jobs."""
        if not _SCHEDULER_AVAILABLE:
            logger.warning("[VECTOR][cron] APScheduler unavailable — start() is a no-op")
            return
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        for job in self._jobs.values():
            if job.get("enabled", True):
                self._register_job(job["name"], job["schedule"], job["command"])
        logger.info("[VECTOR][cron] scheduler started, %d job(s) loaded", len(self._jobs))

    def stop(self) -> None:
        """Graceful shutdown of the scheduler."""
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("[VECTOR][cron] scheduler stopped")

    # ── Job management ────────────────────────────────────────────────────────

    def add_job(
        self,
        name: str,
        schedule: str,
        command: str,
        *,
        enabled: bool = True,
    ) -> dict:
        """Add or replace a cron job.

        Returns:
            {"name": name, "schedule": schedule, "status": "created"}
        """
        # Validate schedule before persisting
        try:
            _parse_schedule(schedule)
        except ValueError as e:
            if _SCHEDULER_AVAILABLE:
                return {"error": str(e), "success": False}
            # if APScheduler unavailable, still persist (metadata only)

        now = datetime.now(timezone.utc).isoformat()
        self._jobs[name] = {
            "name": name,
            "schedule": schedule,
            "command": command,
            "enabled": enabled,
            "created_at": now,
            "last_run": None,
        }
        self._save()

        if self._started and enabled:
            # Remove old APScheduler job if it exists, then re-add
            try:
                self._scheduler.remove_job(name)
            except Exception:
                pass
            self._register_job(name, schedule, command)

        logger.info("[VECTOR][cron] job added: %s  schedule=%s", name, schedule)
        return {"name": name, "schedule": schedule, "status": "created"}

    def remove_job(self, name: str) -> dict:
        """Remove a job by name."""
        if name not in self._jobs:
            return {"removed": False, "error": f"job '{name}' not found"}
        del self._jobs[name]
        self._save()
        if self._scheduler and self._started:
            try:
                self._scheduler.remove_job(name)
            except Exception:
                pass
        logger.info("[VECTOR][cron] job removed: %s", name)
        return {"removed": True, "name": name}

    def list_jobs(self) -> list[dict]:
        """Return all jobs with next_run_time if scheduler is running."""
        result = []
        for job in self._jobs.values():
            entry = dict(job)
            if self._scheduler and self._started:
                try:
                    apjob = self._scheduler.get_job(job["name"])
                    entry["next_run_time"] = (
                        apjob.next_run_time.isoformat() if apjob and apjob.next_run_time else None
                    )
                except Exception:
                    entry["next_run_time"] = None
            else:
                entry["next_run_time"] = None
            result.append(entry)
        return result

    def run_now(self, name: str) -> dict:
        """Execute a job immediately regardless of its schedule."""
        if name not in self._jobs:
            return {"success": False, "error": f"job '{name}' not found"}
        job = self._jobs[name]
        self._execute_command(name, job["command"])
        return {"success": True, "name": name, "status": "executed"}

    def pause_job(self, name: str) -> dict:
        """Pause a running job."""
        if name not in self._jobs:
            return {"success": False, "error": f"job '{name}' not found"}
        self._jobs[name]["enabled"] = False
        self._save()
        if self._scheduler and self._started:
            try:
                self._scheduler.pause_job(name)
            except Exception:
                pass
        logger.info("[VECTOR][cron] job paused: %s", name)
        return {"success": True, "name": name, "status": "paused"}

    def resume_job(self, name: str) -> dict:
        """Resume a paused job."""
        if name not in self._jobs:
            return {"success": False, "error": f"job '{name}' not found"}
        self._jobs[name]["enabled"] = True
        self._save()
        if self._scheduler and self._started:
            try:
                self._scheduler.resume_job(name)
            except Exception:
                # Re-register if not already in scheduler
                job = self._jobs[name]
                self._register_job(name, job["schedule"], job["command"])
        logger.info("[VECTOR][cron] job resumed: %s", name)
        return {"success": True, "name": name, "status": "resumed"}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _register_job(self, name: str, schedule: str, command: str) -> None:
        """Register a job with the APScheduler instance."""
        if not _SCHEDULER_AVAILABLE or not self._started:
            return
        try:
            trigger = _parse_schedule(schedule)
            if trigger is None:
                return
            self._scheduler.add_job(
                func=self._execute_command,
                trigger=trigger,
                id=name,
                args=[name, command],
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.debug("[VECTOR][cron] registered APScheduler job: %s", name)
        except Exception as e:
            logger.error("[VECTOR][cron] failed to register job '%s': %s", name, e)

    def _execute_command(self, name: str, command: str) -> None:
        """Run the command in a subprocess and log output."""
        logger.info("[VECTOR][cron] executing job '%s': %s", name, command)
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            if stdout:
                logger.info("[VECTOR][cron][%s] stdout: %s", name, stdout[:500])
            if stderr:
                logger.warning("[VECTOR][cron][%s] stderr: %s", name, stderr[:500])
            if result.returncode != 0:
                logger.warning("[VECTOR][cron][%s] exit code %d", name, result.returncode)

            # Update last_run
            if name in self._jobs:
                self._jobs[name]["last_run"] = datetime.now(timezone.utc).isoformat()
                self._save()

        except subprocess.TimeoutExpired:
            logger.error("[VECTOR][cron][%s] timed out after 300s", name)
        except Exception as e:
            logger.error("[VECTOR][cron][%s] error: %s", name, e)

    def _save(self) -> None:
        """Persist job metadata to JSON."""
        try:
            self._storage.write_text(
                json.dumps(self._jobs, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("[VECTOR][cron] failed to save jobs: %s", e)

    def _load(self) -> None:
        """Load job metadata from JSON (missing file is not an error)."""
        if not self._storage.exists():
            return
        try:
            data = json.loads(self._storage.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._jobs = data
            logger.debug("[VECTOR][cron] loaded %d job(s) from %s", len(self._jobs), self._storage)
        except Exception as e:
            logger.warning("[VECTOR][cron] could not load jobs from %s: %s", self._storage, e)


# ── Singleton ─────────────────────────────────────────────────────────────────

_cron_manager: Optional[CronManager] = None


def get_cron_manager() -> CronManager:
    """Return the singleton CronManager (not auto-started)."""
    global _cron_manager
    if _cron_manager is None:
        _cron_manager = CronManager()
    return _cron_manager


# ─────────────────────────────────────────────────────────────────────────────

def get_tool_schemas() -> list[dict]:
    """Return OpenAI-format tool schemas for cron job management."""
    return [
        {
            "type": "function",
            "function": {
                "name": "add_cron_job",
                "description": (
                    "Schedule a recurring command. "
                    "schedule can be 'every Xm/Xh/Xd' or a 5-field cron string like '0 2 * * *'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Unique job name",
                        },
                        "schedule": {
                            "type": "string",
                            "description": "Schedule string — 'every 30m', 'every 2h', or '0 2 * * *'",
                        },
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute",
                        },
                        "enabled": {
                            "type": "boolean",
                            "default": True,
                            "description": "Start enabled (default true)",
                        },
                    },
                    "required": ["name", "schedule", "command"],
                },
            },
            "_meta": {"risk": "medium", "read_only": False},
        },
        {
            "type": "function",
            "function": {
                "name": "remove_cron_job",
                "description": "Remove a scheduled job by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Job name to remove"},
                    },
                    "required": ["name"],
                },
            },
            "_meta": {"risk": "medium", "read_only": False},
        },
        {
            "type": "function",
            "function": {
                "name": "list_cron_jobs",
                "description": "List all scheduled jobs with their status and next run time.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            "_meta": {"risk": "safe", "read_only": True},
        },
        {
            "type": "function",
            "function": {
                "name": "run_cron_job_now",
                "description": "Execute a scheduled job immediately, regardless of its schedule.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Job name to run immediately"},
                    },
                    "required": ["name"],
                },
            },
            "_meta": {"risk": "medium", "read_only": False},
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        storage = Path(tmp) / "cron_jobs.json"
        cm = CronManager(storage_path=storage)

        # add_job
        r = cm.add_job("test_job", "every 1m", "echo hello")
        assert r["status"] == "created", r
        assert r["name"] == "test_job"

        # list_jobs
        jobs = cm.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["name"] == "test_job"
        assert jobs[0]["schedule"] == "every 1m"
        assert jobs[0]["command"] == "echo hello"

        # persistence — reload from disk
        cm2 = CronManager(storage_path=storage)
        jobs2 = cm2.list_jobs()
        assert len(jobs2) == 1, f"expected 1 job after reload, got {len(jobs2)}"

        # run_now (executes echo hello)
        rr = cm.run_now("test_job")
        assert rr["success"] is True, rr

        # pause / resume
        cm.pause_job("test_job")
        assert cm._jobs["test_job"]["enabled"] is False
        cm.resume_job("test_job")
        assert cm._jobs["test_job"]["enabled"] is True

        # remove_job
        rd = cm.remove_job("test_job")
        assert rd["removed"] is True, rd
        assert len(cm.list_jobs()) == 0

        # schemas
        schemas = get_tool_schemas()
        assert len(schemas) == 4
        names = {s["function"]["name"] for s in schemas}
        assert "add_cron_job" in names
        assert "remove_cron_job" in names
        assert "list_cron_jobs" in names
        assert "run_cron_job_now" in names

        logger.info("[VECTOR][cron] smoke test complete — %d schemas", len(schemas))

    print("✅ tools/cron_tools.py OK")
