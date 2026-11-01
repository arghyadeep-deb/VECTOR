import sys
import uuid
import asyncio
import datetime
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_FOCUS = CONFIG["models"]["focus"]


class ExerciseLogger(AgentBase):
    """
    Logs exercise sessions from explicit user input or episodic event tags.
    Tracks weekly activity, nudges when sedentary for >2 days, writes to Obsidian.
    RULE 11: vector-focus (local), not Claude API.
    """

    SEDENTARY_THRESHOLD_DAYS = 2

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ExerciseLogger",
            district="health",
            generation=generation,
        )
        # RR-3.7B (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        # RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md): "log_exercise"
        # added -- Governor.dispatch()'s agent selection is an EXACT match
        # on `task_type in agent.capabilities` (governor.py); without this,
        # correct DISTRICT_TASK_MAP routing to "health" (also added this
        # mission) still left the actual executing agent to an HP-lottery
        # among health-district agents, confirmed live in production to
        # sometimes pick FatigueMonitor instead of this agent's own real
        # `run()` branch for this exact type.
        self.capabilities = ["exercise", "health", "log_exercise"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][exercise_logger] ready gen={generation}")

    def log_session(self, activity: str, duration_min: int, notes: str = "") -> bool:
        """Called manually or by voice intent to log an exercise session."""
        ts = datetime.datetime.now().isoformat()
        entry = f"{activity} {duration_min}min" + (f" — {notes}" if notes else "")
        self._memory.store(
            event_type="exercise_session",
            content=entry,
            tags=["health", "exercise", activity.lower().replace(" ", "_")],
            source="exercise_logger",
        )
        self._memory.remember(
            key=f"exercise:{datetime.date.today().isoformat()}",
            value=entry,
            category="health_exercise",
            confidence=0.95,
        )
        self.award_points(30, f"exercise logged: {activity}")
        logger.info(f"[VECTOR][exercise_logger] logged: {entry}")
        return True

    def _fetch_recent_sessions(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT content, timestamp FROM episodic_memory "
                "WHERE event_type = 'exercise_session' AND timestamp > ? "
                "ORDER BY timestamp DESC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][exercise_logger] fetch failed: {e}")
            return []

    def _days_since_last_exercise(self) -> int:
        sessions = self._fetch_recent_sessions(days=30)
        if not sessions:
            return 30
        try:
            last_ts = datetime.datetime.fromisoformat(sessions[0]["timestamp"])
            return (datetime.datetime.now() - last_ts).days
        except Exception:
            return 30

    def _weekly_summary(self, sessions: list[dict]) -> str:
        if not sessions:
            return "No exercise sessions this week."
        lines = [f"- {s['timestamp'][:10]}: {s['content']}" for s in sessions]
        return "\n".join(lines)

    def _get_suggestion(self, days_inactive: int, hydration: str) -> str:
        prompt = (
            f"Arghyadeep hasn't exercised in {days_inactive} days. He's a student developer.\n"
            "Suggest a specific, short (10-20 min) exercise routine he can do right now without equipment."
        )
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(model=_FOCUS, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=60.0)
            if not text:
                raise ValueError("empty response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][exercise_logger] LLM unavailable: {e}")
            return "10 min walk + 20 push-ups + 20 squats."

    async def weekly_report(self) -> bool:
        week_label = datetime.date.today().strftime("W%V-%Y")
        sessions = self._fetch_recent_sessions(days=7)
        days_inactive = self._days_since_last_exercise()

        hydration = self._context.session_hydration_prompt()
        suggestion = self._get_suggestion(days_inactive, hydration) if days_inactive >= self.SEDENTARY_THRESHOLD_DAYS else ""

        total_sessions = len(sessions)
        report = (
            f"# Exercise Log — {week_label}\n\n"
            f"**Sessions this week:** {total_sessions}\n\n"
            f"**Days since last session:** {days_inactive}\n\n"
            f"## Sessions\n{self._weekly_summary(sessions)}\n"
        )
        if suggestion:
            report += f"\n## Suggested Workout\n{suggestion}\n"
        report += f"\n---\n*auto-generated by ExerciseLogger*"

        try:
            self._obsidian.write_note(
                title=f"Exercise Log — {week_label}",
                content=report,
                folder="Health",
                tags=["health", "exercise", "weekly", "vector"],
            )
            self._memory.store(
                event_type="exercise_report",
                content=f"Weekly report: {total_sessions} sessions, {days_inactive}d inactive",
                tags=["health", "exercise"],
                source="exercise_logger",
            )
            self.award_points(20, f"exercise report {week_label}")
            logger.info(f"[VECTOR][exercise_logger] weekly report: {total_sessions} sessions")

            if days_inactive >= self.SEDENTARY_THRESHOLD_DAYS:
                logger.warning(f"[VECTOR][exercise_logger] sedentary alert: {days_inactive} days")
                self.deduct_points(5, "sedentary")

            return True
        except Exception as e:
            logger.error(f"[VECTOR][exercise_logger] write failed: {e}")
            self.deduct_points(5, "write failed")
            return False

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        if task.get("type") == "log_exercise":
            ok = self.log_session(p.get("activity", "walk"), p.get("duration_min", 30), p.get("notes", ""))
            return {"status": "ok" if ok else "error"}
        ok = await self.weekly_report()
        return {"status": "ok" if ok else "error"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][exercise_logger] run_forever — weekly report Sunday 09:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.weekday() == 6 and now.hour == 9 and 0 <= now.minute < 5:
                    await self.weekly_report()
            except Exception as e:
                logger.error(f"[VECTOR][exercise_logger] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][exercise_logger] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        bot = ExerciseLogger()
        assert bot.health_points == 500
        ok_log = bot.log_session("Running", 20, "Morning jog")
        assert ok_log
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Health").mkdir()
            bot._obsidian._vault = vault
            ok_report = await bot.weekly_report()
        print(f"OK exercise_logger.py HP={bot.health_points} log={ok_log} report={ok_report}")

    asyncio.run(_smoke())
