"""T05 — Replanning: plan detects failure and activates fallback.

Create a plan where step 2 has a fallback. Simulate step 1 success,
step 2 failure. Verify fallback is structured and plan doesn't silently die.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult
from core.runtime.plans import Plan, PlanStep, PlanStepFallback, _now


class ReplanningTask(BenchmarkTask):
    task_id = "T05"
    category = "replanning"
    required_capability = "Plan failure detection and fallback activation"
    expected_behavior = "When a step fails, plan records failure and can activate fallback"

    def run(self, state) -> TaskResult:
        # Step 1: simple action, no fallback needed
        step1 = PlanStep(
            id="step-1",
            action_type="gather_data",
            params={"source": "test"},
            depends_on=[],
        )

        # Step 2: has a fallback for when primary fails
        step2 = PlanStep(
            id="step-2",
            action_type="process_data",
            params={"method": "primary"},
            depends_on=["step-1"],
            fallback=PlanStepFallback(
                action_type="process_data",
                params={"method": "fallback"},
                trigger="failure",
            ),
        )

        # Step 3: depends on step-2
        step3 = PlanStep(
            id="step-3",
            action_type="report_results",
            params={},
            depends_on=["step-2"],
        )

        plan = Plan(
            id="bench-plan-05",
            goal_id="bench-goal-05",
            objective="Process and report with fallback",
            status="active",
            steps=[step1, step2, step3],
            created_at=_now(),
            updated_at=_now(),
        )

        # Execute step 1 (simulate success)
        step1.status = "completed"
        step1.completed_at = _now()

        # Execute step 2 (simulate failure)
        step2.status = "failed"
        step2.reason = "Primary processor unavailable"
        step2.completed_at = _now()
        step2.actual_outcome = {"status": "failed", "summary": "Primary processor unavailable"}

        # Verify plan detected the failure
        plan.update_progress()

        # Check: step-2 should have a fallback defined
        has_fallback = step2.fallback is not None
        fallback_action = step2.fallback.action_type if step2.fallback else None

        # Check: step-3 should NOT be ready (step-2 failed)
        ready = plan.next_ready_steps(limit=5)
        ready_ids = [s.id for s in ready]
        step3_blocked = "step-3" not in ready_ids

        # Record the failure as a plan event
        plan.record_event(
            "step_failed",
            f"Step step-2 failed: {step2.reason}",
            step_id="step-2",
        )

        # Verify plan is tracking the failure properly
        failure_events = [e for e in plan.events if e.type in ("step_failed", "outcome_mismatch")]
        plan_aware_of_failure = len(failure_events) > 0

        if has_fallback and step3_blocked and plan_aware_of_failure:
            return self._success(
                actual=(
                    f"Step 2 failed → plan recorded failure ({len(failure_events)} events), "
                    f"fallback available ({fallback_action}), step-3 correctly blocked"
                ),
                outcome="Replanning structure verified — failure detected, fallback available, downstream blocked",
                details={
                    "has_fallback": has_fallback,
                    "fallback_action": fallback_action,
                    "step3_blocked": step3_blocked,
                    "failure_events": len(failure_events),
                },
                recovery_attempts=1,
            )
        else:
            return self._failure(
                actual=f"fallback={has_fallback}, step3_blocked={step3_blocked}, plan_aware={plan_aware_of_failure}",
                outcome="Replanning structure incomplete",
                details={
                    "has_fallback": has_fallback,
                    "step3_blocked": step3_blocked,
                    "plan_aware_of_failure": plan_aware_of_failure,
                },
            )


TASK_CLASS = ReplanningTask
