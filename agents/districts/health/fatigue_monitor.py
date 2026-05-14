import sys
import uuid
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger

_FOCUS = CONFIG["models"]["focus"]

# EAR threshold below which eye closure is considered a blink/fatigue signal
_EAR_FATIGUE_THRESHOLD = 0.25
_SESSION_FATIGUE_MINUTES = 90  # warn after 90 min continuous session


class FatigueMonitor(AgentBase):
    """
    Monitors fatigue via:
    1. Camera EAR (Eye Aspect Ratio) from health_monitor sensing data
    2. Continuous screen-on session duration from episodic_memory
    Notifies when fatigue threshold is crossed. RULE 11: local only.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="FatigueMonitor",
            district="health",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._context = ContextEngine()
        self._session_start: datetime.datetime | None = None
        self._last_break: datetime.datetime | None = None
        self._fatigue_count = 0
        logger.info(f"[VECTOR][fatigue_monitor] ready gen={generation}")

    def _get_ear_from_world_state(self) -> float | None:
        """Pull current EAR from ContextEngine world state (populated by health_monitor)."""
        try:
            ctx = self._context.get_full_context()
            return ctx.get("world_state", {}).get("health", {}).get("ear_score")
        except Exception:
            return None

    def _session_minutes(self) -> float:
        """Minutes since last break or session start."""
        if self._session_start is None:
            return 0.0
        ref = self._last_break or self._session_start
        return (datetime.datetime.now() - ref).total_seconds() / 60

    def _record_fatigue_event(self, reason: str, severity: str) -> None:
        self._memory.store(
            event_type="fatigue_detected",
            content=f"Fatigue [{severity}]: {reason}",
            tags=["health", "fatigue", severity],
            source="fatigue_monitor",
        )
        self._fatigue_count += 1

    def _notify(self, message: str) -> None:
        logger.warning(f"[VECTOR][fatigue_monitor] ALERT: {message}")
        try:
            import ollama
            hydration = self._context.session_hydration_prompt()
            r = ollama.chat(
                model=_FOCUS,
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": f"Fatigue alert for Arghyadeep: {message}. Give a brief, friendly 1-sentence reminder to take a break."},
                ],
            )
            logger.info(f"[VECTOR][fatigue_monitor] suggestion: {r['message']['content'][:100]}")
        except Exception:
            pass

    async def check_once(self) -> dict:
        """Single fatigue check. Returns status dict."""
        status = {"fatigue": False, "reason": None, "session_minutes": self._session_minutes()}

        if self._session_start is None:
            self._session_start = datetime.datetime.now()

        # Check 1: EAR-based fatigue
        ear = self._get_ear_from_world_state()
        if ear is not None and ear < _EAR_FATIGUE_THRESHOLD:
            status["fatigue"] = True
            status["reason"] = f"EAR={ear:.3f} below threshold {_EAR_FATIGUE_THRESHOLD}"
            self._record_fatigue_event(status["reason"], "moderate")
            self._notify(f"Eye fatigue detected (EAR={ear:.3f}). Consider a 20-20-20 break.")

        # Check 2: Session duration
        mins = self._session_minutes()
        if mins >= _SESSION_FATIGUE_MINUTES:
            status["fatigue"] = True
            status["reason"] = status.get("reason") or f"Session={mins:.0f}min"
            self._record_fatigue_event(f"Continuous session: {mins:.0f} min", "mild")
            self._notify(f"You've been working for {mins:.0f} minutes. Take a 5-minute break.")
            self._last_break = datetime.datetime.now()

        if not status["fatigue"]:
            logger.debug(f"[VECTOR][fatigue_monitor] OK — session={mins:.0f}min EAR={ear}")

        return status

    async def run(self, task: dict) -> dict:
        result = await self.check_once()
        return {"status": "ok", **result}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][fatigue_monitor] run_forever — checking every 5 min")
        while self.is_alive:
            try:
                await self.check_once()
            except Exception as e:
                logger.error(f"[VECTOR][fatigue_monitor] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)
        logger.warning("[VECTOR][fatigue_monitor] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = FatigueMonitor()
        assert bot.health_points == 500
        result = await bot.check_once()
        assert "fatigue" in result
        print(f"OK fatigue_monitor.py HP={bot.health_points} fatigue={result['fatigue']}")

    asyncio.run(_smoke())
