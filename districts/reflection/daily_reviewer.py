import re
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
from core.memory.policy import PolicyMemory
from loguru import logger

_CHAIRMAN = CONFIG["models"]["chairman"]
_SCORE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*10\b")


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
        self.capabilities = ["daily_review", "journal", "reflect", "reflection", "review", "task_completed"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        self._policy = PolicyMemory()
        logger.info(f"[VECTOR][daily_reviewer] ready gen={generation} hp={self.health_points}")
        # Phase 2B: subscribe to end-of-day events
        self.subscribe_to("task_completed")
        self.subscribe_to("memory_stored")
        self._event_review_date: str | None = None

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Trigger daily review on significant events."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        # Only trigger review if it's late in the day (22:00+)
        hour = datetime.datetime.now().hour
        today = datetime.date.today().isoformat()
        # Once per day: every task_completed/memory_stored after 22:00 used to run the full
        # LLM review + policy writes + HP award again.
        if et in ("task_completed", "memory_stored") and hour >= 22 and self._event_review_date != today:
            try:
                logger.info("[VECTOR][daily_reviewer] event-triggered review: {}", et)
                if await self.review():
                    self._event_review_date = today
            except Exception as e:
                logger.warning("[VECTOR][daily_reviewer] handle_event failed: {}", e)
        return {"status": "handled", "agent": self.name, "event": et}

    def _fetch_today(self) -> list[dict] | None:
        """Last 24h of events. None = the DB read FAILED (distinct from [] = genuinely no activity)."""
        # episodic_memory.timestamp is stored as aware UTC ISO text; compare like with like
        # (a naive local cutoff shifted the window by the UTC offset).
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            # Exclude test-seeded rows — integration tests that write to the live DB must
            # never surface in the owner's nightly reflection (A6 placeholder bug, 2026-07-08)
            cur.execute(
                "SELECT event_type, content, tags, source, timestamp FROM episodic_memory "
                "WHERE timestamp > ? AND COALESCE(source, '') NOT LIKE '%test%' "
                "AND COALESCE(tags, '') NOT LIKE '%\"test\"%' "
                "ORDER BY timestamp ASC",
                (cutoff,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning("[VECTOR][daily_reviewer] fetch failed: {}", e)
            return None

    def _analyse(self, events: list[dict], hydration: str) -> str | None:
        """LLM analysis, or None when no model produced one (never a canned placeholder)."""
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
            # domain="summarization" — catalog chain of free cloud models with ollama
            # terminal, so the 2AM review survives Ollama being down (was: chairman-only,
            # which produced "LLM reflection unavailable" placeholder journals).
            text = chat(
                model=_CHAIRMAN,
                messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}],
                timeout=120.0,
                district="reflection",
                domain="summarization",
            )
            if not text:
                raise ValueError("summarization chain returned empty response")
            return text
        except Exception as e:
            logger.warning("[VECTOR][daily_reviewer] LLM unavailable: {}", e)
            return None

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
        if events is None:
            logger.error("[VECTOR][daily_reviewer] review aborted: event fetch failed")
            return False

        if events:
            hydration = self._context.session_hydration_prompt()
            analysis = self._analyse(events, hydration)
            if analysis is None:
                logger.error("[VECTOR][daily_reviewer] review aborted: no LLM analysis available")
                return False
        else:
            # Genuinely no activity: say so plainly; never let the LLM invent wins/policy/score.
            analysis = "## SUMMARY\nNo activity was recorded in the last 24 hours."

        rules = self._extract_policy_rules(analysis) if events else []
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

        # Only a real "N/10" under the GROWTH_SCORE heading counts; the heading line itself
        # used to be stored as the "score" (and no-data days must not get a score at all).
        if events:
            lines = analysis.splitlines()
            start = next((i for i, ln in enumerate(lines) if "GROWTH_SCORE" in ln), None)
            for line in (lines[start + 1:] if start is not None else []):
                if line.startswith("##"):
                    break
                if _SCORE_RE.search(line):
                    self._memory.remember(
                        key=f"growth_score:{date_str}",
                        value=line.strip(),
                        category="growth",
                        confidence=0.9,
                    )
                    break

        # A5: prepend top pending hypotheses as "I noticed" lines
        _hyp_section = ""
        try:
            from core.brain.suggestion_queue import SuggestionQueue
            _sq = SuggestionQueue()
            _top = _sq.get_top_pending(limit=3)
            if _top:
                _lines = "\n".join(f"- I noticed: {h['hypothesis'][:120]}" for h in _top)
                _hyp_section = f"## Proactive Insights\n{_lines}\n\n"
                logger.info("[VECTOR][daily_reviewer] {} proactive insights added to briefing", len(_top))
            _sq.close()
        except Exception as _hq_err:
            logger.debug("[VECTOR][daily_reviewer] SuggestionQueue briefing skipped: {}", _hq_err)

        # A6: add cross-domain patterns section from SynthesisBridge
        _patterns_section = ""
        try:
            from core.brain.synthesis_bridge import SynthesisBridge
            _sb = SynthesisBridge()
            _patterns = _sb.get_recent_patterns(days=1)
            if _patterns:
                _pat_lines = "\n".join(f"- {p[:160]}" for p in _patterns[:5])
                _patterns_section = f"## Cross-domain patterns\n{_pat_lines}\n\n"
                logger.info("[VECTOR][daily_reviewer] {} cross-domain patterns added to briefing", len(_patterns))
        except Exception as _pb_err:
            logger.debug("[VECTOR][daily_reviewer] SynthesisBridge patterns skipped: {}", _pb_err)

        try:
            self._obsidian.write_note(
                title=f"Reflection — {date_str}",
                content=f"## Daily Review — {date_str}\n\n{_hyp_section}{_patterns_section}{analysis}",
                folder="Reflections",
                tags=["reflection", "daily", "vector"],
            )
        except Exception as e:
            logger.error("[VECTOR][daily_reviewer] vault write failed: {}", e)
            # Record the failure honestly (was: chain reward 0.85 "obsidian_write" stored before the write).
            self._memory.store_chain(
                situation="daily_reflection",
                goal_ids=["self_improvement"],
                steps=["fetch_events", "llm_analysis", "policy_update", "obsidian_write_failed"],
                action="review",
                outcome=f"vault write failed; {len(events)} events; {len(rules)} policy rules",
                reward=0.2,
            )
            self.deduct_points(10, "vault write failed")
            return False

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
        self.award_points(50, f"daily review {date_str}")
        logger.info("[VECTOR][daily_reviewer] done: {} events, {} rules", len(events), len(rules))
        return True

    async def answer_reflection_question(self, query: str) -> str:
        """Answer a free-text question routed to DailyReviewer instead of
        blindly running the full 2AM-style review() pipeline — which writes
        real new policy rules into PolicyMemory (used by decision_engine)
        and a new Obsidian note on every call, regardless of what was
        actually asked (KNOWN_ISSUES bug pattern: a real, unrelated side
        effect from a stray conversational message). Grounded in today's
        real activity log; no invented data."""
        events = self._fetch_today()
        if events is None:
            return ""  # DB read failed: don't tell the LLM "no activity" and let it answer from nothing
        summary = "\n".join(
            f"[{e.get('timestamp','')[:16]}] {e.get('event_type','')}: {e.get('content','')[:120]}"
            for e in events[:30]
        ) or "No activity logged today."
        prompt = (
            "You are VECTOR's DailyReviewer in the reflection district. "
            "Answer the owner's question using today's real activity log "
            f"below — do not invent data you don't have:\n\n{summary}\n\n"
            f"Question: {query}"
        )
        try:
            from core.inference.vectorcode_llm import chat
            hydration = self._context.session_hydration_prompt()
            text = chat(
                model=_CHAIRMAN,
                messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}],
                timeout=60.0,
                district="reflection",
                domain="summarization",
            )
            return (text or "").strip()
        except Exception as e:
            logger.warning(f"[VECTOR][daily_reviewer] answer_reflection_question failed: {e}")
            return ""

    async def run(self, task: dict) -> dict:
        """Governor dispatch interface."""
        # 2026-08-06: run() used to fall through to self.review() (full
        # nightly pipeline — writes Obsidian note, mutates policy memory)
        # for ANY unmatched task_type with no query text. Now gated
        # behind an explicit task_type; unmatched types with no query
        # return a grounded status instead of triggering side effects.
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

        if task_type == "review":
            ok = await self.review()
            return {"status": "ok" if ok else "error", "agent": self.name}

        # No query and no explicit review request — return status, no side effects
        return {"status": "ok", "response": "DailyReviewer ready. Use task_type='review' to run the nightly review, or ask a question.", "agent": self.name}

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
