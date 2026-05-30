import sys
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class ContextEngine:
    """
    Builds VECTOR's world state. session_hydration_prompt() MUST be called before every LLM call.
    RULE 1 — Skip this = VECTOR has amnesia every session. Never skip.
    """

    def __init__(self):
        self._memory = None
        self._goals = None
        # Sense cache: populated by autonomous_loop._sense_tick() or update_sense_cache().
        # Keys written by FaceDetector: face.detected, face.identity, face.fatigue
        # Keys written by ScreenObserver: screen_summary
        self._sense_cache: dict = {}
        logger.info("[VECTOR][context_engine] initialized")

    def update_sense_cache(self, data: dict) -> None:
        """Update the sense cache with latest sensing results.

        Called by autonomous_loop._sense_tick() after every FaceDetector /
        ScreenObserver pass. May also be called directly in tests.
        Expected keys (all optional):
          face.detected (bool), face.identity (str), face.fatigue (float)
          screen_summary (str)
        """
        self._sense_cache.update(data)

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _get_goals(self):
        if self._goals is None:
            from core.brain.goal_system import GoalSystem
            self._goals = GoalSystem()
        return self._goals

    def get_world_state(self) -> dict:
        """Gather current world state across 9 domains."""
        now = datetime.datetime.now()
        mem = self._get_memory()

        recent_episodes = []
        try:
            recent_episodes = mem.recall("", limit=5)
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] episode recall failed: {e}")

        goal_summary = ""
        try:
            goal_summary = self._get_goals().get_goal_summary()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] goal summary failed: {e}")

        mem_stats = {}
        try:
            mem_stats = mem.get_stats()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] mem stats failed: {e}")

        # --- Presence / face detection from sense cache ---
        face_data: dict = self._sense_cache.get("face", {})
        if face_data.get("detected"):
            presence = "present"
        elif "detected" in face_data:
            # detected key exists but is False — camera ran, no face found
            presence = "absent"
        else:
            presence = self._sense_cache.get("presence", "unknown")

        owner_identity: str = face_data.get("identity", "")
        fatigue_score: float = float(face_data.get("fatigue", 0.0))

        return {
            "timestamp": now.isoformat(),
            "time_of_day": self._time_of_day(now),
            "day_of_week": now.strftime("%A"),
            "owner": CONFIG["owner_name"],
            "env": CONFIG["env"],
            "version": CONFIG["version"],
            "active_model": CONFIG["models"].get(
                CONFIG["model_router"]["conversation"], "vector-focus"
            ),
            "recent_episodes": [ep.get("content", "")[:80] for ep in recent_episodes[:3]],
            "goal_summary": goal_summary,
            "memory_stats": mem_stats,
            "loop_status": "running",
            # Presence fields — sourced from FaceDetector via _sense_cache
            "presence": presence,
            "owner_identity": owner_identity,
            "fatigue_score": fatigue_score,
            "screen_summary": self._sense_cache.get("screen_summary", ""),
        }

    def session_hydration_prompt(self, extra_context: dict | None = None) -> str:
        """
        RULE 1 — Call this before EVERY LLM call.
        Returns a context block to prepend to the LLM message.
        """
        try:
            state = self.get_world_state()
        except Exception as e:
            logger.error(f"[VECTOR][context_engine] world state failed: {e}")
            state = {
                "timestamp": datetime.datetime.now().isoformat(),
                "owner": CONFIG["owner_name"],
                "env": CONFIG["env"],
                "version": CONFIG["version"],
                "time_of_day": "unknown",
                "day_of_week": "unknown",
                "goal_summary": "",
                "recent_episodes": [],
            }

        lines = [
            f"[SESSION CONTEXT — {state['timestamp']}]",
            f"Owner: {state['owner']} | Env: {state['env']} | VECTOR v{state['version']}",
            f"Time: {state['time_of_day']} ({state['day_of_week']})",
        ]

        if state.get("presence") and state["presence"] not in ("unknown", ""):
            identity = state.get("owner_identity", "")
            fatigue = state.get("fatigue_score", 0.0)
            presence_line = f"Presence: {state['presence']}"
            if identity:
                presence_line += f" ({identity})"
            if fatigue > 0.0:
                presence_line += f" fatigue={fatigue:.2f}"
            lines.append(presence_line)

        if state.get("screen_summary"):
            lines.append(f"Screen: {state['screen_summary'][:120]}")

        if state.get("goal_summary"):
            lines.append(f"Active goals: {state['goal_summary']}")

        if state.get("recent_episodes"):
            episodes_str = " | ".join(
                e for e in state["recent_episodes"] if e
            )[:200]
            if episodes_str:
                lines.append(f"Recent context: {episodes_str}")

        if extra_context:
            for k, v in extra_context.items():
                lines.append(f"{k}: {v}")

        lines.append("[END SESSION CONTEXT]")
        return "\n".join(lines)

    def _time_of_day(self, now: datetime.datetime) -> str:
        h = now.hour
        if 5 <= h < 9:
            return "early morning"
        elif 9 <= h < 12:
            return "morning"
        elif 12 <= h < 14:
            return "midday"
        elif 14 <= h < 18:
            return "afternoon"
        elif 18 <= h < 22:
            return "evening"
        elif 22 <= h or h < 1:
            return "night"
        else:
            return "late night"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    engine = ContextEngine()
    state = engine.get_world_state()
    prompt = engine.session_hydration_prompt({"task": "smoke test"})
    ok = (
        "SESSION CONTEXT" in prompt
        and "Arghyadeep" in prompt
        and "[END SESSION CONTEXT]" in prompt
        and len(state) >= 8
    )
    print(
        f"✅ context_engine OK — {len(state)} domains, prompt={len(prompt)} chars"
        if ok else "❌ FAILED"
    )
