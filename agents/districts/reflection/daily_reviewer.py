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
from core.memory.policy import PolicyMemory
from loguru import logger

_CHAIRMAN = CONFIG["models"]["chairman"]


class DailyReviewer(AgentBase):
    """
    2AM nightly reflection: fetch today's events → LLM analysis →
    update policy_memory → write Obsidian journal.
    RULE 11: vector-chairman (local), not Claude API.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DailyReviewer",
            district="reflection",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        self._policy = PolicyMemory()
        logger.info(f"[VECTOR][daily_reviewer] ready gen={generation} hp={self.health_points}")

    def _fetch_today(self) -> list[dict]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT event_type, content, tags, source, timestamp FROM episodic_memory "
                "WHERE timestamp > ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][daily_reviewer] fetch failed: {e}")
            return []

    def _analyse(self, events: list[dict], hydration: str) -> str:
        summary = "\n".join(
            f"[{e.get('timestamp','')[:16]}] {e.get('event_type','')}: {e.get('content','')[:120]}"
            for e in events[:60]
        )
        prompt = (
            f"Today's activity log ({len(events)} events):\n\n{summary}\n\n"
            "Write a structured daily review:\n"
            "## WINS\n## PATTERNS\n## IMPROVEMENTS\n"
            "## POLICY_UPDATES\n(rules: 'If X then always/never Y')\n"
            "## GROWTH_SCORE\n(0-10 with one-sentence reason)\n"
            "Be concise and specific."
        )
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(
                model=_CHAIRMAN,
                messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}],
                timeout=120.0,
            )
            if not text:
                raise ValueError("ollama_safe returned empty response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][daily_reviewer] LLM unavailable: {e}")
            return f"## SUMMARY\n{len(events)} events today. LLM reflection unavailable."

    def _extract_policy_rules(self, text: str) -> list[str]:
        rules, in_section = [], False
        for line in text.splitlines():
            if "## POLICY_UPDATES" in line:
                in_section = True
                continue
            if in_section and line.startswith("##"):
                break
            if in_section and line.strip():
                rules.append(line.strip())
        return rules

    async def review(self) -> bool:
        date_str = datetime.date.today().isoformat()
        events = self._fetch_today()
        if not events:
            events = [{"event_type": "idle", "content": "No activity today.", "timestamp": date_str, "tags": "", "source": "system"}]

        hydration = self._context.session_hydration_prompt()
        analysis = self._analyse(events, hydration)

        rules = self._extract_policy_rules(analysis)
        for i, rule in enumerate(rules[:10]):
            self._memory.remember(
                key=f"policy_rule:{date_str}:{i}",
                value=rule,
                category="behavioral_policy",
                confidence=0.75,
            )
            # RULE 7 — persist to policy_memory so decision_engine uses it (BOTH DIRECTIONS)
            action_type = f"behavioral_rule_{i}"
            situation_hash = f"daily_reflection:{date_str}:{rule[:60]}"
            import hashlib as _hl
            situation_hash = _hl.sha256(situation_hash.encode()).hexdigest()[:12]
            self._policy.update_from_outcome(
                action_type=action_type,
                situation_hash=situation_hash,
                reward=0.65,
            )
            logger.info(f"[VECTOR][reflection] Policy persisted: {action_type} reward=0.65")

        # Store daily lesson digest in semantic_memory for longer retention
        if rules:
            self._memory.remember(
                key=f"policy_lesson_{date_str}",
                value=str(rules[:10])[:500],
                category="policy_lesson",
                confidence=0.8,
            )

        for line in analysis.splitlines():
            if line.strip() and ("GROWTH_SCORE" in line or "/10" in line):
                self._memory.remember(
                    key=f"growth_score:{date_str}",
                    value=line.strip(),
                    category="growth",
                    confidence=0.9,
                )
                break

        self._memory.store_chain(
            situation="daily_reflection",
            goal_ids=["self_improvement"],
            steps=["fetch_events", "llm_analysis", "policy_update", "obsidian_write"],
            action="review",
            outcome=f"{len(events)} events; {len(rules)} policy rules",
            reward=0.85,
        )
        self._memory.store(
            event_type="daily_review",
            content=f"Daily review: {len(events)} events, {len(rules)} policy updates",
            tags=["reflection", "daily"],
            source="daily_reviewer",
        )

        try:
            self._obsidian.write_note(
                title=f"Reflection — {date_str}",
                content=f"## Daily Review — {date_str}\n\n{analysis}",
                folder="Reflections",
                tags=["reflection", "daily", "vector"],
            )
            self.award_points(50, f"daily review {date_str}")
            logger.info(f"[VECTOR][daily_reviewer] done: {len(events)} events, {len(rules)} rules")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][daily_reviewer] vault write failed: {e}")
            self.deduct_points(10, "vault write failed")
            return False

    async def run(self, task: dict) -> dict:
        """Governor dispatch interface."""
        ok = await self.review()
        return {"status": "ok" if ok else "error", "agent": self.name}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][daily_reviewer] run_forever — fires at 02:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 2 and 0 <= now.minute < 5:
                    await self.review()
            except Exception as e:
                logger.error(f"[VECTOR][daily_reviewer] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][daily_reviewer] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        bot = DailyReviewer()
        assert bot.health_points == 500
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Reflections").mkdir()
            bot._obsidian._vault = vault
            ok = await bot.review()
        print(f"OK daily_reviewer.py HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
