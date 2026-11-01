import sys
import os
import uuid
import asyncio
import datetime
from collections import Counter
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger


class PatternFinder(AgentBase):
    """
    Scans recent episodic memory for behavioral and operational patterns.
    Stores discovered patterns in semantic_memory and writes reports to Obsidian.
    Runs every 12h.
    """

    ANALYSIS_WINDOW_HOURS = 48
    MIN_EPISODES = 5

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="PatternFinder",
            district="memory_curator",
            generation=generation,
        )
        self.capabilities = ["consolidate", "memory", "memory_curator", "pattern", "recall"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][pattern_finder] ready gen={generation} hp={self.health_points}")

    # ── Episode helpers ────────────────────────────────────────────────────────

    def _fetch_window(self, hours: int) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        ).isoformat()
        # KNOWN_ISSUES #21: was `self._memory.conn.cursor()` — a direct reference
        # to the EpisodicMemory instance's connection captured once at __init__.
        # get_db_connection()'s self-healing (reopen-if-closed) logic only runs
        # inside get_db_connection() itself; a cached self.conn snapshot never
        # sees it, so once the shared singleton connection was closed anywhere
        # (e.g. EpisodicMemory.close() from another owner of the same
        # singleton), this raised "Cannot operate on a closed database" forever
        # until process restart. get_temp_cursor() always fetches a fresh
        # connection via get_db_connection(), so it self-heals like every other
        # EpisodicMemory read/write path already does.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM episodic_memory WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200",
                (cutoff,),
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _event_distribution(self, episodes: list[dict]) -> str:
        counts = Counter(ep["event_type"] for ep in episodes)
        return ", ".join(f"{k}={v}" for k, v in counts.most_common(8))

    def _hour_distribution(self, episodes: list[dict]) -> str:
        """Shows which hours of the day have the most activity."""
        hours = []
        for ep in episodes:
            try:
                ts = ep["timestamp"]
                h = int(ts[11:13])
                hours.append(h)
            except (IndexError, ValueError, TypeError) as e:
                logger.debug("[VECTOR][pattern_finder] bad episode timestamp {!r}: {}", ep.get("timestamp"), e)
        if not hours:
            return "unknown"
        counts = Counter(hours)
        top = counts.most_common(3)
        return ", ".join(f"{h:02d}:00({c}x)" for h, c in top)

    # ── Core task ─────────────────────────────────────────────────────────────

    async def find_patterns(self, window_hours: int | None = None) -> list[str]:
        """Analyze recent episodes for behavioral + operational patterns.
        Returns list of pattern name strings. Stores in semantic_memory."""
        hours = window_hours or self.ANALYSIS_WINDOW_HOURS
        episodes = self._fetch_window(hours)

        if len(episodes) < self.MIN_EPISODES:
            logger.info(
                f"[VECTOR][pattern_finder] only {len(episodes)} episodes — "
                f"need {self.MIN_EPISODES} to analyze"
            )
            return []

        dist = self._event_distribution(episodes)
        hour_dist = self._hour_distribution(episodes)
        episodes_text = "\n".join(
            f"[{ep['timestamp'][11:16]}] {ep['event_type']}: {ep['content'][:80]}"
            for ep in episodes[:60]
        )
        hydration = self._context.session_hydration_prompt()  # RULE 1

        try:
            if os.getenv("VECTOR_MEMORY_CURATOR_LLM") != "1":
                raise RuntimeError("memory curator LLM disabled; set VECTOR_MEMORY_CURATOR_LLM=1 to enable")
            from core.inference.vectorcode_llm import chat
            raw = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration},
                    {
                        "role": "user",
                        "content": (
                            f"Analyze these {len(episodes)} VECTOR events from the last {hours}h.\n"
                            f"Event types: {dist}\n"
                            f"Peak activity hours: {hour_dist}\n\n"
                            "Find 3-5 behavioral or operational patterns. Format each as:\n"
                            "PATTERN: <short name>\n"
                            "OBSERVATION: <what you noticed>\n"
                            "IMPACT: <why it matters>\n\n"
                            + episodes_text
                        ),
                    },
                ],
                timeout=2.0,
            )
            if not raw:
                raise RuntimeError("empty model response")
        except Exception as e:
            logger.warning(f"[VECTOR][pattern_finder] LLM unavailable: {e}")
            raw = (
                f"Activity summary over {hours}h:\n"
                f"- {len(episodes)} total events\n"
                f"- Distribution: {dist}\n"
                f"- Peak hours: {hour_dist}"
            )

        patterns = self._parse_patterns(raw)

        # Store patterns in semantic_memory
        ts = datetime.date.today().isoformat()
        for i, p in enumerate(patterns):
            if self._memory.remember(
                key=f"pattern:{ts}:{i}",
                value=p,
                category="pattern",
                confidence=0.7,
            ) is False:
                logger.warning("[VECTOR][pattern_finder] pattern {} not persisted (memory write failed)", i)

        # Write pattern report to Obsidian
        try:
            title = f"Pattern Report — {ts}"
            self._obsidian.write_note(
                title=title,
                content=f"## Pattern Analysis — {hours}h window\n\n{raw}",
                folder="Reflections",
                tags=["patterns", "analysis", "auto", "vector"],
            )
            logger.info(f"[VECTOR][pattern_finder] report written: {title}")
        except Exception as e:
            logger.warning(f"[VECTOR][pattern_finder] vault write failed: {e}")

        # RL wiring (RULE 7)
        reward = 0.75 if patterns else 0.3
        self._memory.store_chain(
            situation="pattern_analysis",
            goal_ids=["self_improvement"],
            steps=["fetch_episodes", "analyze_llm", "store_patterns", "write_vault"],
            action="find_patterns",
            outcome=f"{len(patterns)} patterns found",
            reward=reward,
        )

        if patterns:
            self.award_points(40, f"found {len(patterns)} behavioral patterns")
        else:
            self.deduct_points(10, "no patterns found in window")

        logger.info(f"[VECTOR][pattern_finder] {len(patterns)} patterns in {hours}h window")
        return patterns

    def _parse_patterns(self, text: str) -> list[str]:
        """Extract PATTERN: names from structured LLM output."""
        patterns = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.upper().startswith("PATTERN:"):
                name = stripped[8:].strip()
                if name:
                    patterns.append(name)
        if not patterns:
            # Fallback: first 3 non-empty lines as pattern names
            patterns = [l.strip() for l in text.split("\n") if l.strip()][:3]
        return patterns

    def get_stored_patterns(self, days: int = 7) -> list[dict]:
        """Retrieve recent patterns from semantic_memory."""
        cutoff_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        # KNOWN_ISSUES #21 — see _fetch_window() above for why this must go
        # through get_temp_cursor() rather than a cached self._memory.conn.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT key, value, confidence, updated_at FROM semantic_memory "
                "WHERE category='pattern' AND updated_at >= ? ORDER BY updated_at DESC LIMIT 50",
                (cutoff_date,),
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        params = (task or {}).get("params") or {}
        try:
            window = int(params.get("window_hours") or 0) or None
        except (TypeError, ValueError):
            window = None
        patterns = await self.find_patterns(window_hours=window)
        return {"status": "ok", "patterns": patterns, "count": len(patterns)}

    async def run_forever(self) -> None:
        """Pattern analysis every 12h. RULE 2 — never crashes."""
        logger.info("[VECTOR][pattern_finder] run_forever started")
        while self.is_alive:
            try:
                await self.find_patterns()
            except Exception as e:
                logger.error(f"[VECTOR][pattern_finder] tick error: {e}")
                self.deduct_points(10, "tick error")

            for _ in range(720):  # 12h in 1-min chunks
                if not self.is_alive:
                    break
                await asyncio.sleep(60)

        logger.warning("[VECTOR][pattern_finder] died — HP=0")


if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = PatternFinder(generation=1)
        assert bot.health_points == 500
        assert bot.name == "PatternFinder"
        assert bot.district == "memory_curator"

        # Seed episodes
        for i in range(10):
            bot._memory.store(
                event_type=["task", "observe", "reflect", "vault_write"][i % 4],
                content=f"Smoke test event {i} — checking pattern detection",
                tags=["smoke"],
                source="smoke_test",
            )

        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Reflections").mkdir()
            bot._obsidian._vault = vault

            patterns = await bot.find_patterns(window_hours=8760)  # 1 year window — gets all seeded
            assert isinstance(patterns, list), "find_patterns must return list"
            assert bot.health_points != 500, "HP should have changed after analysis"

            # Vault note written
            note_files = list((vault / "Reflections").glob("*.md"))
            assert note_files, "No pattern report written to vault"

        # get_stored_patterns
        stored = bot.get_stored_patterns(days=1)
        assert isinstance(stored, list)

        print(f"✅ pattern_finder.py OK  patterns={len(patterns)} HP={bot.health_points}")

    asyncio.run(_smoke())
