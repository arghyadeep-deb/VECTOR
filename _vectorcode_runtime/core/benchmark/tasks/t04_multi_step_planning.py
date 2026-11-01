"""T04 — Multi-step Planning: create plan, verify DAG ordering.

Create a 3-step plan with dependencies, verify next_ready_steps()
returns them in correct topological order.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult
from core.runtime.plans import Plan, PlanStep, PlanStore, _now


class MultiStepPlanningTask(BenchmarkTask):
    task_id = "T04"
    category = "multi_step_planning"
    required_capability = "Plan creation with DAG dependencies and topological ordering"
    expected_behavior = "3-step plan created; next_ready_steps() returns steps in dependency order"

    def run(self, state) -> TaskResult:
        # Create a 3-step plan: step1 → step2 → step3
        step1 = PlanStep(
            id="step-1",
            action_type="research_topic",
            params={"topic": "benchmark planning"},
            depends_on=[],
            expected_outcome="Research complete",
            priority=3,
        )
        step2 = PlanStep(
            id="step-2",
            action_type="draft_outline",
            params={"format": "markdown"},
            depends_on=["step-1"],
            expected_outcome="Outline drafted",
            priority=2,
        )
        step3 = PlanStep(
            id="step-3",
            action_type="write_report",
            params={"length": "500 words"},
            depends_on=["step-2"],
            expected_outcome="Report written",
            priority=1,
        )

        plan = Plan(
            id="bench-plan-04",
            goal_id="bench-goal-04",
            objective="Create a benchmark report",
            status="active",
            steps=[step1, step2, step3],
            created_at=_now(),
            updated_at=_now(),
        )

        # Before any execution: only step-1 should be ready
        ready = plan.next_ready_steps(limit=5)
        ready_ids = [s.id for s in ready]

        if "step-1" not in ready_ids:
            return self._failure(
                actual=f"step-1 not ready. Ready: {ready_ids}",
                outcome="DAG ordering broken — first step not ready",
            )

        # Simulate step-1 completion
        step1.status = "completed"
        step1.completed_at = _now()

        # Now step-2 should be ready
        ready_after_1 = plan.next_ready_steps(limit=5)
        ready_after_1_ids = [s.id for s in ready_after_1]

        if "step-2" not in ready_after_1_ids:
            return self._failure(
                actual=f"step-2 not ready after step-1 completion. Ready: {ready_after_1_ids}",
                outcome="DAG dependency not respected",
            )

        # step-3 should NOT be ready yet
        if "step-3" in ready_after_1_ids:
            return self._failure(
                actual=f"step-3 prematurely ready after only step-1 completion",
                outcome="Dependency chain violated",
            )

        # Complete step-2, verify step-3 now ready
        step2.status = "completed"
        step2.completed_at = _now()

        ready_after_2 = plan.next_ready_steps(limit=5)
        ready_after_2_ids = [s.id for s in ready_after_2]

        if "step-3" not in ready_after_2_ids:
            return self._failure(
                actual=f"step-3 not ready after step-2 completion. Ready: {ready_after_2_ids}",
                outcome="Final step not reachable",
            )

        return self._success(
            actual=f"3-step plan with DAG deps: step-1 ready → step-2 ready → step-3 ready. Correct topological order.",
            outcome="Multi-step planning with DAG verified",
            details={"steps": 3, "dag_order": ["step-1", "step-2", "step-3"]},
        )


TASK_CLASS = MultiStepPlanningTask
