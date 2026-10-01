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
        self.capabilities = ["progress", "project", "tracking"]
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

    def _query_git_activity(self, days: int = 7) -> list[str]:
        """Raises on DB failure so 'no commits' is never confused with 'unreadable'."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        cur = self._memory.conn.cursor()
        cur.execute(
            "SELECT content FROM episodic_memory "
            "WHERE (event_type = 'git_commit' OR event_type = 'auto_commit') "
            "AND timestamp > ? ORDER BY timestamp DESC LIMIT 30",
            (cutoff,),
        )
        return [row[0] for row in cur.fetchall()]

    def _query_progress_events(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        cur = self._memory.conn.cursor()
        cur.execute(
            "SELECT content, timestamp FROM episodic_memory "
            "WHERE event_type = 'project_progress' AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT 50",
            (cutoff,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _fetch_git_activity(self, days: int = 7) -> list[str]:
        """Pull recent auto-commit events from episodic_memory ([] on failure)."""
        try:
            return self._query_git_activity(days)
        except Exception as e:
            logger.warning("[VECTOR][progress_tracker] git fetch failed: {}", e)
            return []

    def _fetch_progress_events(self, days: int = 7) -> list[dict]:
        try:
            return self._query_progress_events(days)
        except Exception as e:
            logger.warning("[VECTOR][progress_tracker] progress fetch failed: {}", e)
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
            from core.inference.vectorcode_llm import chat
            text = chat(model=_FOCUS, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=60.0)
            if not text:
                raise ValueError("empty response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][progress_tracker] LLM unavailable: {e}")
            return f"{len(git_activity)} commits, {len(progress_events)} updates. Summary unavailable."

    async def weekly_report(self) -> bool:
        week_label = datetime.date.today().strftime("W%V-%Y")
        try:
            git_activity = self._query_git_activity(days=7)
            progress_events = self._query_progress_events(days=7)
        except Exception as e:
            # Never publish a "No commits this week" report built from a failed read.
            logger.error("[VECTOR][progress_tracker] weekly report aborted, data unreadable: {}", e)
            self.deduct_points(5, "progress data unreadable")
            return False

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

    async def answer_projects_question(self, query: str) -> str:
        """Answer a free-text question instead of blindly writing a new
        weekly progress report to the vault on every call, regardless of
        what was actually asked (KNOWN_ISSUES bug pattern: a real,
        unrelated file-write side effect from a stray conversational
        message). Grounded in real recent git/progress activity."""
        try:
            git_activity = self._query_git_activity(days=7)
            progress_events = self._query_progress_events(days=7)
            context = f"{len(git_activity)} commit(s), {len(progress_events)} progress update(s) in the last 7 days."
        except Exception as e:
            logger.warning("[VECTOR][progress_tracker] progress data unreadable: {}", e)
            context = "Recent progress data unavailable right now."
        prompt = (
            "You are VECTOR's ProgressTracker in the projects district. "
            "Answer the owner's question using this real context — do not "
            f"invent data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            from core.inference.vectorcode_llm import chat
            hydration = self._context.session_hydration_prompt()
            text = chat(model=_FOCUS, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=60.0)
            return (text or "").strip() or context
        except Exception as e:
            logger.warning(f"[VECTOR][progress_tracker] answer_projects_question failed: {e}")
            return context

    async def run(self, task: dict) -> dict:
        query = (
            (task.get("params") or {}).get("query")
            or task.get("query")
            or task.get("text")
            or ""
        ).strip()
        if query:
            answer = await self.answer_projects_question(query)
            if answer:
                self.award_points(10, "projects_question_answered")
                return {"status": "ok", "response": answer}

        ok = await self.weekly_report()
        return {"status": "ok" if ok else "error"}

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
