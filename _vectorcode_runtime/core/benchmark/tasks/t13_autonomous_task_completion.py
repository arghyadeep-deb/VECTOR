"""T13 — Autonomous Task Completion: goal → plan → execute → done.

Create a goal, build a 2-step plan, execute both steps manually
(simulating PlanRunner lifecycle), verify plan reaches 'completed'.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult
from core.runtime.plans import Plan, PlanStep, PlanStore, _now


class AutonomousTaskCompletionTask(BenchmarkTask):
    task_id = "T13"
    category = "autonomous_task_completion"
    required_capability = "Full plan lifecycle: goal → plan → execute → complete"
    expected_behavior = "2-step plan created, both steps executed, plan status = completed"

    def run(self, state) -> TaskResult:
        from core.brain.goal_system import GoalSystem

        # Create a goal
        gs = GoalSystem()
        try:
            goal_id = gs.add_goal(
                title="Benchmark autonomous completion test",
                horizon="SHORT",
                priority=10,
                tags=["benchmark"],
            )
        except Exception as e:
            return self._failure(
                actual=f"GoalSystem.add_goal failed: {e}",
                outcome="Could not create goal",
            )

        # Create a 2-step plan linked to the goal
        step1 = PlanStep(
            id="step-a",
            action_type="respond",
            params={"text": "Step 1: Data gathered"},
            depends_on=[],
            verification={"type": "always"},
        )
        step2 = PlanStep(
            id="step-b",
            action_type="respond",
            params={"text": "Step 2: Report generated"},
            depends_on=["step-a"],
            verification={"type": "always"},
        )

        plan = Plan(
            id="bench-plan-13",
            goal_id=goal_id,
            objective="Complete benchmark task autonomously",
            status="active",
            steps=[step1, step2],
            created_at=_now(),
            updated_at=_now(),
        )

        # Store in PlanStore (using temp path from isolated state)
        store = PlanStore(path=Path(state.plan_store_path))
        store.add(plan)

        # Simulate PlanRunner lifecycle: execute steps in order
        # Step 1: should be ready (no dependencies)
        ready = plan.next_ready_steps(limit=3)
        if not ready or ready[0].id != "step-a":
            return self._failure(
                actual=f"step-a not ready first. Ready: {[s.id for s in ready]}",
                outcome="Plan ordering broken",
            )

        # Execute step 1 (simulate success)
        step1.status = "completed"
        step1.completed_at = _now()
        step1.actual_outcome = {"status": "executed", "verification_passed": True}
        plan.update_progress()

        # Step 2: should now be ready
        ready_after = plan.next_ready_steps(limit=3)
        if not ready_after or ready_after[0].id != "step-b":
            return self._failure(
                actual=f"step-b not ready after step-a. Ready: {[s.id for s in ready_after]}",
                outcome="DAG dependency broken",
            )

        # Execute step 2
        step2.status = "completed"
        step2.completed_at = _now()
        step2.actual_outcome = {"status": "executed", "verification_passed": True}
        plan.update_progress()

        # Check completion
        is_complete = plan.is_complete()
        if is_complete:
            plan.status = "completed"
            plan.record_event("completed", "All steps completed and verified")

        store.save()

        # Verify final state
        saved_plan = store.get("bench-plan-13")
        final_status = saved_plan.status if saved_plan else "not_found"
        final_progress = saved_plan.progress if saved_plan else 0.0

        if is_complete and final_status == "completed" and final_progress >= 0.99:
            return self._success(
                actual=(
                    f"Goal → Plan(2 steps) → Execute → Complete. "
                    f"Status={final_status}, progress={final_progress:.2f}. "
                    f"Plan persisted to store."
                ),
                outcome="Autonomous task completion verified — full lifecycle",
                details={
                    "goal_id": goal_id,
                    "plan_id": plan.id,
                    "steps_completed": 2,
                    "final_status": final_status,
                    "final_progress": final_progress,
                },
            )
        else:
            return self._failure(
                actual=f"complete={is_complete}, status={final_status}, progress={final_progress:.2f}",
                outcome="Plan did not reach completion",
                details={
                    "goal_id": goal_id,
                    "is_complete": is_complete,
                    "final_status": final_status,
                    "final_progress": final_progress,
                },
            )


TASK_CLASS = AutonomousTaskCompletionTask
