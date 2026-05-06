import sys
import uuid
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_FOCUS = CONFIG["models"]["focus"]


class ProgressTracker(AgentBase):
    """
    Tracks and reports project progress. Reads git activity, task completions,
    and manual updates from episodic_memory. Writes weekly progress reports.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ProgressTracker",
            district="projects",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][progress_tracker] ready gen={generation}")

    def log_progress(self, project_id: str, milestone: str, notes: str = "") -> None:
        """Log a progress update for a project."""
        self._memory.store(
            event_type="project_progress",
            content=f"[{project_id}] {milestone}" + (f" — {notes}" if notes else ""),
            tags=["projects", "progress", f"proj_{project_id}"],
            source="progress_tracker",
        )
        self._memory.remember(
            key=f"progress:{project_id}:{datetime.date.today().isoformat()}",
            value=milestone,
            category="project_progress",
            confidence=0.9,
        )
        self.award_points(15, f"progress logged: {project_id}")
        logger.info(f"[VECTOR][progress_tracker] logged: [{project_id}] {milestone}")

    def _fetch_git_activity(self, days: int = 7) -> list[str]:
        """Pull recent auto-commit events from episodic_memory."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT content FROM episodic_memory "
                "WHERE (event_type = 'git_commit' OR event_type = 'auto_commit') "
                "AND timestamp > ? ORDER BY timestamp DESC LIMIT 30",
                (cutoff,),
            )
            return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][progress_tracker] git fetch failed: {e}")
            return []

    def _fetch_progress_events(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT content, timestamp FROM episodic_memory "
                "WHERE event_type = 'project_progress' AND timestamp > ? "
                "ORDER BY timestamp DESC LIMIT 50",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][progress_tracker] progress fetch failed: {e}")
            return []

    def _summarise(self, git_activity: list[str], progress_events: list[dict], hydration: str) -> str:
        git_text = "\n".join(f"- {c[:100]}" for c in git_activity[:15]) or "No commits this week."
        progress_text = "\n".join(
            f"- {e['timestamp'][:10]}: {e['content'][:100]}" for e in progress_events
        ) or "No manual progress updates."

        prompt = (
            f"Weekly project progress summary:\n\n"
            f"Git commits:\n{git_text}\n\n"
            f"Progress updates:\n{progress_text}\n\n"
            "Write a brief weekly progress report (3-5 bullet points):\n"
            "- What was completed\n- Current blockers\n- Next week's priorities\n"
            "Be specific and direct."
        )
        try:
            import ollama
            r = ollama.chat(
                model=_FOCUS,
                messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}],
            )
            return r["message"]["content"]
        except Exception as e:
            logger.warning(f"[VECTOR][progress_tracker] LLM unavailable: {e}")
            return f"{len(git_activity)} commits, {len(progress_events)} updates. Summary unavailable."

    async def weekly_report(self) -> bool:
        week_label = datetime.date.today().strftime("W%V-%Y")
        git_activity = self._fetch_git_activity(days=7)
        progress_events = self._fetch_progress_events(days=7)

        hydration = self._context.session_hydration_prompt()
        summary = self._summarise(git_activity, progress_events, hydration)

        report = (
            f"# Progress Report — {week_label}\n\n"
            f"{summary}\n\n"
            f"---\n"
            f"*{len(git_activity)} commits · {len(progress_events)} updates · auto-generated*"
        )

        try:
            self._obsidian.write_note(
                title=f"Progress Report — {week_label}",
                content=report,
                folder="Projects",
                tags=["project", "progress", "weekly", "vector"],
            )
            self._memory.store(
                event_type="progress_report",
                content=f"Weekly progress report: {week_label}",
                tags=["projects", "progress"],
                source="progress_tracker",
            )
            self._memory.store_chain(
                situation="progress_reporting",
                goal_ids=["project_momentum"],
                steps=["fetch_git_activity", "fetch_progress_events", "llm_summarise", "obsidian_write"],
                action="weekly_report",
                outcome=f"{len(git_activity)} commits + {len(progress_events)} updates",
                reward=0.8,
            )
            self.award_points(25, f"progress report {week_label}")
            logger.info(f"[VECTOR][progress_tracker] weekly report: {week_label}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][progress_tracker] write failed: {e}")
            self.deduct_points(5, "write failed")
            return False

    async def run_forever(self) -> None:
        logger.info("[VECTOR][progress_tracker] run_forever — weekly report Sunday 10:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.weekday() == 6 and now.hour == 10 and 0 <= now.minute < 5:
                    await self.weekly_report()
            except Exception as e:
                logger.error(f"[VECTOR][progress_tracker] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][progress_tracker] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        bot = ProgressTracker()
        assert bot.health_points == 500
        bot.log_progress("vec001", "Completed Phase 2 districts", "all 4 districts written")
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Projects").mkdir()
            bot._obsidian._vault = vault
            ok = await bot.weekly_report()
        print(f"OK progress_tracker.py HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
