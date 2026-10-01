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
        self.capabilities = ["analyse", "analysis", "growth", "progress", "reflect"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][growth_analyst] ready gen={generation}")

    def _fetch_growth_scores(self, days: int = 21) -> list[dict] | None:
        """None = the DB read FAILED (distinct from [] = no scores recorded)."""
        # semantic_memory's time column is `updated_at` (aware UTC ISO); there is no `timestamp`.
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT key, value, updated_at AS timestamp FROM semantic_memory "
                "WHERE category = 'growth' AND updated_at > ? ORDER BY updated_at ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning("[VECTOR][growth_analyst] fetch growth scores failed: {}", e)
            return None

    def _fetch_policy_updates(self, days: int = 7) -> list[dict] | None:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT key, value, updated_at AS timestamp FROM semantic_memory "
                "WHERE category = 'behavioral_policy' AND updated_at > ? ORDER BY updated_at ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning("[VECTOR][growth_analyst] fetch policies failed: {}", e)
            return None

    def _fetch_recent_events(self, days: int = 7) -> list[dict] | None:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
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
            logger.warning("[VECTOR][growth_analyst] fetch events failed: {}", e)
            return None

    def _analyse(self, growth_scores: list[dict], policies: list[dict], events: list[dict], hydration: str) -> str | None:
        """LLM analysis, or None when no model produced one (never a canned placeholder)."""
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
            + (
                "NOTE: fewer than 2 growth scores exist, so there is NO trend data. Under ## TREND and "
                "## 3_WEEK_PROJECTION write 'insufficient data' - do not infer a trend.\n\n"
                if len(growth_scores) < 2 else ""
            )
            + "## TREND\n(Is growth score improving, declining, or flat? With evidence)\n"
            "## VELOCITY\n(Rate of skill/habit development — fast/medium/slow, and why)\n"
            "## RECURRING_PATTERNS\n(What keeps showing up — positive and negative)\n"
            "## BOTTLENECKS\n(What is holding back growth most?)\n"
            "## 3_WEEK_PROJECTION\n(Where will Arghyadeep be in 3 weeks at this rate?)\n"
            "## RECOMMENDED_FOCUS\n(Single most impactful thing to change this week)\n"
            "Be honest, specific, and data-driven."
        )
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(model=_REASONING, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=120.0)
            if not text:
                raise ValueError("ollama_safe returned empty response")
            return text
        except Exception as e:
            logger.warning("[VECTOR][growth_analyst] LLM unavailable: {}", e)
            return None

    async def analyse(self) -> bool:
        # %G (ISO year) with %V (ISO week); %Y mislabels year-boundary weeks and overwrites old notes.
        week_label = datetime.date.today().strftime("W%V-%G")
        growth_scores = self._fetch_growth_scores(days=21)
        policies = self._fetch_policy_updates(days=7)
        events = self._fetch_recent_events(days=7)
        if growth_scores is None or policies is None or events is None:
            logger.error("[VECTOR][growth_analyst] analysis aborted: a data fetch failed")
            return False

        hydration = self._context.session_hydration_prompt()
        analysis = self._analyse(growth_scores, policies, events, hydration)
        if analysis is None:
            logger.error("[VECTOR][growth_analyst] analysis aborted: no LLM analysis available")
            return False

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
            self._memory.store_chain(
                situation="growth_analysis",
                goal_ids=["self_improvement"],
                steps=["fetch_scores", "fetch_policies", "llm_analysis", "obsidian_write"],
                action="analyse",
                outcome=f"{len(growth_scores)} scores, {len(policies)} policies",
                reward=0.8,
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
            logger.error("[VECTOR][growth_analyst] write failed: {}", e)
            self.deduct_points(10, "write failed")
            return False

    async def answer_reflection_question(self, query: str) -> str:
        """Answer a free-text question routed to GrowthAnalyst instead of
        blindly running analyse() — which writes a new Obsidian note and
        semantic-memory entries on every call regardless of what was
        actually asked (KNOWN_ISSUES bug pattern: a real, unrelated file-
        write side effect from a stray conversational message). Grounded
        in the agent's own real growth-score/policy history."""
        growth_scores = self._fetch_growth_scores(days=21)
        policies = self._fetch_policy_updates(days=7)
        if growth_scores is None or policies is None:
            return ""  # DB read failed: don't present "0 scores tracked" as fact
        context = (
            f"{len(growth_scores)} growth scores tracked (last 21 days), "
            f"{len(policies)} policy updates (last 7 days)."
        )
        prompt = (
            "You are VECTOR's GrowthAnalyst in the reflection district. "
            "Answer the owner's question using this real context — do not "
            f"invent data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            from core.inference.vectorcode_llm import chat
            hydration = self._context.session_hydration_prompt()
            text = chat(model=_REASONING, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=60.0)
            return (text or "").strip()
        except Exception as e:
            logger.warning(f"[VECTOR][growth_analyst] answer_reflection_question failed: {e}")
            return ""

    async def run(self, task: dict) -> dict:
        # 2026-08-06: run() used to fall through to self.analyse() (full
        # weekly growth analysis — writes Obsidian note, stores semantic
        # memory) for ANY unmatched task_type with no query text. Now
        # gated behind an explicit task_type; unmatched types with no
        # query return a grounded status instead of triggering side effects.
        task_type = task.get("type", "")
        query = (
            (task.get("params") or {}).get("query")
            or task.get("query")
            or task.get("text")
            or ""
        ).strip()
        if query:
            answer = await self.answer_reflection_question(query)
            if answer:
                self.award_points(10, "reflection_question_answered")
                return {"status": "ok", "response": answer, "agent": self.name}

        if task_type == "analyse":
            ok = await self.analyse()
            return {"status": "ok" if ok else "error"}

        # No query and no explicit analyse request — return status, no side effects
        return {"status": "ok", "response": "GrowthAnalyst ready. Use task_type='analyse' to run the weekly analysis, or ask a question."}

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
