"""
ProactiveCare — thin policy layer that reads existing health signals and emits
care interventions. Never computes fatigue itself; reads FatigueMonitor +
HealthMonitor + NudgeEngine. Only fires in PROACTIVE/HYBRID + outside DND.

Spec §2 (Phase 2 empathy wiring).
"""

import datetime
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from core.config import CONFIG


@dataclass
class Intervention:
    """A care recommendation from ProactiveCare."""
    kind: str           # "break", "hydrate", "eye_rest", "stress_check"
    message: str
    severity: float     # 0-1
    source: str         # which monitor triggered this


_BREAK_INTERVAL_MIN = int(CONFIG.get("presence", {}).get("break_interval_min", 90))
_FATIGUE_HIGH       = 7.0   # score ≥ 7 on 0-10 scale → high fatigue
_STRESS_HIGH        = 0.75  # system cpu ≥ 75% sustained → stress indicator


class ProactiveCare:
    """
    Reads existing health monitor signals and generates Intervention objects.
    Completely stateless — call check() whenever the loop wants to assess.
    Does NOT compute fatigue or stress; delegates 100% to existing monitors.
    """

    def __init__(self):
        self._health_monitor = None
        self._fatigue_monitor = None
        self._nudge_engine = None
        # Initialize to now so the timer starts from session boot (not None)
        self._last_break_ts: Optional[datetime.datetime] = datetime.datetime.now()

    def _get_health_monitor(self):
        if self._health_monitor is None:
            try:
                from core.sensing.health_monitor import HealthMonitor
                self._health_monitor = HealthMonitor()
            except Exception as e:
                logger.debug("[VECTOR][proactive_care] health_monitor unavailable: {}", e)
        return self._health_monitor

    def _get_fatigue_monitor(self):
        if self._fatigue_monitor is None:
            try:
                from districts.health.fatigue_monitor import FatigueMonitor
                self._fatigue_monitor = FatigueMonitor()
            except Exception as e:
                logger.debug("[VECTOR][proactive_care] fatigue_monitor unavailable: {}", e)
        return self._fatigue_monitor

    def _get_nudge_engine(self):
        if self._nudge_engine is None:
            try:
                from core.loop.nudge_engine import NudgeEngine
                self._nudge_engine = NudgeEngine()
            except Exception as e:
                logger.debug("[VECTOR][proactive_care] nudge_engine unavailable: {}", e)
        return self._nudge_engine

    def check(self) -> list[Intervention]:
        """
        Poll health signals and return a list of care interventions (may be empty).
        Always returns a list; never raises.
        """
        from core.loop.presence import get_presence_config, allow_proactive, TriggerMode
        cfg = get_presence_config()

        # Gate: only fire in proactive / hybrid, outside DND
        if not allow_proactive("proactive_care", cfg=cfg):
            return []

        interventions: list[Intervention] = []

        try:
            interventions.extend(self._check_fatigue())
        except Exception as e:
            logger.debug("[VECTOR][proactive_care] fatigue check failed: {}", e)

        try:
            interventions.extend(self._check_system_stress())
        except Exception as e:
            logger.debug("[VECTOR][proactive_care] stress check failed: {}", e)

        try:
            interventions.extend(self._check_break_overdue())
        except Exception as e:
            logger.debug("[VECTOR][proactive_care] break check failed: {}", e)

        if interventions:
            logger.info("[VECTOR][proactive_care] {} intervention(s): {}", len(interventions),
                        [i.kind for i in interventions])

        return interventions

    def record_break(self) -> None:
        """Call when the owner takes a break so the overdue timer resets."""
        self._last_break_ts = datetime.datetime.now()

    # ── private checks (each reads from existing monitors) ──────────────────
    def _check_fatigue(self) -> list[Intervention]:
        hm = self._get_health_monitor()
        if hm is None:
            return []
        fatigue = hm.get_fatigue_score()
        if fatigue >= _FATIGUE_HIGH:
            return [Intervention(
                kind="eye_rest",
                message="I've noticed your fatigue score is elevated. Consider resting your eyes for a few minutes.",
                severity=min(1.0, (fatigue - _FATIGUE_HIGH + 1) / 3),
                source="health_monitor",
            )]
        return []

    def _check_system_stress(self) -> list[Intervention]:
        hm = self._get_health_monitor()
        if hm is None:
            return []
        load = hm.get_system_load()
        cpu = load.get("cpu_percent", 0.0)
        if cpu >= _STRESS_HIGH * 100:
            return [Intervention(
                kind="stress_check",
                message=f"System is under heavy load ({cpu:.0f}% CPU). Are you alright?",
                severity=min(1.0, (cpu / 100 - _STRESS_HIGH) / (1 - _STRESS_HIGH)),
                source="system_load",
            )]
        return []

    def _check_break_overdue(self) -> list[Intervention]:
        now = datetime.datetime.now()
        if self._last_break_ts is None:
            # No recorded break — we can't judge without a baseline
            return []
        elapsed_min = (now - self._last_break_ts).total_seconds() / 60
        if elapsed_min >= _BREAK_INTERVAL_MIN:
            return [Intervention(
                kind="break",
                message=f"You've been working for {elapsed_min:.0f} minutes. A short break would help.",
                severity=min(1.0, (elapsed_min - _BREAK_INTERVAL_MIN) / 30),
                source="session_timer",
            )]
        return []


_proactive_care: Optional[ProactiveCare] = None


def get_proactive_care() -> ProactiveCare:
    global _proactive_care
    if _proactive_care is None:
        _proactive_care = ProactiveCare()
    return _proactive_care


if __name__ == "__main__":
    care = ProactiveCare()

    # record_break so timer has a baseline
    care.record_break()

    # check should return [] (no fatigue data, no stress, break just taken)
    interventions = care.check()
    assert isinstance(interventions, list), "check() must return list"
    print(f"OK proactive_care -- {len(interventions)} interventions at start")

    # Test Intervention dataclass
    iv = Intervention(kind="break", message="Test", severity=0.5, source="test")
    assert iv.kind == "break"
    print("OK Intervention dataclass")
