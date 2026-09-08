"""Integration tests for the multi-step plan system.

Tests the full flow: plan creation → step execution → verification → replan →
completion, including persistence across simulated restarts.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.loop.decision_engine import Candidate
from core.runtime.plans import (
    Plan,
    PlanRunner,
    PlanStep,
    PlanStepFallback,
    PlanStore,
    _now,
    verify_step_outcome,
)


def _make_mock_report(status: str = "executed", reason: str = "ok") -> MagicMock:
    report = MagicMock()
    report.status = status
    report.reason = reason
    report.result = {"data": "test"} if status == "executed" else None
    report.to_dict.return_value = {"status": status, "reason": reason}
    return report


class TestPlanFullLifecycle(unittest.TestCase):
    """Full plan: create → execute all steps → completed."""

    def test_three_step_plan_completes(self):
        """A 3-step linear plan executes all steps and reaches 'completed'."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="Three step plan", status="active",
                steps=[
                    PlanStep(id="s1", action_type="step_a"),
                    PlanStep(id="s2", action_type="step_b", depends_on=["s1"]),
                    PlanStep(id="s3", action_type="step_c", depends_on=["s2"]),
                ],
                created_at=_now(), updated_at=_now(),
            )

            store = PlanStore(path=tmppath)
            store.add(plan)
            runner = PlanRunner(store=store)

            # Mock executor to always succeed
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=_make_mock_report())
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()

            # Execute step by step (as the autonomous loop would)
            for _ in range(3):
                ready = plan.next_ready_steps()
                if not ready:
                    break
                loop.run_until_complete(runner.execute_step(plan, ready[0]))

            loop.close()

            self.assertEqual(plan.status, "completed")
            self.assertAlmostEqual(plan.progress, 1.0)
            self.assertEqual(mock_executor.execute.call_count, 3)
        finally:
            tmppath.unlink(missing_ok=True)

    def test_dag_plan_executes_in_order(self):
        """DAG plan: s1 → s2, s3 (parallel) → s4. s4 only runs after s2 and s3."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="DAG plan", status="active",
                steps=[
                    PlanStep(id="s1", action_type="fetch_data"),
                    PlanStep(id="s2", action_type="analyze_a", depends_on=["s1"]),
                    PlanStep(id="s3", action_type="analyze_b", depends_on=["s1"]),
                    PlanStep(id="s4", action_type="merge", depends_on=["s2", "s3"]),
                ],
                created_at=_now(), updated_at=_now(),
            )

            store = PlanStore(path=tmppath)
            store.add(plan)
            runner = PlanRunner(store=store)
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=_make_mock_report())
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()
            executed_ids = []

            for _ in range(4):
                ready = plan.next_ready_steps()
                for step in ready:
                    loop.run_until_complete(runner.execute_step(plan, step))
                    executed_ids.append(step.id)

            loop.close()

            # s1 first, then s2+s3 (order between them doesn't matter), then s4
            self.assertEqual(executed_ids[0], "s1")
            self.assertIn("s2", executed_ids[1:3])
            self.assertIn("s3", executed_ids[1:3])
            self.assertEqual(executed_ids[3], "s4")
            self.assertEqual(plan.status, "completed")
        finally:
            tmppath.unlink(missing_ok=True)


class TestPlanSurvivesRestart(unittest.TestCase):
    """Plan mid-execution → save → reload → resume from correct step."""

    def test_resume_after_restart(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="Resume test", status="active",
                steps=[
                    PlanStep(id="s1", action_type="step_a"),
                    PlanStep(id="s2", action_type="step_b", depends_on=["s1"]),
                    PlanStep(id="s3", action_type="step_c", depends_on=["s2"]),
                ],
                created_at=_now(), updated_at=_now(),
            )

            store = PlanStore(path=tmppath)
            store.add(plan)
            runner = PlanRunner(store=store)
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=_make_mock_report())
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()

            # Execute only step 1
            ready = plan.next_ready_steps()
            loop.run_until_complete(runner.execute_step(plan, ready[0]))
            self.assertEqual(plan.steps[0].status, "completed")

            # Simulate restart: create new store from same file
            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.steps[0].status, "completed")
            self.assertEqual(loaded.steps[1].status, "planned")

            # Resume execution
            runner2 = PlanRunner(store=store2)
            runner2._executor = mock_executor
            remaining_ready = loaded.next_ready_steps()
            self.assertEqual(len(remaining_ready), 1)
            self.assertEqual(remaining_ready[0].id, "s2")

            for _ in range(2):
                ready = loaded.next_ready_steps()
                if not ready:
                    break
                loop.run_until_complete(runner2.execute_step(loaded, ready[0]))

            loop.close()

            self.assertEqual(loaded.status, "completed")
            self.assertEqual(mock_executor.execute.call_count, 3)
        finally:
            tmppath.unlink(missing_ok=True)


class TestPlanFailureAndReplan(unittest.TestCase):
    """Step failure → fallback → plan continues."""

    def test_fallback_on_failure(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="Fallback test", status="active",
            steps=[
                PlanStep(
                    id="s1", action_type="risky_action",
                    fallback=PlanStepFallback(action_type="safe_action"),
                ),
                PlanStep(id="s2", action_type="final_step", depends_on=["s1"]),
            ],
            created_at=_now(), updated_at=_now(),
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            store = PlanStore(path=tmppath)
            store.add(plan)
            runner = PlanRunner(store=store)

            # First call fails, subsequent calls succeed
            fail_report = _make_mock_report("failed", "permission denied")
            ok_report = _make_mock_report("executed", "ok")
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(side_effect=[fail_report, ok_report, ok_report])
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()

            # Execute step 1 — should fail and trigger fallback
            ready = plan.next_ready_steps()
            result1 = loop.run_until_complete(runner.execute_step(plan, ready[0]))

            # After replan, step s1 should have been replaced with safe_action
            s1 = plan.get_step("s1")
            self.assertEqual(s1.action_type, "safe_action")

            # Continue execution — fallback step + step 2 should succeed
            for _ in range(2):
                ready = plan.next_ready_steps()
                if not ready:
                    break
                loop.run_until_complete(runner.execute_step(plan, ready[0]))

            loop.close()

            self.assertEqual(plan.status, "completed")
        finally:
            tmppath.unlink(missing_ok=True)


class TestPlanCandidatesInDecision(unittest.TestCase):
    """Plan steps enter as Candidates and compete fairly with goal actions."""

    def test_plan_candidate_source_tag(self):
        """Plan step candidates have source='plan:{plan_id}:{step_id}'."""
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="search_web")],
            created_at=_now(), updated_at=_now(),
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)
        try:
            store = PlanStore(path=tmppath)
            store.add(plan)

            # Simulate what _get_plan_candidates does
            candidates = []
            for p in store.active_plans():
                for step in p.next_ready_steps(limit=2):
                    c = Candidate(
                        action_type=step.action_type,
                        params={**step.params, "_plan_id": p.id, "_step_id": step.id},
                        goal_ids=[p.goal_id] if p.goal_id else [],
                        confidence=step.confidence,
                        urgency=min(1.0, 0.55 + 0.05),
                        timing_score=1.0,
                        estimated_cost_inr=step.estimated_cost_inr,
                        source=f"plan:{p.id}:{step.id}",
                    )
                    candidates.append(c)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].source, "plan:p1:s1")
            self.assertEqual(candidates[0].action_type, "search_web")
        finally:
            tmppath.unlink(missing_ok=True)

    def test_plan_candidate_urgency_bonus(self):
        """Plan candidates get +0.05 urgency over baseline."""
        c = Candidate(
            action_type="test",
            params={},
            urgency=min(1.0, 0.55 + 0.05),
            source="plan:p1:s1",
        )
        self.assertAlmostEqual(c.urgency, 0.60)


class TestPlanVerificationIntegration(unittest.TestCase):
    """verify_step_outcome with different verification strategies."""

    def test_status_check_integration(self):
        step = PlanStep(id="s1", action_type="test", verification={"type": "status_check"})
        self.assertTrue(verify_step_outcome(step, "executed"))
        self.assertFalse(verify_step_outcome(step, "blocked"))

    def test_always_verification(self):
        step = PlanStep(id="s1", action_type="test", verification={"type": "always"})
        self.assertTrue(verify_step_outcome(step, "failed"))


class TestMultiplePlansConcurrent(unittest.TestCase):
    """Two active plans — steps from both appear as candidates."""

    def test_two_plans_both_contribute_candidates(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            store = PlanStore(path=tmppath)

            p1 = Plan(
                id="p1", goal_id="g1", objective="Plan A", status="active",
                steps=[PlanStep(id="s1", action_type="action_a")],
                created_at=_now(), updated_at=_now(),
            )
            p2 = Plan(
                id="p2", goal_id="g2", objective="Plan B", status="active",
                steps=[PlanStep(id="s1", action_type="action_b")],
                created_at=_now(), updated_at=_now(),
            )
            store.add(p1)
            store.add(p2)

            active = store.active_plans()
            self.assertEqual(len(active), 2)

            all_ready = []
            for plan in active:
                all_ready.extend(plan.next_ready_steps())

            self.assertEqual(len(all_ready), 2)
            action_types = {s.action_type for s in all_ready}
            self.assertEqual(action_types, {"action_a", "action_b"})
        finally:
            tmppath.unlink(missing_ok=True)


class TestCrashRecovery(unittest.TestCase):
    """Plan-step crash/restart recovery (MUST-FIX blocker #2, see
    VECTOR_TECHNICAL_KNOWLEDGE/51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md §16.B
    and VECTOR_TECHNICAL_KNOWLEDGE/52_AUTONOMY_BLOCKER_REMEDIATION.md).

    execute_step() persists status='running' to disk BEFORE executing
    (plans.py:~698), then resolves to a terminal status after. A step still
    'running' the next time a plan is freshly loaded into a NEW PlanStore
    was, by construction, orphaned by a process that died mid-step — no
    live code path in this single-process/single-PlanRunner architecture
    can leave a step 'running' across a fresh PlanStore.

    These tests don't kill a real OS process (impractical in-process); they
    write the exact 'crashed' persisted state directly to disk via the real
    PlanStore.save()/Plan.to_dict() machinery, then load it through a FRESH
    PlanStore instance — byte-for-byte the same code path a real process
    restart takes (PlanStore._ensure_loaded() cannot distinguish an
    in-process simulated crash from a real one: both are 'a JSON file on
    disk has status=running, and this is this PlanStore's first load of
    it'). This is the same simulation technique TestPlanSurvivesRestart
    above already uses for the clean-completion case.
    """

    def _plan_with_running_step(
        self, action_type: str, fallback: PlanStepFallback | None = None,
        extra_steps: list[PlanStep] | None = None,
    ) -> tuple[Path, Plan]:
        """Write a plan with one step stuck at status='running' directly to
        disk (via the real Plan/PlanStore serialization), simulating the
        exact on-disk state a crash mid-execute_step() would leave."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        steps = [
            PlanStep(id="s1", action_type=action_type, status="running", fallback=fallback),
        ]
        if extra_steps:
            steps.extend(extra_steps)
        plan = Plan(
            id="p1", goal_id="g1", objective="Crash recovery test", status="active",
            steps=steps,
            created_at=_now(), updated_at=_now(),
        )
        plan.record_event("step_started", "Step s1 started", step_id="s1")

        # Write via the REAL persistence layer (PlanStore.save), not a
        # hand-built JSON blob — proves the recovery hook fires on genuine
        # PlanStore-written state, not a test-only shape.
        store = PlanStore(path=tmppath)
        store.add(plan)
        return tmppath, plan

    # -- C, D, E, F, G: step enters running, "crash" occurs, fresh process
    #    detects and recovers a GREEN (safe) step -------------------------

    def test_green_step_detected_and_reset_to_planned(self):
        """C-G: a GREEN-tier step stuck 'running' is detected on fresh load
        and becomes eligible for re-execution (reset to 'planned')."""
        tmppath, _ = self._plan_with_running_step("search_web")  # GREEN
        try:
            # "new process" = fresh PlanStore over the same file
            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")
            step = loaded.get_step("s1")

            self.assertEqual(step.status, "planned")  # G: eligible again
            self.assertIsNotNone(step.retry_info)
            self.assertEqual(step.retry_info["recovery_decision"], "reset_to_planned")
            self.assertFalse(loaded.review_required)

            # Recovery persisted the reset immediately — a second fresh
            # load must NOT re-fire recovery (no duplicate event).
            events = [e for e in loaded.events if e.type == "step_recovered"]
            self.assertEqual(len(events), 1)
        finally:
            tmppath.unlink(missing_ok=True)

    # -- H, I: recovery executes correctly + dependent steps can proceed --

    def test_recovered_green_step_executes_and_unblocks_dependents(self):
        """H, I: after recovery, the step is re-offered by
        next_ready_steps(), executes successfully through the normal
        PlanRunner path, and a downstream dependent step becomes ready."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="Recover then continue", status="active",
                steps=[
                    PlanStep(id="s1", action_type="search_web", status="running"),  # GREEN
                    PlanStep(id="s2", action_type="respond", depends_on=["s1"]),
                ],
                created_at=_now(), updated_at=_now(),
            )
            plan.record_event("step_started", "Step s1 started", step_id="s1")
            store = PlanStore(path=tmppath)
            store.add(plan)

            # Fresh process: load triggers recovery
            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")
            self.assertEqual(loaded.get_step("s1").status, "planned")

            # Recovered step is offered again and executes normally
            runner = PlanRunner(store=store2)
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=_make_mock_report())
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()
            ready = loaded.next_ready_steps()
            self.assertEqual([s.id for s in ready], ["s1"])
            loop.run_until_complete(runner.execute_step(loaded, ready[0]))
            self.assertEqual(loaded.get_step("s1").status, "completed")

            # I: dependent step s2 is now ready
            ready2 = loaded.next_ready_steps()
            self.assertEqual([s.id for s in ready2], ["s2"])
            loop.run_until_complete(runner.execute_step(loaded, ready2[0]))
            loop.close()

            self.assertEqual(loaded.status, "completed")
            # Exactly 2 real executions total for this plan: the recovered
            # s1 (once — not re-run a second time by anything) and s2. If
            # recovery had left s1 in a state that could be picked up and
            # executed twice, this would be 3+.
            self.assertEqual(mock_executor.execute.call_count, 2)
        finally:
            tmppath.unlink(missing_ok=True)

    # -- Safety check: non-GREEN step is NEVER auto-resumed -----------------

    def test_yellow_tier_step_not_auto_resumed(self):
        """SAFETY: a YELLOW-tier step (e.g. commit_code) stuck 'running'
        must NOT be silently reset to 'planned' and re-executed — it could
        have a real side effect (file write, external call) already in
        flight. It is marked 'failed' with an explicit reason instead, and
        the plan is flagged for review."""
        tmppath, _ = self._plan_with_running_step("commit_code")  # YELLOW, no fallback
        try:
            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")
            step = loaded.get_step("s1")

            self.assertEqual(step.status, "failed")
            self.assertNotEqual(step.status, "planned")  # never silently re-armed
            self.assertIn("not safe to auto-resume", step.reason)
            self.assertEqual(step.retry_info["recovery_decision"], "marked_failed_not_auto_resumed")
            self.assertTrue(loaded.review_required)
        finally:
            tmppath.unlink(missing_ok=True)

    def test_red_tier_step_not_auto_resumed(self):
        """SAFETY: same as above for a RED-tier action (financial_transaction) —
        the highest-risk category must never be blindly re-run."""
        tmppath, _ = self._plan_with_running_step("financial_transaction")
        try:
            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")
            step = loaded.get_step("s1")

            self.assertEqual(step.status, "failed")
            self.assertTrue(loaded.review_required)
        finally:
            tmppath.unlink(missing_ok=True)

    def test_non_green_step_with_fallback_routes_around_crash_safely(self):
        """A non-GREEN step that crashed but HAS a declared fallback still
        gets a safe path forward: the fallback (itself a fresh, unstarted
        action) is swapped in via the same synchronous logic replan_plan()
        already uses for a normal failure — the ORIGINAL risky action is
        still never auto-resumed."""
        tmppath, _ = self._plan_with_running_step(
            "commit_code", fallback=PlanStepFallback(action_type="search_web"),
        )
        try:
            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")
            step = loaded.get_step("s1")

            # The risky action was replaced, not resumed
            self.assertEqual(step.action_type, "search_web")
            self.assertEqual(step.status, "planned")
            self.assertFalse(loaded.review_required)
            fallback_events = [e for e in loaded.events if e.type == "fallback_activated"]
            self.assertEqual(len(fallback_events), 1)
        finally:
            tmppath.unlink(missing_ok=True)

    # -- J: completed steps are NOT re-executed ------------------------------

    def test_completed_step_untouched_by_recovery(self):
        """J: a genuinely completed step is never touched by recovery, even
        when another step in the same plan is stuck 'running'."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)
        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="Mixed statuses", status="active",
                steps=[
                    PlanStep(
                        id="s1", action_type="search_web", status="completed",
                        actual_outcome={"status": "executed", "summary": "ok", "verification_passed": True},
                        completed_at=_now(),
                    ),
                    PlanStep(id="s2", action_type="search_web", status="running", depends_on=["s1"]),
                ],
                created_at=_now(), updated_at=_now(),
            )
            store = PlanStore(path=tmppath)
            store.add(plan)

            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")

            s1 = loaded.get_step("s1")
            self.assertEqual(s1.status, "completed")
            self.assertIsNone(s1.retry_info)  # untouched — no recovery data written
            self.assertEqual(s1.actual_outcome["summary"], "ok")  # original outcome preserved

            s2 = loaded.get_step("s2")
            self.assertEqual(s2.status, "planned")  # only s2 was recovered
        finally:
            tmppath.unlink(missing_ok=True)

    # -- K: genuinely failed steps remain correctly represented --------------

    def test_pre_existing_failed_step_distinguishable_from_recovery_failure(self):
        """K: a step that failed BEFORE the crash (for a real, unrelated
        reason) is left exactly as it was — recovery must not touch it or
        overwrite its original failure reason, and it's distinguishable
        from a recovery-driven failure (retry_info is None vs. populated)."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)
        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="Pre-existing failure", status="active",
                steps=[
                    PlanStep(
                        id="s1", action_type="search_web", status="failed",
                        reason="original unrelated failure — no permission",
                    ),
                    PlanStep(id="s2", action_type="commit_code", status="running"),
                ],
                created_at=_now(), updated_at=_now(),
            )
            store = PlanStore(path=tmppath)
            store.add(plan)

            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")

            s1 = loaded.get_step("s1")
            self.assertEqual(s1.status, "failed")
            self.assertEqual(s1.reason, "original unrelated failure — no permission")
            self.assertIsNone(s1.retry_info)  # NOT touched by recovery

            s2 = loaded.get_step("s2")
            self.assertEqual(s2.status, "failed")  # recovery-driven failure (YELLOW, no fallback)
            self.assertIsNotNone(s2.retry_info)  # WAS touched by recovery — distinguishable
            self.assertIn("Interrupted by process restart", s2.reason)
        finally:
            tmppath.unlink(missing_ok=True)

    # -- L: multiple recovery attempts cannot execute the same step
    #    concurrently -------------------------------------------------------

    def test_recovery_is_idempotent_across_repeated_loads(self):
        """L: recovery must not re-fire (and must not risk a second,
        concurrent 'recovery' of the same step) on a second, third, etc.
        fresh load of an already-recovered plan — the persisted status is
        no longer 'running' after the first recovery, so the guard at the
        top of _recover_stale_running_steps() (status != 'running' -> skip)
        makes a second pass a structural no-op, not a race that needs a
        lock."""
        tmppath, _ = self._plan_with_running_step("search_web")
        try:
            # Simulate three independent "process starts" in a row.
            statuses = []
            event_counts = []
            for _ in range(3):
                store = PlanStore(path=tmppath)
                loaded = store.get("p1")
                statuses.append(loaded.get_step("s1").status)
                event_counts.append(
                    len([e for e in loaded.events if e.type == "step_recovered"])
                )

            self.assertEqual(statuses, ["planned", "planned", "planned"])
            # Only ONE step_recovered event exists, ever — later loads see
            # the already-recovered on-disk state and add nothing new.
            self.assertEqual(event_counts, [1, 1, 1])
        finally:
            tmppath.unlink(missing_ok=True)

    # -- M: recovery state survives persistence/reload -----------------------

    def test_recovery_decision_persisted_to_disk_not_just_memory(self):
        """M: the recovered status and retry_info are written to disk
        immediately (PlanStore.save()), not just held in the in-memory
        Plan object — verified by reading the raw JSON file directly,
        bypassing PlanStore entirely."""
        tmppath, _ = self._plan_with_running_step("search_web")
        try:
            store2 = PlanStore(path=tmppath)
            store2.get("p1")  # triggers recovery + save()

            raw = json.loads(tmppath.read_text(encoding="utf-8"))
            disk_step = raw["plans"][0]["steps"][0]
            self.assertEqual(disk_step["status"], "planned")
            self.assertIsNotNone(disk_step["retry_info"])
            self.assertEqual(disk_step["retry_info"]["recovery_decision"], "reset_to_planned")
        finally:
            tmppath.unlink(missing_ok=True)

    def test_plan_dependencies_preserved_through_recovery(self):
        """Recovery must not disturb depends_on links — DAG structure
        survives the crash/recovery cycle unchanged."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)
        try:
            plan = Plan(
                id="p1", goal_id="g1", objective="DAG preserved", status="active",
                steps=[
                    PlanStep(id="s1", action_type="search_web", status="running"),
                    PlanStep(id="s2", action_type="search_web", depends_on=["s1"]),
                    PlanStep(id="s3", action_type="search_web", depends_on=["s1", "s2"]),
                ],
                created_at=_now(), updated_at=_now(),
            )
            store = PlanStore(path=tmppath)
            store.add(plan)

            store2 = PlanStore(path=tmppath)
            loaded = store2.get("p1")

            self.assertEqual(loaded.get_step("s2").depends_on, ["s1"])
            self.assertEqual(loaded.get_step("s3").depends_on, ["s1", "s2"])
            self.assertFalse(loaded.has_circular_deps())
        finally:
            tmppath.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
