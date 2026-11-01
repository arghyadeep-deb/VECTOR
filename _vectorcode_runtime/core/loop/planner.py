# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by core/runtime/plans.py (PlanStore/PlanRunner). Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
import sys
import asyncio
import datetime

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
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

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

    def get_active_plans(self) -> list[dict]:
        """Return summary of active multi-step plans.

        Plans are managed by PlanStore (core.runtime.plans) and wired into
        _think_tick() as additional candidates. This method exposes them for
        the HUD dashboard and diagnostic tools.
        """
        try:
            from core.runtime.plans import get_plan_store
            store = get_plan_store()
            return [
                {
                    "id": p.id,
                    "goal_id": p.goal_id,
                    "objective": p.objective,
                    "status": p.status,
                    "progress": p.progress,
                    "confidence": p.confidence,
                    "total_steps": len(p.steps),
                    "completed_steps": sum(1 for s in p.steps if s.status == "completed"),
                    "ready_steps": [s.id for s in p.next_ready_steps()],
                    "replan_count": p.replan_count,
                }
                for p in store.active_plans()
            ]
        except Exception as e:
            logger.warning(f"[VECTOR][planner] get_active_plans failed: {e}")
            return []


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
        if ok else "âŒ FAILED"
    )
