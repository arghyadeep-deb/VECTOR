import sys
import os
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


class ConsolidationBot(AgentBase):
    """
    Compresses old episodic memory into semantic summaries.
    Writes daily reflections to Obsidian. Runs once per day.
    """

    CONSOLIDATION_DAYS = 30
    REFLECTION_HOURS = 24
    # Forgetting horizon: raw episodes older than this are pruned AFTER they have
    # been summarized into semantic_memory + mem0. 3x the consolidation window so
    # nothing is forgotten before it has been consolidated.
    RETENTION_DAYS = 90

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ConsolidationBot",
            district="memory_curator",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        mem0_enabled = os.getenv("VECTOR_MEM0_ENABLE") == "1"
        # mem0 episodic layer — self-hosted OSS only (RULE 11, never MemoryClient)
        try:
            if not mem0_enabled:
                raise ImportError("mem0 disabled; set VECTOR_MEM0_ENABLE=1 to enable")
            from mem0 import Memory as _Mem0
            self._mem0 = _Mem0()
            logger.info("[VECTOR][consolidation_bot] mem0 episodic layer active")
        except ImportError:
            self._mem0 = None
            logger.info("[VECTOR][consolidation_bot] mem0 not installed — EpisodicMemory only")
        except Exception as _e:
            self._mem0 = None
            logger.warning(f"[VECTOR][consolidation_bot] mem0 init failed: {_e}")
        logger.info(f"[VECTOR][consolidation_bot] ready gen={generation} hp={self.health_points}")
        # Phase 2B: subscribe to memory events
        self.subscribe_to("memory_stored")
        self.subscribe_to("research_complete")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Run consolidation when memory fills up."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("memory_stored", "research_complete"):
            try:
                logger.info(f"[VECTOR][consolidation_bot] event-triggered consolidation: {et}")
                await self.run({"type": "consolidate", "params": {"source": "event"}})
            except Exception as e:
                logger.debug(f"[VECTOR][consolidation_bot] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    # ── mem0 helper ───────────────────────────────────────────────────────────

    def _store_to_mem0(self, content: str, role: str = "assistant") -> None:
        """Store content to mem0 episodic layer alongside EpisodicMemory."""
        if not self._mem0:
            return
        try:
            self._mem0.add(
                [{"role": role, "content": content}],
                user_id="vector",
                metadata={"source": "consolidation_bot"},
            )
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] mem0 store failed: {e}")

    # ── Episode helpers ────────────────────────────────────────────────────────

    def _fetch_old_episodes(self, days_old: int) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old)
        ).isoformat()
        # KNOWN_ISSUES #21: a cached self._memory.conn never sees
        # get_db_connection()'s self-healing reopen-if-closed logic — see
        # pattern_finder.py's _fetch_window() for the full explanation.
        # get_temp_cursor() always resolves a live connection.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM episodic_memory WHERE timestamp < ? ORDER BY timestamp ASC LIMIT 200",
                (cutoff,),
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetch_recent_episodes(self, hours: int) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        ).isoformat()
        # KNOWN_ISSUES #21 — see _fetch_old_episodes() above.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM episodic_memory WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 100",
                (cutoff,),
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # ── Core tasks ─────────────────────────────────────────────────────────────

    async def consolidate_old_episodes(self) -> int:
        """Compress episodes older than CONSOLIDATION_DAYS into semantic_memory summaries."""
        episodes = self._fetch_old_episodes(self.CONSOLIDATION_DAYS)
        if not episodes:
            logger.info("[VECTOR][consolidation_bot] no old episodes to consolidate")
            return 0

        batch_text = "\n".join(
            f"[{ep['timestamp'][:10]}] {ep['event_type']}: {ep['content'][:120]}"
            for ep in episodes[:50]
        )
        hydration = self._context.session_hydration_prompt()  # RULE 1

        try:
            if os.getenv("VECTOR_MEMORY_CURATOR_LLM") != "1":
                raise RuntimeError("memory curator LLM disabled; set VECTOR_MEMORY_CURATOR_LLM=1 to enable")
            from core.inference.vectorcode_llm import chat
            summary = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration},
                    {
                        "role": "user",
                        "content": (
                            "You are VECTOR's ConsolidationBot. Compress these episodic memories "
                            "into 3-5 key semantic facts. Return as bullet points.\n\n"
                            + batch_text
                        ),
                    },
                ],
                timeout=2.0,
            )
            if not summary:
                raise RuntimeError("empty model response")
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] LLM unavailable: {e}")
            first_ts = episodes[0]["timestamp"][:10]
            last_ts = episodes[-1]["timestamp"][:10]
            summary = f"Compressed {len(episodes)} episodes ({first_ts} to {last_ts})"

        key = f"consolidation:{datetime.date.today().isoformat()}"
        self._memory.remember(key, summary, category="consolidation", confidence=0.8)
        self._store_to_mem0(f"Memory consolidation [{key}]: {summary[:400]}")
        self._memory.store_chain(
            situation="memory_consolidation",
            goal_ids=["maintain_memory"],
            steps=["fetch_old_episodes", "summarize_llm", "store_semantic"],
            action="consolidate",
            outcome=f"compressed {len(episodes)} episodes",
            reward=0.8,
        )
        self.award_points(30, f"consolidated {len(episodes)} old episodes")
        logger.info(f"[VECTOR][consolidation_bot] consolidated {len(episodes)} episodes → {key}")

        # Forgetting (roadmap #7): now that old episodes are summarized into
        # semantic_memory + mem0, prune the redundant raw rows past the retention
        # horizon so the episodic DB stays bounded in 24/7 operation.
        try:
            forgotten = self._memory.prune_old_episodes(self.RETENTION_DAYS)
            if forgotten:
                self.award_points(10, f"forgot {forgotten} stale raw episodes")
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] forgetting pass skipped: {e}")

        try:
            from core.engine.memory_tree.tree_builder import get_shared_tree
            tree_forgotten = get_shared_tree().prune_old_chunks(self.RETENTION_DAYS)
            if tree_forgotten:
                self.award_points(5, f"forgot {tree_forgotten} stale tree chunks")
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] memory_tree forgetting pass skipped: {e}")

        return len(episodes)

    async def write_daily_reflection(self) -> bool:
        """Summarize last 24h of episodic memory → write to Obsidian Reflections/."""
        episodes = self._fetch_recent_episodes(hours=self.REFLECTION_HOURS)
        date_str = datetime.date.today().isoformat()
        title = f"Daily Reflection — {date_str}"

        if not episodes:
            logger.info("[VECTOR][consolidation_bot] no recent episodes — writing minimal reflection")
            reflection = "No significant events logged in the last 24 hours."
        else:
            episodes_text = "\n".join(
                f"- [{ep['event_type']}] {ep['content'][:100]}"
                for ep in episodes[:30]
            )
            hydration = self._context.session_hydration_prompt()  # RULE 1

            try:
                if os.getenv("VECTOR_MEMORY_CURATOR_LLM") != "1":
                    raise RuntimeError("memory curator LLM disabled; set VECTOR_MEMORY_CURATOR_LLM=1 to enable")
                from core.inference.vectorcode_llm import chat
                reflection = chat(
                    model=CONFIG["models"]["reasoning"],
                    messages=[
                        {"role": "system", "content": hydration},
                        {
                            "role": "user",
                            "content": (
                                "Write a concise daily reflection for VECTOR based on these events. "
                                "2-3 paragraphs: what happened, what was learned, what to improve.\n\n"
                                + episodes_text
                            ),
                        },
                    ],
                    timeout=2.0,
                )
                if not reflection:
                    raise RuntimeError("empty model response")
            except Exception as e:
                logger.warning(f"[VECTOR][consolidation_bot] LLM unavailable: {e}")
                reflection = (
                    f"Daily summary: {len(episodes)} events logged.\n\n" + episodes_text[:800]
                )

        try:
            self._obsidian.write_note(
                title=title,
                content=reflection,
                folder="Reflections",
                tags=["reflection", "daily", "auto", "vector"],
            )
            self._store_to_mem0(f"Daily reflection [{date_str}]: {reflection[:600]}")
            self._memory.store_chain(
                situation="daily_reflection",
                goal_ids=["self_awareness"],
                steps=["fetch_recent_episodes", "generate_reflection", "write_vault"],
                action="write_daily_reflection",
                outcome=f"reflection written: {title}",
                reward=0.9,
            )
            self.award_points(50, "daily reflection written to vault")
            logger.info(f"[VECTOR][consolidation_bot] reflection written: {title}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][consolidation_bot] write_note failed: {e}")
            self.deduct_points(20, "reflection write failed")
            return False

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = (task or {}).get("type", "")
        if task_type == "store_findings":
            return self._store_findings(task.get("params", {}))
        # classify_chat_intent()'s LLM classifier isn't limited to a fixed
        # vocabulary for non-RED-tier task types (governor.py: "Otherwise pick
        # a short snake_case task_type") — live traces show it invents
        # "create_note" as often as it uses the RED-tier "overwrite_note_
        # personal" string for the same kind of request. Match on substring
        # rather than an exact list so new LLM-invented synonyms (add_note,
        # note_this, etc.) still land here instead of back in the HP-lottery.
        if task_type in ("save_note", "overwrite_note_personal") or "note" in task_type:
            return self._save_note(task.get("params", {}))
        count = await self.consolidate_old_episodes()
        return {"status": "ok", "consolidated": count}

    def _save_note(self, params: dict) -> dict:
        """Save a "note this down" / personal-reminder-style request.

        KNOWN_ISSUES #21/#23: save_note and overwrite_note_personal are
        real task_types Governor.dispatch() routes to district="memory_curator"
        (classify_chat_intent() picks them with high confidence — e.g. 0.95
        live), but none of the 3 memory_curator agents ever declared either as
        a capability. That meant the request fell through to
        Governor.dispatch()'s HP-lottery fallback (governor.py's Task A.3
        note) and ran whatever agent won HP's UNRELATED default action
        instead — for this bot, that's consolidate_old_episodes(), which
        returns {"consolidated": <count>}. Confirmed live: a "note this down"
        request silently consolidated old episodes instead, and the bare
        episode count (e.g. 200) rendered as the entire response — nonsense
        to the person who asked to have something noted. This gives the task
        type an actual, correct handler instead of an accidental one.
        """
        content = str(
            params.get("content") or params.get("query") or params.get("text") or ""
        ).strip()
        if not content:
            return {"status": "error", "error": "no note content provided to save"}
        key = f"note:{datetime.datetime.now(datetime.timezone.utc).isoformat()}"
        try:
            self._memory.remember(key, content, category="personal_note", confidence=1.0)
            self.award_points(10, "note_saved")
            return {"status": "ok", "response": f"Noted: {content}"}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] save_note failed: {e}")
            return {"status": "error", "error": str(e)}

    def _store_findings(self, params: dict) -> dict:
        """Store a specific research finding into semantic memory.

        districts/research/research_hub.py's event-triggered research sends
        this — it expects a targeted write, not a full consolidation pass.
        Reuses the same EpisodicMemory.remember() write path
        consolidate_old_episodes() already uses for semantic-memory entries.
        """
        topic = str(params.get("topic", "")).strip()
        findings = str(params.get("findings", "")).strip()
        if not topic or not findings:
            return {"status": "error", "error": "store_findings needs both 'topic' and 'findings'"}
        key = f"finding:{topic}:{datetime.datetime.now().isoformat()}"
        try:
            self._memory.remember(key, findings, category="research_finding", confidence=0.6)
            self.award_points(15, "finding_stored")
            return {"status": "ok", "key": key}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] store_findings failed: {e}")
            return {"status": "error", "error": str(e)}

    async def run_forever(self) -> None:
        """Daily reflection + weekly consolidation. RULE 2 — never crashes."""
        logger.info("[VECTOR][consolidation_bot] run_forever started")
        while self.is_alive:
            try:
                await self.write_daily_reflection()
                if datetime.datetime.now().weekday() == 0:  # Monday = weekly consolidation
                    await self.consolidate_old_episodes()
            except Exception as e:
                logger.error(f"[VECTOR][consolidation_bot] tick error: {e}")
                self.deduct_points(10, "tick error")

            for _ in range(1440):  # 24h in 1-min chunks — responsive to is_alive
                if not self.is_alive:
                    break
                await asyncio.sleep(60)

        logger.warning("[VECTOR][consolidation_bot] died — HP=0")


if __name__ == "__main__":
    import tempfile, os
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = ConsolidationBot(generation=1)
        assert bot.health_points == 500
        assert bot.name == "ConsolidationBot"
        assert bot.district == "memory_curator"

        # Seed an episode to reflect on
        bot._memory.store(
            event_type="task",
            content="ConsolidationBot smoke test event",
            tags=["smoke", "test"],
            source="smoke_test",
        )

        # write_daily_reflection — writes to real vault, graceful if Ollama absent
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Reflections").mkdir()
            bot._obsidian._vault = vault

            ok = await bot.write_daily_reflection()
            assert ok, "write_daily_reflection returned False"
            assert bot.health_points > 500, "HP should have increased after success"

            note_files = list((vault / "Reflections").glob("*.md"))
            assert note_files, "No reflection note written to vault"
            content = note_files[0].read_text(encoding="utf-8")
            assert "source: vector" in content

        print(f"✅ consolidation_bot.py OK  HP={bot.health_points}")

    asyncio.run(_smoke())
