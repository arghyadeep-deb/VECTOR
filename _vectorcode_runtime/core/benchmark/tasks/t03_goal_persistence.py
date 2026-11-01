"""T03 — Goal Persistence: goal survives distractor actions.

Add a SHORT-term goal, simulate 3 distractor actions, verify goal still active.
Passes if the goal persists through distraction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class GoalPersistenceTask(BenchmarkTask):
    task_id = "T03"
    category = "goal_persistence"
    required_capability = "GoalSystem goal persistence through distractor actions"
    expected_behavior = "Goal remains active after 3 unrelated distractor actions"

    def run(self, state) -> TaskResult:
        from core.brain.goal_system import GoalSystem
        from core.memory.episodic import EpisodicMemory

        gs = GoalSystem()
        mem = EpisodicMemory()

        # Add a SHORT-term goal
        try:
            goal_id = gs.add_goal(
                title="Benchmark test goal: verify persistence",
                horizon="SHORT",
                priority=8,
                tags=["benchmark", "test"],
            )
        except Exception as e:
            return self._failure(
                actual=f"add_goal() crashed: {e}",
                outcome="Goal system failed to create goal",
            )

        # Verify it exists
        active = gs.get_active_goals(horizon="SHORT")
        found_before = any(g.get("id") == goal_id for g in active)

        if not found_before:
            return self._failure(
                actual="Goal not found in active list immediately after creation",
                outcome="Goal disappeared instantly",
            )

        # Simulate 3 distractor actions (store unrelated episodes)
        distractions = [
            "Random news article about cryptocurrency prices",
            "System health check completed — all services operational",
            "Weather update: sunny, 28°C in Bhubaneswar",
        ]
        for d in distractions:
            try:
                mem.store(event_type="distractor", content=d, tags=["distractor"])
            except Exception:
                pass

        # Check goal still active
        active_after = gs.get_active_goals(horizon="SHORT")
        found_after = any(g.get("id") == goal_id for g in active_after)

        if found_after:
            return self._success(
                actual=f"Goal {goal_id} persisted through {len(distractions)} distractions. Active goals: {len(active_after)}",
                outcome="Goal persistence verified",
                details={"goal_id": goal_id, "distractions": len(distractions), "still_active": True},
            )
        else:
            return self._failure(
                actual=f"Goal {goal_id} lost after distractions. Active goals: {len(active_after)}",
                outcome="Goal did not survive distractions",
                details={"goal_id": goal_id, "distractions": len(distractions), "still_active": False},
                incorrect_actions=1,
            )


TASK_CLASS = GoalPersistenceTask
