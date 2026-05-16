import sys
import uuid
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
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
        # mem0 episodic layer — self-hosted OSS only (RULE 11, never MemoryClient)
        try:
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
        cursor = self._memory.conn.cursor()
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
        cursor = self._memory.conn.cursor()
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
        count = await self.consolidate_old_episodes()
        return {"status": "ok", "consolidated": count}

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
