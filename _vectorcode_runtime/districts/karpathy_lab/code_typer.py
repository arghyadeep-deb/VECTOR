import sys
import uuid
import json
import asyncio
import datetime
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class CodeTyper(AgentBase):
    """
    Tracks 30-min daily Karpathy coding sessions.
    RULE 12 — 30 min/day. Type every line. This builds the Chairman LLM.
    Every session is logged to karpathy.runs_dir and episodic memory.
    """

    DAILY_GOAL_MINUTES: int = 30

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="CodeTyper",
            district="karpathy_lab",
            generation=generation,
        )
        self.capabilities = ["karpathy_lab"]
        if ghost:
            self.inherit_ghost(ghost)

        self._runs_dir = Path(CONFIG["karpathy"]["runs_dir"])
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._today_minutes: float = 0.0
        self._current_session: dict | None = None
        self._memory = None
        logger.info(f"[VECTOR][code_typer] ready gen={generation} hp={self.health_points}")

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    # ── Session management ────────────────────────────────────────────────────

    def start_session(self, topic: str, file_path: str = "") -> dict:
        """Begin a Karpathy coding session."""
        if self._current_session:
            logger.warning("[VECTOR][code_typer] session already active — call end_session() first")
            return {"status": "already_active", "session": self._current_session}

        self._current_session = {
            "session_id": str(uuid.uuid4())[:8],
            "topic": topic,
            "file_path": file_path,
            "start": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "end": None,
            "duration_minutes": 0.0,
            "lines_typed": 0,
            "date": datetime.date.today().isoformat(),
        }
        self.award_points(5, "karpathy session started")
        logger.info(f"[VECTOR][code_typer] session started — topic={topic}")
        return {"status": "started", "session": self._current_session}

    def log_progress(self, lines_typed: int) -> None:
        """Update lines typed in the active session."""
        if not self._current_session:
            return
        self._current_session["lines_typed"] += max(0, lines_typed)

    def end_session(self) -> dict:
        """End the active session, persist to disk and episodic memory."""
        if not self._current_session:
            return {"status": "no_active_session"}

        end_time = datetime.datetime.now(datetime.timezone.utc)
        start_time = datetime.datetime.fromisoformat(self._current_session["start"])
        duration = (end_time - start_time).total_seconds() / 60.0

        self._current_session["end"] = end_time.isoformat()
        self._current_session["duration_minutes"] = round(duration, 2)
        self._today_minutes += duration

        session = dict(self._current_session)
        self._current_session = None

        self._persist_session(session)

        goal_met = self._today_minutes >= self.DAILY_GOAL_MINUTES
        if goal_met:
            self.award_points(50, f"karpathy daily goal met — {self._today_minutes:.1f} min")
        else:
            self.award_points(20, f"karpathy partial session — {duration:.1f} min")

        logger.info(
            f"[VECTOR][code_typer] session ended — {duration:.1f} min, "
            f"total today={self._today_minutes:.1f}/{self.DAILY_GOAL_MINUTES} min, "
            f"lines={session['lines_typed']}, goal_met={goal_met}"
        )
        return {"status": "completed", "session": session, "daily_goal_met": goal_met}

    def _persist_session(self, session: dict) -> None:
        """Save session to JSON log file and episodic memory."""
        date_str = session["date"]
        log_file = self._runs_dir / f"sessions_{date_str}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(session) + "\n")
        except Exception as e:
            logger.error(f"[VECTOR][code_typer] persist failed: {e}")

        try:
            self._get_memory().store(
                event_type="karpathy_session",
                content=(
                    f"Karpathy session: {session['topic']} — "
                    f"{session['duration_minutes']:.1f} min, {session['lines_typed']} lines typed"
                ),
                tags=["karpathy", "learning", "code_typer"],
                source="code_typer",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][code_typer] episodic store failed: {e}")

    # ── Daily summary ─────────────────────────────────────────────────────────

    def get_today_summary(self) -> dict:
        """Return today's Karpathy progress."""
        date_str = datetime.date.today().isoformat()
        log_file = self._runs_dir / f"sessions_{date_str}.jsonl"
        sessions = []
        if log_file.exists():
            for line in log_file.read_text(encoding="utf-8").splitlines():
                try:
                    sessions.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)

        total_minutes = sum(s.get("duration_minutes", 0) for s in sessions)
        total_lines = sum(s.get("lines_typed", 0) for s in sessions)
        return {
            "date": date_str,
            "sessions": len(sessions),
            "total_minutes": round(total_minutes, 2),
            "total_lines": total_lines,
            "goal_met": total_minutes >= self.DAILY_GOAL_MINUTES,
            "goal_minutes": self.DAILY_GOAL_MINUTES,
        }

    def get_streak(self) -> int:
        """Count consecutive days with at least one session logged."""
        streak = 0
        today = datetime.date.today()
        for i in range(365):
            day = today - datetime.timedelta(days=i)
            log_file = self._runs_dir / f"sessions_{day.isoformat()}.jsonl"
            if log_file.exists() and log_file.stat().st_size > 0:
                streak += 1
            else:
                break
        return streak

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def check_daily_reminder(self) -> None:
        """Fire reminder if daily goal not yet met by 9 PM."""
        now = datetime.datetime.now()
        if now.hour < 21:
            return
        summary = self.get_today_summary()
        if not summary["goal_met"]:
            remaining = self.DAILY_GOAL_MINUTES - summary["total_minutes"]
            logger.warning(
                f"[VECTOR][code_typer] RULE 12 at risk — "
                f"{remaining:.0f} min remaining for today's Karpathy goal. Streak={self.get_streak()} days"
            )


    async def run(self, task: dict) -> dict:
        summary = self.get_today_summary()
        streak = self.get_streak()
        return {"status": "ok", "summary": summary, "streak": streak}


if __name__ == "__main__":
    import tempfile, os
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        with tempfile.TemporaryDirectory() as d:
            import core.config as _cfg
            original_runs = _cfg.CONFIG["karpathy"]["runs_dir"]
            _cfg.CONFIG["karpathy"]["runs_dir"] = d

            ct = CodeTyper(generation=1)
            assert ct.name == "CodeTyper"
            assert ct.district == "karpathy_lab"

            # Start → log progress → end
            ct.start_session("nanoGPT backprop", "train.py")
            ct.log_progress(15)
            result = ct.end_session()
            assert result["status"] == "completed"
            assert result["session"]["lines_typed"] == 15

            summary = ct.get_today_summary()
            assert summary["sessions"] == 1
            assert summary["total_lines"] == 15

            _cfg.CONFIG["karpathy"]["runs_dir"] = original_runs

        print(f"✅ code_typer OK  HP={ct.health_points}")

    asyncio.run(_smoke())
