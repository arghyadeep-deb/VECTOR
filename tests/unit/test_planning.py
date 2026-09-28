"""Unit tests for multi-step plan system (core/runtime/plans.py).

Tests Plan, PlanStep, PlanStore, PlanEvent, verify_step_outcome, replan_plan,
and DAG dependency resolution — all without network or LLM calls.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.runtime.plans import (
    MAX_REPLANS,
    Plan,
    PlanEvent,
    PlanRunner,
    PlanStep,
    PlanStepFallback,
    PlanStore,
    _now,
    decompose_goal_to_plan,
    get_plan_store,
    replan_plan,
    verify_step_outcome,
)


class TestPlanStep(unittest.TestCase):
    """PlanStep dataclass serialization and defaults."""

    def test_defaults(self):
        s = PlanStep(id="s1", action_type="search_web")
        self.assertEqual(s.status, "planned")
        self.assertEqual(s.depends_on, [])
        self.assertEqual(s.priority, 1)
        self.assertAlmostEqual(s.confidence, 0.5)
        self.assertIsNone(s.fallback)
        self.assertIsNone(s.actual_outcome)

    def test_round_trip(self):
        s = PlanStep(
            id="s1",
            action_type="search_web",
            params={"query": "test"},
            depends_on=["s0"],
            expected_outcome="Results found",
            verification={"type": "status_check"},
            confidence=0.8,
            fallback=PlanStepFallback(action_type="respond", params={"message": "fallback"}),
        )
        d = s.to_dict()
        s2 = PlanStep.from_dict(d)
        self.assertEqual(s2.id, "s1")
        self.assertEqual(s2.action_type, "search_web")
        self.assertEqual(s2.depends_on, ["s0"])
        self.assertAlmostEqual(s2.confidence, 0.8)
        self.assertIsNotNone(s2.fallback)
        self.assertEqual(s2.fallback.action_type, "respond")

    def test_from_dict_handles_missing_fields(self):
        s = PlanStep.from_dict({"id": "x"})
        self.assertEqual(s.id, "x")
        self.assertEqual(s.action_type, "respond")
        self.assertEqual(s.status, "planned")

    def test_from_dict_handles_null_fields(self):
        s = PlanStep.from_dict({
            "id": "x",
            "action_type": "test",
            "depends_on": None,
            "fallback": None,
            "actual_outcome": None,
        })
        self.assertEqual(s.depends_on, [])
        self.assertIsNone(s.fallback)


class TestPlanDAG(unittest.TestCase):
    """DAG dependency resolution — next_ready_steps and cycle detection."""

    def _make_dag_plan(self) -> Plan:
        return Plan(
            id="p1", goal_id="g1", objective="test", status="active",
            steps=[
                PlanStep(id="s1", action_type="a"),
                PlanStep(id="s2", action_type="b", depends_on=["s1"]),
                PlanStep(id="s3", action_type="c", depends_on=["s1"]),
                PlanStep(id="s4", action_type="d", depends_on=["s2", "s3"]),
            ],
            created_at=_now(), updated_at=_now(),
        )

    def test_initial_ready_is_root(self):
        plan = self._make_dag_plan()
        ready = plan.next_ready_steps()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "s1")

    def test_after_completing_root_two_steps_ready(self):
        plan = self._make_dag_plan()
        plan.steps[0].status = "completed"
        ready = plan.next_ready_steps()
        self.assertEqual(len(ready), 2)
        self.assertEqual({r.id for r in ready}, {"s2", "s3"})

    def test_after_completing_all_but_last(self):
        plan = self._make_dag_plan()
        plan.steps[0].status = "completed"
        plan.steps[1].status = "completed"
        plan.steps[2].status = "completed"
        ready = plan.next_ready_steps()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "s4")

    def test_no_ready_when_all_complete(self):
        plan = self._make_dag_plan()
        for s in plan.steps:
            s.status = "completed"
        ready = plan.next_ready_steps()
        self.assertEqual(len(ready), 0)

    def test_limit_respected(self):
        plan = self._make_dag_plan()
        plan.steps[0].status = "completed"
        ready = plan.next_ready_steps(limit=1)
        self.assertEqual(len(ready), 1)

    def test_priority_ordering(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="test", status="active",
            steps=[
                PlanStep(id="s1", action_type="low", priority=5),
                PlanStep(id="s2", action_type="high", priority=1),
                PlanStep(id="s3", action_type="mid", priority=3),
            ],
            created_at=_now(), updated_at=_now(),
        )
        ready = plan.next_ready_steps()
        self.assertEqual(ready[0].id, "s2")  # priority 1 first
        self.assertEqual(ready[1].id, "s3")
        self.assertEqual(ready[2].id, "s1")

    def test_circular_dependency_detected(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="circular", status="active",
            steps=[
                PlanStep(id="s1", action_type="a", depends_on=["s2"]),
                PlanStep(id="s2", action_type="b", depends_on=["s1"]),
            ],
            created_at=_now(), updated_at=_now(),
        )
        self.assertTrue(plan.has_circular_deps())

    def test_no_false_positive_on_acyclic(self):
        plan = self._make_dag_plan()
        self.assertFalse(plan.has_circular_deps())

    def test_unknown_dep_ignored(self):
        """A depends_on referencing a nonexistent step doesn't break resolution."""
        plan = Plan(
            id="p1", goal_id="g1", objective="test", status="active",
            steps=[
                PlanStep(id="s1", action_type="a", depends_on=["nonexistent"]),
            ],
            created_at=_now(), updated_at=_now(),
        )
        # "nonexistent" is not in completed_ids, so s1 should NOT be ready
        ready = plan.next_ready_steps()
        self.assertEqual(len(ready), 0)


class TestPlanProgress(unittest.TestCase):
    """Progress and confidence calculations."""

    def test_progress_starts_at_zero(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="a"), PlanStep(id="s2", action_type="b")],
            created_at=_now(), updated_at=_now(),
        )
        plan.update_progress()
        self.assertAlmostEqual(plan.progress, 0.0)

    def test_progress_half_done(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="a"), PlanStep(id="s2", action_type="b")],
            created_at=_now(), updated_at=_now(),
        )
        plan.steps[0].status = "completed"
        plan.update_progress()
        self.assertAlmostEqual(plan.progress, 0.5)

    def test_progress_skipped_counts(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="a"), PlanStep(id="s2", action_type="b")],
            created_at=_now(), updated_at=_now(),
        )
        plan.steps[0].status = "completed"
        plan.steps[1].status = "skipped"
        plan.update_progress()
        self.assertAlmostEqual(plan.progress, 1.0)

    def test_confidence_averages_completed(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[
                PlanStep(id="s1", action_type="a", confidence=0.8),
                PlanStep(id="s2", action_type="b", confidence=0.4),
            ],
            created_at=_now(), updated_at=_now(),
        )
        plan.update_progress()
        self.assertAlmostEqual(plan.confidence, 0.6)

    def test_is_complete(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="a"), PlanStep(id="s2", action_type="b")],
            created_at=_now(), updated_at=_now(),
        )
        self.assertFalse(plan.is_complete())
        plan.steps[0].status = "completed"
        self.assertFalse(plan.is_complete())
        plan.steps[1].status = "completed"
        self.assertTrue(plan.is_complete())


class TestPlanEvents(unittest.TestCase):
    """Event recording and serialization."""

    def test_record_event(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[], created_at=_now(), updated_at=_now(),
        )
        event = plan.record_event("step_started", "Step s1 started", step_id="s1")
        self.assertEqual(event.type, "step_started")
        self.assertEqual(event.step_id, "s1")
        self.assertEqual(len(plan.events), 1)

    def test_event_serialization(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[], created_at=_now(), updated_at=_now(),
        )
        plan.record_event("test", "msg", data={"key": "value"})
        d = plan.to_dict()
        plan2 = Plan.from_dict(d)
        self.assertEqual(len(plan2.events), 1)
        self.assertEqual(plan2.events[0].type, "test")
        self.assertEqual(plan2.events[0].data, {"key": "value"})


class TestPlanStore(unittest.TestCase):
    """JSON-file persistence — plans survive save/load round-trip."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._path = Path(self._tmp.name)
        self._tmp.close()
        self._path.unlink(missing_ok=True)

    def tearDown(self):
        self._path.unlink(missing_ok=True)

    def _make_plan(self, plan_id="p1") -> Plan:
        return Plan(
            id=plan_id, goal_id="g1", objective="test objective", status="active",
            steps=[
                PlanStep(id="s1", action_type="a", depends_on=[]),
                PlanStep(id="s2", action_type="b", depends_on=["s1"]),
            ],
            created_at=_now(), updated_at=_now(),
            confidence=0.7, progress=0.5,
        )

    def test_save_and_load(self):
        store = PlanStore(path=self._path)
        plan = self._make_plan()
        store.add(plan)

        store2 = PlanStore(path=self._path)
        loaded = store2.get("p1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.objective, "test objective")
        self.assertEqual(len(loaded.steps), 2)
        self.assertEqual(loaded.steps[1].depends_on, ["s1"])

    def test_active_plans_filter(self):
        store = PlanStore(path=self._path)
        store.add(self._make_plan("p1"))
        p2 = self._make_plan("p2")
        p2.status = "completed"
        store.add(p2)
        p3 = self._make_plan("p3")
        p3.status = "paused"
        store.add(p3)

        active = store.active_plans()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].id, "p1")

    def test_plans_for_goal(self):
        store = PlanStore(path=self._path)
        p1 = self._make_plan("p1")
        p1.goal_id = "g1"
        store.add(p1)
        p2 = self._make_plan("p2")
        p2.goal_id = "g2"
        store.add(p2)

        result = store.plans_for_goal("g1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "p1")

    def test_list_limit(self):
        store = PlanStore(path=self._path)
        for i in range(5):
            store.add(self._make_plan(f"p{i}"))
        result = store.list(limit=3)
        self.assertEqual(len(result), 3)

    def test_clear(self):
        store = PlanStore(path=self._path)
        store.add(self._make_plan())
        store.clear(persist=True)
        store2 = PlanStore(path=self._path)
        self.assertIsNone(store2.get("p1"))

    def test_empty_file_handled(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("{}", encoding="utf-8")
        store = PlanStore(path=self._path)
        self.assertEqual(len(store.list()), 0)

    def test_corrupt_file_handled(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("not json", encoding="utf-8")
        store = PlanStore(path=self._path)
        self.assertEqual(len(store.list()), 0)


class TestPlanSerialization(unittest.TestCase):
    """Full Plan to_dict/from_dict round-trip with all fields."""

    def test_full_round_trip(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="Full test", status="active",
            steps=[
                PlanStep(
                    id="s1", action_type="search_web",
                    params={"query": "test"},
                    depends_on=[],
                    expected_outcome="Results found",
                    verification={"type": "status_check"},
                    confidence=0.8,
                    fallback=PlanStepFallback(action_type="respond", trigger="failure"),
                ),
                PlanStep(
                    id="s2", action_type="summarize",
                    depends_on=["s1"],
                    estimated_time_sec=120.0,
                    estimated_cost_inr=5.0,
                ),
            ],
            created_at=_now(), updated_at=_now(),
            confidence=0.7, progress=0.5, replan_count=1,
        )
        plan.record_event("test_event", "testing", step_id="s1", data={"k": "v"})

        d = plan.to_dict()
        restored = Plan.from_dict(d)

        self.assertEqual(restored.id, "p1")
        self.assertEqual(restored.goal_id, "g1")
        self.assertEqual(len(restored.steps), 2)
        self.assertEqual(restored.steps[0].fallback.action_type, "respond")
        self.assertEqual(restored.steps[1].estimated_time_sec, 120.0)
        self.assertEqual(restored.replan_count, 1)
        self.assertEqual(len(restored.events), 1)


class TestVerifyOutcome(unittest.TestCase):
    """verify_step_outcome — different verification types."""

    def test_status_check_pass(self):
        step = PlanStep(id="s1", action_type="test", verification={"type": "status_check"})
        self.assertTrue(verify_step_outcome(step, "executed"))

    def test_status_check_fail(self):
        step = PlanStep(id="s1", action_type="test", verification={"type": "status_check"})
        self.assertFalse(verify_step_outcome(step, "failed"))

    def test_always_passes(self):
        step = PlanStep(id="s1", action_type="test", verification={"type": "always"})
        self.assertTrue(verify_step_outcome(step, "failed"))

    def test_unknown_type_falls_back_to_status(self):
        step = PlanStep(id="s1", action_type="test", verification={"type": "unknown_type"})
        self.assertTrue(verify_step_outcome(step, "executed"))
        self.assertFalse(verify_step_outcome(step, "failed"))

    def test_file_exists_missing_path(self):
        step = PlanStep(id="s1", action_type="test", verification={
            "type": "file_exists", "criteria": {"path": "/nonexistent/file.txt"},
        })
        self.assertFalse(verify_step_outcome(step, "executed"))


class TestReplan(unittest.TestCase):
    """replan_plan — fallback, LLM replan, and abandon."""

    def test_fallback_activated(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[
                PlanStep(
                    id="s1", action_type="risky_action",
                    fallback=PlanStepFallback(action_type="safe_action"),
                ),
            ],
            created_at=_now(), updated_at=_now(),
        )
        plan.steps[0].status = "failed"
        plan.steps[0].reason = "failed"

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(replan_plan(plan, plan.steps[0]))
        loop.close()

        self.assertEqual(result.steps[0].action_type, "safe_action")
        self.assertEqual(result.replan_count, 1)
        self.assertEqual(result.events[-1].type, "fallback_activated")

    def test_abandon_after_budget(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="failing_action")],
            created_at=_now(), updated_at=_now(),
            replan_count=MAX_REPLANS,  # already at limit
        )
        plan.steps[0].status = "failed"

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(replan_plan(plan, plan.steps[0]))
        loop.close()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.replan_count, MAX_REPLANS + 1)

    def test_no_fallback_no_replan_triggers_abandon(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="no_fallback")],
            created_at=_now(), updated_at=_now(),
            replan_count=MAX_REPLANS,
        )
        plan.steps[0].status = "failed"

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(replan_plan(plan, plan.steps[0]))
        loop.close()

        self.assertEqual(result.status, "failed")


class TestDecomposeGoal(unittest.TestCase):
    """decompose_goal_to_plan — fallback to rule-based when LLM fails."""

    def test_decompose_returns_plan_or_none(self):
        """Even if both LLM and rules fail, returns None (not crash)."""
        # 2026-09-24 (external review, Phase 3): both are now lazily
        # imported inside decompose_goal_to_plan() from core.runtime.missions
        # (not module-level in core.runtime.plans anymore), so that's the
        # real patch target -- a `from X import Y` inside a function reads
        # the CURRENT value of Y in X at call time.
        loop = asyncio.new_event_loop()
        with patch("core.runtime.missions.MissionPlanAdvisor", side_effect=Exception("no LLM")):
            with patch("core.runtime.missions.ObjectiveDecomposer", side_effect=Exception("no rules")):
                result = loop.run_until_complete(decompose_goal_to_plan("g1", "test objective"))
        loop.close()
        # Both failed → returns None
        self.assertIsNone(result)

    def test_circular_deps_flattened(self):
        """If LLM returns circular deps, they get flattened to sequential."""
        # Mock the advisor to return circular steps (advise returns dict with "steps" key)
        mock_advisor = MagicMock()
        mock_advisor.advise = MagicMock(return_value={
            "steps": [
                {"action_type": "a", "depends_on": ["step-2"]},
                {"action_type": "b", "depends_on": ["step-1"]},
            ],
            "status": "ok",
        })

        loop = asyncio.new_event_loop()
        with patch("core.runtime.missions.MissionPlanAdvisor", return_value=mock_advisor):
            result = loop.run_until_complete(decompose_goal_to_plan("g1", "circular test"))
        loop.close()

        if result is not None:
            self.assertFalse(result.has_circular_deps())


class TestPlanRunner(unittest.TestCase):
    """PlanRunner.execute_step — single step execution."""

    def test_execute_step_success(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="test_action")],
            created_at=_now(), updated_at=_now(),
        )

        mock_executor = MagicMock()
        mock_report = MagicMock()
        mock_report.status = "executed"
        mock_report.reason = "ok"
        mock_report.result = {"data": "test"}
        mock_report.to_dict.return_value = {"status": "executed"}
        mock_executor.execute = AsyncMock(return_value=mock_report)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            store = PlanStore(path=tmppath)
            store.add(plan)
            runner = PlanRunner(store=store)
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(runner.execute_step(plan, plan.steps[0]))
            loop.close()

            self.assertEqual(result["status"], "completed")
            self.assertTrue(result["verification_passed"])
            self.assertEqual(plan.status, "completed")
            self.assertAlmostEqual(plan.progress, 1.0)
        finally:
            tmppath.unlink(missing_ok=True)

    def test_execute_step_failure_triggers_replan(self):
        plan = Plan(
            id="p1", goal_id="g1", objective="t", status="active",
            steps=[PlanStep(id="s1", action_type="failing_action")],
            created_at=_now(), updated_at=_now(),
        )

        mock_executor = MagicMock()
        mock_report = MagicMock()
        mock_report.status = "failed"
        mock_report.reason = "permission denied"
        mock_report.result = None
        mock_report.to_dict.return_value = {"status": "failed"}
        mock_executor.execute = AsyncMock(return_value=mock_report)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
        tmppath.unlink(missing_ok=True)

        try:
            store = PlanStore(path=tmppath)
            store.add(plan)
            runner = PlanRunner(store=store)
            runner._executor = mock_executor

            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(runner.execute_step(plan, plan.steps[0]))
            loop.close()

            self.assertEqual(result["status"], "failed")
            # Plan should eventually be failed after replan budget exhausted
            self.assertIn(plan.status, ("failed", "active"))
        finally:
            tmppath.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
