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

_CHAIRMAN = CONFIG["models"]["chairman"]
_REASONING = CONFIG["models"]["reasoning"]


class GrowthAnalyst(AgentBase):
    """
    Weekly growth analysis: trends in growth scores, recurring patterns,
    skill velocity, and 3-week rolling trajectory. Writes to Obsidian.
    RULE 11: local models only.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="GrowthAnalyst",
            district="reflection",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][growth_analyst] ready gen={generation}")

    def _fetch_growth_scores(self, days: int = 21) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT key, value, timestamp FROM semantic_memory "
                "WHERE category = 'growth' AND timestamp > ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][growth_analyst] fetch growth scores failed: {e}")
            return []

    def _fetch_policy_updates(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT key, value, timestamp FROM semantic_memory "
                "WHERE category = 'behavioral_policy' AND timestamp > ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][growth_analyst] fetch policies failed: {e}")
            return []

    def _fetch_recent_events(self, days: int = 7) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT event_type, content, tags, timestamp FROM episodic_memory "
                "WHERE timestamp > ? ORDER BY timestamp ASC LIMIT 200",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][growth_analyst] fetch events failed: {e}")
            return []

    def _analyse(self, growth_scores: list[dict], policies: list[dict], events: list[dict], hydration: str) -> str:
        scores_text = "\n".join(
            f"{s.get('timestamp','')[:10]}: {s.get('value','')}"
            for s in growth_scores
        ) or "No growth scores recorded yet."

        policies_text = "\n".join(
            f"- {p.get('value','')}" for p in policies[:20]
        ) or "No policy updates this week."

        event_types = {}
        for e in events:
            t = e.get("event_type", "unknown")
            event_types[t] = event_types.get(t, 0) + 1
        activity_summary = ", ".join(f"{k}:{v}" for k, v in sorted(event_types.items(), key=lambda x: -x[1])[:10])

        prompt = (
            f"Growth scores (last 21 days):\n{scores_text}\n\n"
            f"New policy rules (last 7 days):\n{policies_text}\n\n"
            f"Activity summary (last 7 days): {activity_summary}\n\n"
            "Provide a structured growth analysis:\n"
            "## TREND\n(Is growth score improving, declining, or flat? With evidence)\n"
            "## VELOCITY\n(Rate of skill/habit development — fast/medium/slow, and why)\n"
            "## RECURRING_PATTERNS\n(What keeps showing up — positive and negative)\n"
            "## BOTTLENECKS\n(What is holding back growth most?)\n"
            "## 3_WEEK_PROJECTION\n(Where will Arghyadeep be in 3 weeks at this rate?)\n"
            "## RECOMMENDED_FOCUS\n(Single most impactful thing to change this week)\n"
            "Be honest, specific, and data-driven."
        )
        try:
            import ollama
            r = ollama.chat(
                model=_REASONING,
                messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}],
            )
            return r["message"]["content"]
        except Exception as e:
            logger.warning(f"[VECTOR][growth_analyst] LLM unavailable: {e}")
            return f"## SUMMARY\n{len(events)} events, {len(growth_scores)} growth scores. Analysis unavailable."

    async def analyse(self) -> bool:
        week_label = datetime.date.today().strftime("W%V-%Y")
        growth_scores = self._fetch_growth_scores(days=21)
        policies = self._fetch_policy_updates(days=7)
        events = self._fetch_recent_events(days=7)

        hydration = self._context.session_hydration_prompt()
        analysis = self._analyse(growth_scores, policies, events, hydration)

        # Store summary in semantic memory
        for line in analysis.splitlines():
            if "RECOMMENDED_FOCUS" in line or line.strip().startswith("##"):
                continue
            if line.strip():
                self._memory.remember(
                    key=f"growth_analysis:{week_label}",
                    value=analysis[:500],
                    category="growth_analysis",
                    confidence=0.8,
                )
                break

        self._memory.store_chain(
            situation="growth_analysis",
            goal_ids=["self_improvement"],
            steps=["fetch_scores", "fetch_policies", "llm_analysis", "obsidian_write"],
            action="analyse",
            outcome=f"{len(growth_scores)} scores, {len(policies)} policies",
            reward=0.8,
        )

        try:
            self._obsidian.write_note(
                title=f"Growth Analysis — {week_label}",
                content=(
                    f"# Growth Analysis — {week_label}\n\n{analysis}\n\n"
                    f"---\n*{len(growth_scores)} growth scores · {len(events)} events · auto-generated*"
                ),
                folder="Reflections",
                tags=["growth", "analysis", "weekly", "vector"],
            )
            self._memory.store(
                event_type="growth_analysis",
                content=f"Growth analysis: {week_label}",
                tags=["growth", "weekly"],
                source="growth_analyst",
            )
            self.award_points(60, f"growth analysis {week_label}")
            logger.info(f"[VECTOR][growth_analyst] analysis complete: {week_label}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][growth_analyst] write failed: {e}")
            self.deduct_points(10, "write failed")
            return False

    async def run_forever(self) -> None:
        logger.info("[VECTOR][growth_analyst] run_forever — Sunday 02:30")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.weekday() == 6 and now.hour == 2 and 30 <= now.minute < 35:
                    await self.analyse()
            except Exception as e:
                logger.error(f"[VECTOR][growth_analyst] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][growth_analyst] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        bot = GrowthAnalyst()
        assert bot.health_points == 500
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Reflections").mkdir()
            bot._obsidian._vault = vault
            ok = await bot.analyse()
        print(f"OK growth_analyst.py HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
