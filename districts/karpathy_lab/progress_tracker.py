"""
Module: agents/karpathy_lab/progress_tracker.py
District: karpathy_lab | Focus: Training run tracking and reporting
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, sqlite3
from typing import Optional


class ProgressTracker(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ProgressTracker",
            district="karpathy_lab",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.runs_dir = Path(CONFIG.get("karpathy", {}).get("runs_dir", "./data/training_runs"))
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.runs_dir / "runs.db"
        self._current_run: str | None = None
        self._init_db()
        logger.info("[VECTOR][karpathy_lab] ProgressTracker ready")

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
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

        conn = sqlite3.connect(self.db_path)
        start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        config_json = json.dumps(config)

        conn.execute(
            "INSERT OR REPLACE INTO training_runs (run_name, config, start_time, status) VALUES (?, ?, ?, ?)",
            (run_name, config_json, start_time, "running")
        )
        conn.commit()
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

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO step_logs (run_name, step, metrics, timestamp) VALUES (?, ?, ?, ?)",
            (active_run, step, metrics_json, timestamp)
        )
        conn.commit()
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

    def get_progress(self, run_name: str) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Getting progress for run: {run_name}")
        conn = sqlite3.connect(self.db_path)

        cursor = conn.execute(
            "SELECT start_time, end_time, status, config FROM training_runs WHERE run_name = ?",
            (run_name,)
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"error": f"Run '{run_name}' not found"}

        start_time, end_time, status, config_json = row
        config = json.loads(config_json)

        cursor2 = conn.execute(
            "SELECT step, metrics, timestamp FROM step_logs WHERE run_name = ? ORDER BY step DESC LIMIT 1",
            (run_name,)
        )
        last_step_row = cursor2.fetchone()
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

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT step, metrics, timestamp FROM step_logs ORDER BY step ASC"
        )
        rows = cursor.fetchall()
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
                "average": round(avg_loss, 6) if avg_loss else None,
                "min": round(min_loss, 6) if min_loss else None,
                "max": round(max_loss, 6) if max_loss else None,
                "count": len(losses),
            },
            "all_steps": steps_data[-20:],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        prompt = f"Generate a brief training summary for run '{run_name}': Current step {progress['current_step']}/{progress['max_steps']} ({progress['progress_percent']}%), avg loss {round(avg_loss, 4) if avg_loss else 'N/A'}. Keep it concise."
        summary = self._call_ollama(prompt)
        report["ollama_summary"] = summary

        report_path = self.runs_dir / f"{run_name}_report.json"
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
        p = task.get("params", {})
        result = self.generate_report(p.get("run_name", "default"))
        return {"status": "ok", **result}


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