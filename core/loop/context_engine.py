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
        self._health = None
        self._screen = None
        self._obsidian = None
        logger.info("[VECTOR][context_engine] initialized")

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

    def _get_health(self):
        if self._health is None:
            try:
                from core.sensing.health_monitor import HealthMonitor
                self._health = HealthMonitor()
            except Exception:
                pass
        return self._health

    def _get_screen(self):
        if self._screen is None:
            try:
                from core.sensing.screen_observer import ScreenObserver
                self._screen = ScreenObserver()
            except Exception:
                pass
        return self._screen

    def _get_obsidian(self):
        if self._obsidian is None:
            try:
                from core.memory.obsidian_sync import ObsidianSync
                self._obsidian = ObsidianSync()
            except Exception as e:
                logger.warning(f"[VECTOR][context_engine] ObsidianSync init failed: {e}")
        return self._obsidian

    async def get_vault_context(self, query: str) -> str:
        """LightRAG hybrid query over Obsidian vault. Returns '' if not ready."""
        try:
            obs = self._get_obsidian()
            if obs is None:
                return ""
            return await obs.query(query, mode="hybrid")
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] vault context failed: {e}")
            return ""

    def get_world_state(self) -> dict:
        """Gather current world state across 9 domains."""
        now = datetime.datetime.now()  # local time for time-of-day display
        now_utc = datetime.datetime.now(datetime.timezone.utc)
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

        health_snapshot = {}
        try:
            h = self._get_health()
            if h:
                health_snapshot = h.get_health_snapshot()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] health snapshot failed: {e}")

        screen_activity = "unknown"
        try:
            s = self._get_screen()
            if s:
                result = s.observe()
                screen_activity = result.get("activity", "unknown")
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] screen observe failed: {e}")

        return {
            "timestamp": now_utc.isoformat(),
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
            "health": health_snapshot,
            "screen_activity": screen_activity,
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
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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

        if state.get("health"):
            h = state["health"]
            lines.append(
                f"Owner health: energy={h.get('energy_level','?')} fatigue={h.get('fatigue_score','?')} "
                f"cpu={h.get('cpu_percent','?')}% ram={h.get('ram_percent','?')}%"
            )
        if state.get("screen_activity") and state["screen_activity"] != "unknown":
            lines.append(f"Current activity: {state['screen_activity']}")

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
