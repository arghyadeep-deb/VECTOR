import sys
import uuid
import asyncio
import datetime

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
        self.capabilities = ["check_fatigue", "fatigue", "health", "health_alert"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._context = ContextEngine()
        self._session_start: datetime.datetime | None = None
        self._last_break: datetime.datetime | None = None
        self._fatigue_count = 0
        self._ear_unavailable_warned = False
        logger.info(f"[VECTOR][fatigue_monitor] ready gen={generation}")
        # Phase 2B: subscribe to health events
        self.subscribe_to("health_alert")
        self.subscribe_to("user_interaction")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Suggest break on health/fatigue events."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("health_alert", "user_interaction"):
            try:
                logger.info(f"[VECTOR][fatigue_monitor] event-triggered check: {et}")
                await self.run({"type": "check_fatigue", "params": {"source": "event"}})
            except Exception as e:
                logger.debug(f"[VECTOR][fatigue_monitor] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    def _get_ear_from_world_state(self) -> float | None:
        """Map ContextEngine's 0-10 camera fatigue score to an EAR threshold signal.

        ContextEngine exposes the derived fatigue score, not the raw EAR. The
        monitor only needs the threshold side here, so preserve the existing
        EAR-facing private contract used by callers/tests.
        """
        try:
            state = self._context.get_world_state()
            if state.get("presence") != "present":
                return None
            fatigue_score = float(state["fatigue_score"])
            return 0.0 if fatigue_score >= 7.0 else 1.0
        except Exception as exc:
            logger.warning("[VECTOR][fatigue_monitor] EAR sensor read failed: {}", exc)
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
            from core.inference.vectorcode_llm import chat
            hydration = self._context.session_hydration_prompt()
            text = chat(model=_FOCUS, messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": f"Fatigue alert for Arghyadeep: {message}. Give a brief, friendly 1-sentence reminder to take a break."},
            ], timeout=30.0)
            if text:
                logger.info(f"[VECTOR][fatigue_monitor] suggestion: {text[:100]}")
        except Exception as exc:
            logger.warning(
                "[VECTOR][fatigue_monitor] suggestion generation failed: {}", exc
            )

    async def check_once(self) -> dict:
        """Single fatigue check. Returns status dict."""
        status = {
            "fatigue": False,
            "reason": None,
            "session_minutes": self._session_minutes(),
            "ear_available": True,
        }

        if self._session_start is None:
            self._session_start = datetime.datetime.now()

        # Check 1: EAR-based fatigue (depends on health_monitor populating world_state)
        ear = self._get_ear_from_world_state()
        if ear is None:
            status["ear_available"] = False
            if not self._ear_unavailable_warned:
                logger.warning(
                    "[VECTOR][fatigue_monitor] EAR score unavailable in world_state — "
                    "health_monitor camera sensing isn't populating health.ear_score; "
                    "camera-based eye-fatigue detection is disabled, falling back to "
                    "session-duration-only checks"
                )
                self._ear_unavailable_warned = True
        elif ear < _EAR_FATIGUE_THRESHOLD:
            self._ear_unavailable_warned = False
            status["fatigue"] = True
            status["reason"] = f"EAR signal below threshold {_EAR_FATIGUE_THRESHOLD}"
            self._record_fatigue_event(status["reason"], "moderate")
            self._notify("Eye fatigue detected. Consider a 20-20-20 break.")

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
        # Session duration remains usable without EAR, but do not represent a
        # failed/missing camera signal as a fully healthy sensor check.
        return {
            "status": "ok",
            "assessment_status": "complete" if result["ear_available"] else "degraded",
            **result,
        }

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
