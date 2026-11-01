"""
Module: agents/karpathy_lab/progress_tracker.py
District: karpathy_lab | Focus: Training run tracking and reporting
"""

from core.memory.db_utils import apply_pragmas
import sys
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, sqlite3, threading
from typing import Optional

class ProgressTracker(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ProgressTracker",
            district="karpathy_lab",
            generation=1
        )
        self.capabilities = ["generate_report", "get_progress", "log_step", "progress", "project", "report", "start_run", "tracking"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self._lock = threading.RLock()
        from core.runtime_paths import data_path

        self.runs_dir = Path(CONFIG.get("karpathy", {}).get("runs_dir") or data_path("training_runs"))
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "runs.db"
        self._current_run: str | None = None
        self._init_db()
        logger.info("[VECTOR][karpathy_lab] ProgressTracker ready")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        apply_pragmas(conn)
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""CREATE TABLE IF NOT EXISTS training_runs (
                    run_name TEXT PRIMARY KEY,
                    config TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT DEFAULT 'running'
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS step_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_name TEXT,
                    step INTEGER,
                    metrics TEXT,
                    timestamp TEXT
                )""")
                conn.commit()
            finally:
                conn.close()

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def start_run(self, run_name: str, config: dict) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Starting training run: {run_name}")
        self.add_lesson({"action": "start_run", "run_name": run_name})

        start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        config_json = json.dumps(config)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO training_runs (run_name, config, start_time, status) VALUES (?, ?, ?, ?)",
                    (run_name, config_json, start_time, "running")
                )
                conn.commit()
            finally:
                conn.close()
        self._current_run = run_name

        result = {
            "run_name": run_name,
            "config": config,
            "start_time": start_time,
            "status": "running",
        }

        self.memory.store(
            event_type="training_run_started",
            content=f"Training run '{run_name}' started",
            tags=["training", "run", run_name],
            context=result,
            source="ProgressTracker"
        )

        logger.info(f"[VECTOR][karpathy_lab] Training run '{run_name}' started at {start_time}")
        return result

    def log_step(self, step: int, metrics: dict, run_name: str = None) -> dict:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        metrics_json = json.dumps(metrics)
        active_run = run_name or self._current_run
        if not active_run:
            # Previously inserted a NULL run_name row that no report could
            # ever find, while returning a normal-looking log entry.
            logger.warning("[VECTOR][karpathy_lab] log_step with no active run — step not recorded")
            return {"error": "no active run; call start_run first", "status": "error"}

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO step_logs (run_name, step, metrics, timestamp) VALUES (?, ?, ?, ?)",
                    (active_run, step, metrics_json, timestamp)
                )
                conn.commit()
            finally:
                conn.close()

        log_entry = {"step": step, "metrics": metrics, "timestamp": timestamp}

        self.memory.store(
            event_type="training_step_logged",
            content=f"Step {step}: loss={metrics.get('loss', 'N/A')}",
            tags=["training", "step", str(step)],
            context=log_entry,
            source="ProgressTracker"
        )

        return log_entry

    def _get_latest_run_name(self) -> str | None:
        """Read-only lookup of the most recently started run, for the free-text
        dispatch fallback below — no side effects, no required args."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT run_name FROM training_runs ORDER BY start_time DESC LIMIT 1"
                )
                row = cursor.fetchone()
            finally:
                conn.close()
        return row[0] if row else None

    def get_progress(self, run_name: str) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Getting progress for run: {run_name}")
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT start_time, end_time, status, config FROM training_runs WHERE run_name = ?",
                    (run_name,)
                )
                row = cursor.fetchone()
                if not row:
                    return {"error": f"Run '{run_name}' not found"}

                start_time, end_time, status, config_json = row
                config = json.loads(config_json)

                cursor2 = conn.execute(
                    "SELECT step, metrics, timestamp FROM step_logs WHERE run_name = ? ORDER BY step DESC LIMIT 1",
                    (run_name,)
                )
                last_step_row = cursor2.fetchone()
            finally:
                conn.close()

        current_step = last_step_row[0] if last_step_row else 0
        max_steps = config.get("training", {}).get("max_steps", 0)
        progress_pct = round((current_step / max_steps) * 100, 2) if max_steps > 0 else 0

        elapsed = None
        if start_time:
            start_dt = datetime.datetime.fromisoformat(start_time)
            if end_time:
                end_dt = datetime.datetime.fromisoformat(end_time)
                elapsed = (end_dt - start_dt).total_seconds()
            else:
                elapsed = (datetime.datetime.now(datetime.timezone.utc) - start_dt).total_seconds()

        progress = {
            "run_name": run_name,
            "status": status,
            "current_step": current_step,
            "max_steps": max_steps,
            "progress_percent": progress_pct,
            "start_time": start_time,
            "end_time": end_time,
            "elapsed_seconds": round(elapsed, 1) if elapsed else None,
            "config": config,
        }

        return progress

    def generate_report(self, run_name: str) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Generating report for run: {run_name}")
        self.add_lesson({"action": "generate_report", "run_name": run_name})

        progress = self.get_progress(run_name)
        if "error" in progress:
            return progress

        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT step, metrics, timestamp FROM step_logs WHERE run_name = ? ORDER BY step ASC",
                    (run_name,)
                )
                rows = cursor.fetchall()
            finally:
                conn.close()

        steps_data = []
        losses = []
        for row in rows:
            metrics = json.loads(row[1])
            steps_data.append({"step": row[0], "metrics": metrics})
            if "loss" in metrics:
                losses.append(metrics["loss"])

        avg_loss = sum(losses) / len(losses) if losses else None
        min_loss = min(losses) if losses else None
        max_loss = max(losses) if losses else None

        report = {
            "run_name": run_name,
            "status": progress["status"],
            "total_steps": progress["current_step"],
            "max_steps": progress["max_steps"],
            "progress_percent": progress["progress_percent"],
            "elapsed_seconds": progress["elapsed_seconds"],
            "loss_summary": {
                "average": round(avg_loss, 6) if avg_loss is not None else None,
                "min": round(min_loss, 6) if min_loss is not None else None,
                "max": round(max_loss, 6) if max_loss is not None else None,
                "count": len(losses),
            },
            "all_steps": steps_data[-20:],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        prompt = f"Generate a brief training summary for run '{run_name}': Current step {progress['current_step']}/{progress['max_steps']} ({progress['progress_percent']}%), avg loss {round(avg_loss, 4) if avg_loss else 'N/A'}. Keep it concise."
        try:
            summary = self._call_ollama(prompt)
        except Exception as e:
            logger.warning(f"[VECTOR][karpathy_lab] report summary unavailable: {e}")
            summary = None
        report["ollama_summary"] = summary

        # run_name is caller-supplied — never let it steer the write path.
        import re
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", run_name).strip("._") or "run"
        report_path = (self.runs_dir / f"{safe_name}_report.json").resolve()
        if not report_path.is_relative_to(self.runs_dir.resolve()):
            return {"error": "invalid run_name for report path"}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)

        self.memory.store(
            event_type="training_report_generated",
            content=f"Generated report for run '{run_name}'",
            tags=["training", "report", run_name],
            context=report,
            source="ProgressTracker"
        )

        logger.info(f"[VECTOR][karpathy_lab] Report generated for '{run_name}'")
        return report

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["start_run", "log_step", "get_progress", "generate_report"]

        if task_type == "start_run":
            return self.start_run(p.get("run_name", "default"), p.get("config", {}))
        if task_type == "log_step":
            return self.log_step(p.get("step", 0), p.get("metrics", {}), p.get("run_name"))
        if task_type == "get_progress":
            return self.get_progress(p.get("run_name", "default"))
        if task_type == "generate_report":
            # generate_report()'s own "status" field is the training run's
            # status (running/completed/...), a different axis than the
            # governor-dispatch status convention — preserve it under
            # "run_status" and report dispatch-level "ok" separately.
            report = self.generate_report(p.get("run_name", "default"))
            if "error" in report:
                return {**report, "status": "error"}
            return {**report, "run_status": report.get("status"), "status": "ok"}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "how is my current training run going, any issues?" previously hit
        # the bare "unhandled type" error stub. Route it to the read-only
        # get_progress()/generate_report() capabilities against the most
        # recently started run (self._current_run if this instance started
        # one, else the latest run in the DB) — no writes, no required args,
        # never starts a new run from free text.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            run_name = p.get("run_name") or self._current_run or self._get_latest_run_name()
            if not run_name:
                return {
                    "status": "ok",
                    "response": "No training runs have been started yet. Start one with a run_name and config to track progress.",
                }
            if any(w in q for w in ("report", "summary")):
                report = self.generate_report(run_name)
                if "error" in report:
                    return {**report, "status": "error"}
                return {**report, "run_status": report.get("status"), "status": "ok"}
            return self.get_progress(run_name)

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = ProgressTracker()
    assert agent.health_points == 500

    run = agent.start_run("test-run-001", {"training": {"max_steps": 1000}, "learning_rate": 3e-4})
    assert run["run_name"] == "test-run-001"
    assert run["status"] == "running"

    agent.log_step(1, {"loss": 2.5, "lr": 1e-5})
    agent.log_step(2, {"loss": 2.3, "lr": 1.2e-5})
    agent.log_step(3, {"loss": 2.1, "lr": 1.5e-5})

    progress = agent.get_progress("test-run-001")
    assert progress["current_step"] == 3
    assert progress["progress_percent"] == 0.3

    report = agent.generate_report("test-run-001")
    assert "loss_summary" in report
    assert report["loss_summary"]["min"] == 2.1

    print("✅ progress_tracker.py OK")
