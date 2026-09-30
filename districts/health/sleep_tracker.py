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


class SleepTracker(AgentBase):
    """
    Infers sleep patterns from activity gaps in episodic_memory.
    Writes daily sleep log to Obsidian. Warns on chronic under-sleep.
    RULE 11: vector-focus (local), not Claude API.
    """

    SLEEP_GAP_HOURS = 4.0  # minimum gap to count as a sleep period
    TARGET_SLEEP_HOURS = 7.0

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SleepTracker",
            district="health",
            generation=generation,
        )
        self.capabilities = ["fatigue", "health", "sleep"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][sleep_tracker] ready gen={generation}")

    def _infer_sleep_periods(self, days: int = 1) -> list[dict] | None:
        """Detect sleep by finding gaps >= SLEEP_GAP_HOURS in episodic events."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days + 1)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT timestamp FROM episodic_memory WHERE timestamp > ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            timestamps = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][sleep_tracker] fetch failed: {e}")
            return None

        return self._compute_sleep_periods(timestamps)

    def _compute_sleep_periods(self, timestamps: list[str]) -> list[dict]:
        """Pure gap-detection over an ascending list of ISO timestamps.
        Split from the DB fetch so the gap logic is deterministically testable."""
        if len(timestamps) < 2:
            return []

        sleep_periods = []
        for i in range(1, len(timestamps)):
            try:
                t_prev = datetime.datetime.fromisoformat(timestamps[i - 1])
                t_curr = datetime.datetime.fromisoformat(timestamps[i])
                gap_hours = (t_curr - t_prev).total_seconds() / 3600
                if gap_hours >= self.SLEEP_GAP_HOURS:
                    sleep_periods.append({
                        "sleep_start": timestamps[i - 1],
                        "sleep_end": timestamps[i],
                        "duration_hours": round(gap_hours, 2),
                    })
            except Exception:
                continue

        return sleep_periods

    def _quality_label(self, hours: float) -> str:
        if hours >= 8:
            return "excellent"
        if hours >= 7:
            return "good"
        if hours >= 6:
            return "fair"
        if hours >= 4:
            return "poor"
        return "very poor"

    def _get_advice(self, avg_hours: float, hydration: str) -> str:
        prompt = (
            f"Arghyadeep's average sleep: {avg_hours:.1f} hours/night (target: {self.TARGET_SLEEP_HOURS}h).\n"
            "Give 2-3 specific, actionable sleep improvement tips tailored to a student developer.\n"
            "Be concise and direct."
        )
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(model=_FOCUS, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=60.0)
            if not text:
                raise ValueError("empty response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][sleep_tracker] LLM unavailable: {e}")
            return "Track consistent sleep/wake times. Avoid screens 30 min before bed."

    async def track(self) -> bool:
        date_str = datetime.date.today().isoformat()
        periods = self._infer_sleep_periods(days=7)

        if periods is None:
            logger.error("[VECTOR][sleep_tracker] tracking unavailable: event fetch failed")
            self.deduct_points(5, "event fetch failed")
            return False

        if not periods:
            logger.info("[VECTOR][sleep_tracker] no sleep periods detected")
            self._memory.store(
                event_type="sleep_log",
                content=f"No sleep detected on {date_str}",
                tags=["health", "sleep"],
                source="sleep_tracker",
            )
            return True

        total_hours = sum(p["duration_hours"] for p in periods)
        avg_hours = total_hours / len(periods)
        last = periods[-1]

        self._memory.remember(
            key=f"sleep:{date_str}",
            value=f"{last['duration_hours']:.1f}h ({self._quality_label(last['duration_hours'])})",
            category="health_sleep",
            confidence=0.7,
        )

        hydration = self._context.session_hydration_prompt()
        advice = self._get_advice(avg_hours, hydration) if avg_hours < self.TARGET_SLEEP_HOURS else ""

        report = (
            f"# Sleep Log — {date_str}\n\n"
            f"**Last sleep:** {last['sleep_start'][:16]} — {last['sleep_end'][:16]} "
            f"({last['duration_hours']:.1f}h, {self._quality_label(last['duration_hours'])})\n\n"
            f"**7-day average:** {avg_hours:.1f}h/night\n\n"
            f"**Target:** {self.TARGET_SLEEP_HOURS}h\n"
        )
        if advice:
            report += f"\n## Recommendations\n{advice}\n"
        report += f"\n---\n*{len(periods)} sleep periods detected · auto-generated*"

        try:
            self._obsidian.write_note(
                title=f"Sleep Log — {date_str}",
                content=report,
                folder="Health",
                tags=["health", "sleep", "vector"],
            )
            self._memory.store(
                event_type="sleep_log",
                content=f"Sleep: {last['duration_hours']:.1f}h avg={avg_hours:.1f}h",
                tags=["health", "sleep"],
                source="sleep_tracker",
            )
            self.award_points(20, f"sleep tracked {date_str}")
            logger.info(f"[VECTOR][sleep_tracker] tracked: last={last['duration_hours']:.1f}h avg={avg_hours:.1f}h")

            if avg_hours < 6:
                logger.warning(f"[VECTOR][sleep_tracker] chronic under-sleep: {avg_hours:.1f}h avg")
                self.deduct_points(10, "chronic under-sleep detected")

            return True
        except Exception as e:
            logger.error(f"[VECTOR][sleep_tracker] write failed: {e}")
            self.deduct_points(5, "write failed")
            return False

    async def run(self, task: dict) -> dict:
        ok = await self.track()
        return {"status": "ok" if ok else "error", "agent": self.name}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][sleep_tracker] run_forever — daily at 08:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 8 and 0 <= now.minute < 5:
                    await self.track()
            except Exception as e:
                logger.error(f"[VECTOR][sleep_tracker] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][sleep_tracker] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        bot = SleepTracker()
        assert bot.health_points == 500
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Health").mkdir()
            bot._obsidian._vault = vault
            ok = await bot.track()
        print(f"OK sleep_tracker.py HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
