"""Weekly self-improvement cron scheduler.

Wires SelfImprovementCycle.run_weekly() into APScheduler.
Runs every Sunday at 02:30 local time (after the 2AM reflection loop).

Usage — standalone:
    python core/training/weekly_scheduler.py

Usage — programmatic:
    from core.training.weekly_scheduler import WeeklyTrainingScheduler
    sched = WeeklyTrainingScheduler()
    sched.start()          # non-blocking background scheduler
    ...
    sched.stop()
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from datetime import datetime

from loguru import logger
from core.runtime_paths import data_path

__all__ = ["WeeklyTrainingScheduler"]

_CRON_HOUR = 2
_CRON_MINUTE = 30
_CRON_DAY_OF_WEEK = "sun"   # every Sunday


class WeeklyTrainingScheduler:
    """APScheduler-backed weekly training cron.

    Runs SelfImprovementCycle.run_weekly() on the configured schedule and
    persists results to the configured VECTOR data root.
    """

    def __init__(
        self,
        adapters_dir: str | None = None,
        log_path: str | None = None,
        hour: int = _CRON_HOUR,
        minute: int = _CRON_MINUTE,
        day_of_week: str = _CRON_DAY_OF_WEEK,
    ) -> None:
        self._adapters_dir = adapters_dir or str(data_path("adapters"))
        self._log_path = Path(log_path) if log_path else data_path("reports", "scheduler_log.jsonl")
        self._hour = hour
        self._minute = minute
        self._day_of_week = day_of_week
        self._scheduler = None
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _run_cycle(self) -> None:
        """Called by APScheduler on the cron schedule."""
        logger.info(
            "[VECTOR][weekly_sched] Starting scheduled self-improvement cycle at {}",
            datetime.now().isoformat(),
        )
        try:
            from core.training.self_improvement_cycle import SelfImprovementCycle
            cycle = SelfImprovementCycle(adapters_dir=self._adapters_dir)
            result = cycle.run_weekly()
            self._append_log(result)
            logger.info(
                "[VECTOR][weekly_sched] Cycle complete: status={} adapters_dir={}",
                result.get("status"), self._adapters_dir,
            )
        except Exception as e:
            logger.error("[VECTOR][weekly_sched] Cycle failed: {}", e)
            self._append_log({"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()})

    def _append_log(self, result: dict) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, default=str) + "\n")
        except Exception as e:
            logger.warning("[VECTOR][weekly_sched] log write failed: {}", e)

    def start(self) -> bool:
        """Start the background scheduler. Returns True if APScheduler is available."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            self._scheduler = BackgroundScheduler(timezone="local")
            self._scheduler.add_job(
                self._run_cycle,
                trigger=CronTrigger(
                    day_of_week=self._day_of_week,
                    hour=self._hour,
                    minute=self._minute,
                ),
                id="weekly_training",
                name="Weekly Self-Improvement Cycle",
                replace_existing=True,
            )
            self._scheduler.start()
            logger.info(
                "[VECTOR][weekly_sched] Scheduler started — fires every {} at {:02d}:{:02d}",
                self._day_of_week, self._hour, self._minute,
            )
            return True
        except ImportError:
            logger.warning("[VECTOR][weekly_sched] apscheduler not installed — scheduler disabled")
            return False
        except Exception as e:
            logger.error("[VECTOR][weekly_sched] Scheduler start failed: {}", e)
            return False

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("[VECTOR][weekly_sched] Scheduler stopped")

    def run_now(self) -> dict:
        """Trigger the cycle immediately (synchronous, for testing)."""
        logger.info("[VECTOR][weekly_sched] Manual trigger: run_now()")
        try:
            from core.training.self_improvement_cycle import SelfImprovementCycle
            cycle = SelfImprovementCycle(adapters_dir=self._adapters_dir)
            result = cycle.run_weekly()
            self._append_log(result)
            return result
        except Exception as e:
            logger.error("[VECTOR][weekly_sched] run_now failed: {}", e)
            err = {"status": "error", "error": str(e), "timestamp": datetime.now().isoformat()}
            self._append_log(err)
            return err

    def get_next_run(self) -> str | None:
        """Return ISO timestamp of the next scheduled run, or None."""
        try:
            if self._scheduler and self._scheduler.running:
                job = self._scheduler.get_job("weekly_training")
                if job and job.next_run_time:
                    return job.next_run_time.isoformat()
        except Exception as e:
            logger.warning("[VECTOR][weekly_sched] get_next_run failed: {}", e)
        return None

    def get_log(self, limit: int = 20) -> list[dict]:
        """Return the last N entries from the scheduler log."""
        if not self._log_path.exists():
            return []
        try:
            lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
            entries = []
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return entries
        except Exception as e:
            logger.warning("[VECTOR][weekly_sched] log read failed: {}", e)
            return []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import time

    sched = WeeklyTrainingScheduler(log_path=str(data_path("reports", "test_scheduler_log.jsonl")))
    started = sched.start()
    print(f"Scheduler started: {started}")
    if started:
        nxt = sched.get_next_run()
        print(f"Next run: {nxt}")
        time.sleep(0.5)
        sched.stop()

    # Run one cycle immediately to verify end-to-end
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    sched2 = WeeklyTrainingScheduler(adapters_dir=tmp, log_path=f"{tmp}/sched_log.jsonl")
    result = sched2.run_now()
    print(f"run_now status: {result.get('status')}")
    log = sched2.get_log()
    print(f"Log entries: {len(log)}")
    shutil.rmtree(tmp, ignore_errors=True)
    # Cleanup test log
    data_path("reports", "test_scheduler_log.jsonl").unlink(missing_ok=True)
    print("weekly_scheduler.py OK")