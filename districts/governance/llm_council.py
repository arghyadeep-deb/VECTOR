import sys
import re
import uuid
import asyncio
import datetime
from collections import defaultdict
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_COUNCIL_MEMBERS = [
    CONFIG["models"]["reasoning"],           # vector-reasoning (qwen3:14b) — step-by-step
    CONFIG["models"]["r1"],                  # vector-r1 (deepseek-r1:14b) — chain-of-thought
    CONFIG["models"]["dev"],                 # vector-dev (devstral:24b) — code+logic specialist
]
_CHAIRMAN = CONFIG["models"]["chairman"]     # vector-chairman (gemma4:31b)


class LLMCouncil(AgentBase):
    """
    3-stage deliberative council for high-stakes VECTOR decisions.

    Stage 1: Each member answers the question independently.
    Stage 2: Each member ranks the others' answers anonymously.
    Stage 3: Chairman synthesizes the final verdict.

    HP gate:   requester must have >= CONFIG["council"]["hp_gate"] HP (700).
    Throttle:  max CONFIG["council"]["max_per_week"] sessions per week (10).
    RULE 11:   all LLM calls via Ollama (no Claude API at runtime).
    RULE 1:    session_hydration_prompt() before every LLM call.
    RULE 8:    every session stored in reasoning_chains.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="LLMCouncil",
            district="governance",
            generation=generation,
        )
        self.capabilities = ["council", "decision", "decision_made", "governance", "high", "high_stakes", "security_alert", "vote"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][llm_council] ready gen={generation} hp={self.health_points}")
        # Phase 2B: subscribe to high-stakes decision events
        self.subscribe_to("decision_made")
        self.subscribe_to("security_alert")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Convene council on high-stakes events."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        data = event.get("data", {})
        if et == "security_alert" or (et == "decision_made" and data.get("stakes") in ("high", "critical")):
            try:
                logger.info(f"[VECTOR][llm_council] event-triggered convene: {et}")
                await self.convene(
                    question=f"Event {et}: {str(data)[:150]}. Should VECTOR take action?",
                    stakes="high", requester_hp=self.health_points,
                )
            except Exception as e:
                logger.debug(f"[VECTOR][llm_council] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    # ── Throttle ───────────────────────────────────────────────────────────────

    def _week_key(self) -> str:
        today = datetime.date.today()
        iso = today.isocalendar()
        return f"council_sessions:{iso.year}:W{iso.week:02d}"

    def _sessions_this_week(self) -> int:
        result = self._memory.recall_fact(self._week_key())
        try:
            return int(result["value"]) if result is not None else 0
        except (ValueError, TypeError, KeyError):
            return 0

    def _increment_weekly_count(self) -> None:
        self._memory.remember(
            key=self._week_key(),
            value=str(self._sessions_this_week() + 1),
            category="council_throttle",
            confidence=1.0,
        )

    # ── Ollama call ────────────────────────────────────────────────────────────

    def _call_model(self, model: str, system: str, user: str) -> str:
        """Ollama call via ollama_safe — RULE 11: no Claude API at runtime."""
        try:
            from core.inference.vectorcode_llm import chat
            from core.prompt_library import get_library as _gl
            _lib = _gl().get_for_agent("llm_council") or ""
            _sys = (system + "\n\n" + _lib).strip() if _lib else system
            return chat(
                model=model,
                messages=[
                    {"role": "system", "content": _sys},
                    {"role": "user", "content": user},
                ],
                timeout=120.0,
            ) or ""
        except Exception as e:
            logger.warning(f"[VECTOR][llm_council] {model} failed: {e}")
            return ""

    # ── Stage 1 ────────────────────────────────────────────────────────────────

    async def _stage1_collect(self, question: str, hydration: str) -> list[dict]:
        """Each council member answers the question independently."""
        results = []
        for model in _COUNCIL_MEMBERS:
            # RULE 2 — run blocking Ollama call off the event loop thread
            text = await asyncio.to_thread(
                self._call_model,
                model,
                hydration,
                f"As a council member, answer this question thoroughly:\n\n{question}",
            )
            if text:
                results.append({"model": model, "response": text})
                logger.info(f"[VECTOR][llm_council] stage1 {model}: {len(text)} chars")
        return results

    # ── Stage 2 ────────────────────────────────────────────────────────────────

    async def _stage2_rank(
        self, question: str, hydration: str, stage1: list[dict]
    ) -> tuple[list[dict], dict]:
        """Each member ranks the others' responses (blind labels A/B/C…)."""
        labels = [chr(65 + i) for i in range(len(stage1))]
        label_to_model = {f"Response {lbl}": r["model"] for lbl, r in zip(labels, stage1)}

        responses_text = "\n\n".join(
            f"Response {lbl}:\n{r['response']}"
            for lbl, r in zip(labels, stage1)
        )

        ranking_prompt = (
            f"Question: {question}\n\n"
            f"Evaluate these anonymized responses:\n\n{responses_text}\n\n"
            "Briefly evaluate each response, then end your reply with exactly:\n"
            "FINAL RANKING:\n1. Response X\n2. Response Y\n..."
        )

        results = []
        for model in _COUNCIL_MEMBERS:
            # RULE 2 — run blocking Ollama call off the event loop thread
            text = await asyncio.to_thread(self._call_model, model, hydration, ranking_prompt)
            if text:
                parsed = self._parse_ranking(text)
                results.append({"model": model, "ranking": text, "parsed": parsed})
                logger.info(f"[VECTOR][llm_council] stage2 {model}: ranked {parsed}")

        return results, label_to_model

    # ── Stage 3 ────────────────────────────────────────────────────────────────

    async def _stage3_synthesize(
        self, question: str, hydration: str, stage1: list[dict], stage2: list[dict]
    ) -> str:
        """Chairman synthesizes stage1 + stage2 into a single verdict."""
        stage1_text = "\n\n".join(
            f"Model: {r['model']}\nResponse: {r['response']}" for r in stage1
        )
        stage2_text = "\n\n".join(
            f"Model: {r['model']}\nRanking evaluation:\n{r['ranking']}" for r in stage2
        )

        chairman_prompt = (
            f"Original Question: {question}\n\n"
            f"STAGE 1 — Individual Responses:\n{stage1_text}\n\n"
            f"STAGE 2 — Peer Rankings:\n{stage2_text}\n\n"
            "As Chairman, synthesize the collective wisdom into a single definitive answer. "
            "Identify consensus, weigh rankings, and be decisive."
        )

        text = await asyncio.to_thread(self._call_model, _CHAIRMAN, hydration, chairman_prompt)
        if not text:
            text = stage1[0]["response"] if stage1 else "Council failed to produce a verdict."
            logger.warning("[VECTOR][llm_council] chairman unavailable — using best stage1 fallback")
        return text

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_ranking(text: str) -> list[str]:
        if "FINAL RANKING:" in text:
            section = text.split("FINAL RANKING:", 1)[1]
            matches = re.findall(r'\d+\.\s*(Response [A-Z])', section)
            if matches:
                return matches
        return re.findall(r'Response [A-Z]', text)

    @staticmethod
    def _calculate_aggregate(stage2: list[dict], label_to_model: dict) -> list[dict]:
        positions: dict[str, list[int]] = defaultdict(list)
        for r in stage2:
            for pos, label in enumerate(r["parsed"], start=1):
                if label in label_to_model:
                    positions[label_to_model[label]].append(pos)
        agg = [
            {"model": m, "avg_rank": round(sum(ps) / len(ps), 2)}
            for m, ps in positions.items()
        ]
        agg.sort(key=lambda x: x["avg_rank"])
        return agg

    # ── Public API ─────────────────────────────────────────────────────────────

    async def convene(
        self,
        question: str,
        stakes: str = "high",
        requester_hp: int = 500,
        context_tags: list[str] | None = None,
    ) -> dict:
        """
        Run a full 3-stage council session.

        Returns dict with: verdict, session_id, stage1, stage2, aggregate_rankings.
        Returns early with a message dict if HP gate or throttle blocks the session.
        """
        date_str = datetime.date.today().isoformat()
        session_id = str(uuid.uuid4())[:8]

        # HP gate — NOTE (#14): At startup all agents have 500 HP (below 700 gate).
        # The Governor (VECTOR itself) always has effective HP=1000 and can always convene council.
        # Individual agents earn council access through performance.
        hp_gate = CONFIG["council"]["hp_gate"]
        if requester_hp < hp_gate:
            logger.warning(
                f"[VECTOR][llm_council] HP gate: requester_hp={requester_hp} < {hp_gate}"
            )
            return {
                "verdict": f"HP gate: requester needs {hp_gate} HP, has {requester_hp}.",
                "session_id": session_id,
                "stage1": [], "stage2": [], "aggregate_rankings": [],
            }

        # Weekly throttle
        sessions_used = self._sessions_this_week()
        max_sessions = CONFIG["council"]["max_per_week"]
        if sessions_used >= max_sessions:
            logger.warning(f"[VECTOR][llm_council] throttle: {sessions_used}/{max_sessions}")
            return {
                "verdict": f"Council throttled: {sessions_used}/{max_sessions} sessions this week.",
                "session_id": session_id,
                "stage1": [], "stage2": [], "aggregate_rankings": [],
            }

        # RULE 1 — session hydration before every LLM call
        hydration = self._context.session_hydration_prompt()

        logger.info(f"[VECTOR][llm_council] session {session_id} — stakes={stakes}")

        # Stage 1
        stage1 = await self._stage1_collect(question, hydration)
        if not stage1:
            self.deduct_points(15, "council: all members failed stage1")
            return {
                "verdict": "All council models failed to respond.",
                "session_id": session_id,
                "stage1": [], "stage2": [], "aggregate_rankings": [],
            }

        # Stage 2
        stage2, label_to_model = await self._stage2_rank(question, hydration, stage1)

        # Stage 3
        verdict = await self._stage3_synthesize(question, hydration, stage1, stage2)

        # Aggregate
        aggregate = self._calculate_aggregate(stage2, label_to_model)

        # Increment throttle counter
        self._increment_weekly_count()

        # RULE 8 — store in reasoning_chains
        reward = 0.85 if stage2 else 0.6
        self._memory.store_chain(
            situation=f"council_session:{stakes}",
            goal_ids=["high_stakes_decision"],
            steps=["stage1_collect", "stage2_rank", "stage3_synthesize"],
            action="convene",
            outcome=f"{len(stage1)} members responded; verdict: {verdict[:80]}",
            reward=reward,
        )
        self._memory.store(
            event_type="council_session",
            content=f"Council {session_id}: {question[:80]}",
            tags=["council", "governance", stakes] + (context_tags or []),
            source="llm_council",
        )

        # Write to Obsidian Council/
        note_lines = [
            f"## Council Session — {date_str}\n",
            f"**Session:** `{session_id}`  **Stakes:** {stakes}  **Requester HP:** {requester_hp}\n",
            f"### Question\n\n{question}\n",
            "### Stage 1 — Individual Responses\n",
        ]
        for r in stage1:
            note_lines.append(f"#### {r['model']}\n{r['response']}\n")
        note_lines.append("### Stage 2 — Peer Rankings\n")
        for r in stage2:
            note_lines.append(f"**{r['model']}**: `{r['parsed']}`\n")
        if aggregate:
            note_lines.append("### Aggregate Rankings\n")
            for i, a in enumerate(aggregate, 1):
                note_lines.append(f"{i}. {a['model']} (avg rank: {a['avg_rank']})")
        note_lines.append(f"\n### Chairman Verdict\n\n{verdict}")
        note_content = "\n".join(note_lines)

        try:
            self._obsidian.write_note(
                title=f"Council — {session_id} — {date_str}",
                content=note_content,
                folder="Council",
                tags=["council", "governance", stakes, "vector"],
            )
            self.award_points(50, f"council session {session_id}")
            logger.info(f"[VECTOR][llm_council] session {session_id} complete — HP={self.health_points}")
        except Exception as e:
            logger.error(f"[VECTOR][llm_council] vault write failed: {e}")
            self.deduct_points(10, "vault write failed")

        return {
            "verdict": verdict,
            "session_id": session_id,
            "stage1": stage1,
            "stage2": stage2,
            "aggregate_rankings": aggregate,
        }

    async def run(self, task: dict) -> dict:
        """Governor dispatch interface.

        Bug fixed (KNOWN_ISSUES bug-pattern sweep): this only ever checked
        params["question"] and fell back to the raw task_type string (e.g.
        "answer_question") as the literal question text — the real chat
        entry point (governor.dispatch()) actually populates the free-text
        message under params["query"] (per governor.py's own taint-tracking
        comment), so a real conversational question routed here was never
        read at all; the council would convene on its own task_type label
        instead of what the owner actually asked. Now checks the real
        field first, only falling back to the generic prompt when there is
        genuinely no question text anywhere.
        """
        p = task.get("params", {})
        question = (
            p.get("question")
            or p.get("query")
            or task.get("query")
            or task.get("text")
            or task.get("type", "What should VECTOR do next?")
        )
        stakes = p.get("stakes", "medium")
        requester_hp = p.get("requester_hp", 0)  # fail-closed: missing HP = blocked by gate (default 700 bypasses it)
        return await self.convene(question=question, stakes=stakes, requester_hp=requester_hp)

    # ── Loop (event-driven agent — listens for convene requests) ──────────────

    async def run_forever(self) -> None:
        """RULE 2 — never crashes. Council is event-driven; this loop keeps the agent alive."""
        logger.info("[VECTOR][llm_council] run_forever started")
        while self.is_alive:
            try:
                for _ in range(60):
                    if not self.is_alive:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[VECTOR][llm_council] tick error: {e}")
                self.deduct_points(5, "tick error")
        logger.warning("[VECTOR][llm_council] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    import tempfile

    async def _smoke():
        bot = LLMCouncil()
        assert bot.health_points == 500
        assert bot.name == "LLMCouncil"
        assert bot.district == "governance"

        # HP gate test (requester_hp below gate)
        result = await bot.convene(
            question="What is 2+2?",
            stakes="high",
            requester_hp=100,
        )
        assert "HP gate" in result["verdict"], f"Expected HP gate block, got: {result['verdict']}"

        # Full session with real vault dir
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Council").mkdir()
            bot._obsidian._vault = vault

            result = await bot.convene(
                question="Should VECTOR prioritize speed or accuracy in responses?",
                stakes="high",
                requester_hp=750,
            )
            assert isinstance(result, dict)
            assert "verdict" in result
            assert "session_id" in result

        print(f"✅ llm_council.py OK  HP={bot.health_points}  verdict_len={len(result['verdict'])}")

    asyncio.run(_smoke())
