import sys
import asyncio
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class Planner:
    """
    RULE 6 — Goal system drives the planner.
    Reads goal_system.generate_immediate_actions() — NOT world state, NOT user commands.
    Produces an ordered action queue for the autonomous loop.
    """

    def __init__(self):
        self._goals = None
        self._context = None
        logger.info("[VECTOR][planner] initialized")

    def _get_goals(self):
        if self._goals is None:
            from core.brain.goal_system import GoalSystem
            self._goals = GoalSystem()
        return self._goals

    def _get_context(self):
        if self._context is None:
            from core.loop.context_engine import ContextEngine
            self._context = ContextEngine()
        return self._context

    def plan(self, limit: int = 4) -> list[dict]:
        """
        RULE 6 — Reads goal_system.generate_immediate_actions().
        Returns ordered list of {action, goal_id, urgency, reason} dicts.
        Never raises.
        """
        try:
            actions = self._get_goals().generate_immediate_actions(limit=limit)
            if not actions:
                logger.debug("[VECTOR][planner] no immediate actions from goal system")
                return []

            logger.info(
                f"[VECTOR][planner] planned {len(actions)} actions: "
                f"{[a['action'] for a in actions]}"
            )
            return actions
        except Exception as e:
            logger.error(f"[VECTOR][planner] plan() failed: {e}")
            return []

    def plan_for_energy(self, limit: int = 4) -> list[dict]:
        """
        Same as plan() but filters by current energy level from health monitor.
        High energy → all actions. Low energy → only urgency=high actions.
        """
        try:
            actions = self.plan(limit=limit * 2)
            if not actions:
                return []

            energy = "high"
            try:
                world = self._get_context().get_world_state()
                energy = world.get("health", {}).get("energy_level", "high")
            except Exception:
                pass

            if energy == "low":
                actions = [a for a in actions if a.get("urgency") == "high"]
            elif energy == "medium":
                actions = [a for a in actions if a.get("urgency") in ("high", "medium")]

            return actions[:limit]
        except Exception as e:
            logger.error(f"[VECTOR][planner] plan_for_energy() failed: {e}")
            return []

    def get_next_action(self) -> dict | None:
        """Returns the single highest-priority action, or None."""
        actions = self.plan(limit=1)
        return actions[0] if actions else None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    planner = Planner()
    actions = planner.plan(limit=4)
    energy_actions = planner.plan_for_energy(limit=4)
    next_action = planner.get_next_action()
    ok = isinstance(actions, list) and isinstance(energy_actions, list)
    print(
        f"✅ planner OK — planned={len(actions)}, energy_filtered={len(energy_actions)}, "
        f"next={next_action['action'] if next_action else 'None'}"
        if ok else "❌ FAILED"
    )
