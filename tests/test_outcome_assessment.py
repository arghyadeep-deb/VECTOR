"""Shared outcome assessment (V1 handoff slice, built 2026-09-26).

  * executor: an explicit failure signal inside a payload whose `status` looks fine is a failure, not "executed"
  * plans: `result_field` / `all_of` verification checks the step's REAL result payload, not the handler's self-report
  * plans: dotted param bindings hand nested real output ("fields.detail_url") from one step to the next
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.runtime.executor import AutonomousExecutor, assess_payload_failure
from core.runtime.plans import Plan, PlanStep, _resolve_step_params, _now, verify_step_outcome


# ── executor ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload,expected", [
    ({"status": "ok", "error": "provider timed out"}, "error_field"),
    ({"status": "success", "success": False}, "success_false"),
    ({"ok": False}, "ok_false"),
    ({"status": "ok", "verified": False}, "verified_false"),
    ({"status": "ok", "error": {"code": 500}}, "error_field"),
])
def test_explicit_failure_signals_are_detected(payload, expected):
    assert assess_payload_failure(payload) == expected


@pytest.mark.parametrize("payload", [
    {"status": "ok"},
    {"status": "ok", "error": None},
    {"status": "ok", "error": ""},
    {"status": "ok", "error": []},
    {"status": "success", "success": True, "verified": True},   # a positive flag is not evidence, and not a failure either
    {},
    None,
    "not a dict",
])
def test_absence_of_a_signal_is_never_inferred_as_failure(payload):
    assert assess_payload_failure(payload) is None


def _gateway_result(payload, approved=True, executed=True):
    return SimpleNamespace(approved=approved, executed=executed, result=payload, reason="", level="GREEN")


def test_executor_verification_rejects_ok_status_with_an_error_field():
    v = AutonomousExecutor._verify_gateway_result(_gateway_result({"status": "ok", "error": "search backend down"}))
    assert v["ok"] is False and "search backend down" in v["message"]
    assert "payload_signal:error_field" in v["checks"]


def test_executor_verification_still_accepts_a_clean_success():
    v = AutonomousExecutor._verify_gateway_result(_gateway_result({"status": "success", "items": [1]}))
    assert v["ok"] is True


# ── plan verification ───────────────────────────────────────────────────────────

def _step(verification):
    return PlanStep(id="s", action_type="web_extract", verification=verification)


def test_result_field_equals_passes_only_with_the_evidence():
    v = {"type": "result_field", "criteria": {"field": "fields.title", "equals": "Invoice 42"}}
    assert verify_step_outcome(_step(v), "executed", {"fields": {"title": "Invoice 42"}}) is True
    assert verify_step_outcome(_step(v), "executed", {"fields": {"title": "Something else"}}) is False
    assert verify_step_outcome(_step(v), "executed", {"fields": {}}) is False
    assert verify_step_outcome(_step(v), "executed", None) is False


def test_result_field_requires_the_step_to_have_executed():
    v = {"type": "result_field", "criteria": {"field": "x", "non_empty": True}}
    assert verify_step_outcome(_step(v), "failed", {"x": "present"}) is False
    assert verify_step_outcome(_step(v), "blocked", {"x": "present"}) is False


@pytest.mark.parametrize("criteria,payload,ok", [
    ({"field": "a", "contains": "cat"}, {"a": "a cat sat"}, True),
    ({"field": "a", "contains": "dog"}, {"a": "a cat sat"}, False),
    ({"field": "a", "regex": r"^\d{3}$"}, {"a": "123"}, True),
    ({"field": "a", "regex": r"^\d{3}$"}, {"a": "12"}, False),
    ({"field": "a", "regex": "("}, {"a": "x"}, False),                # bad regex fails closed
    ({"field": "a", "in": ["x", "y"]}, {"a": "y"}, True),
    ({"field": "a", "in": ["x", "y"]}, {"a": "z"}, False),
    ({"field": "a", "non_empty": True}, {"a": "  "}, False),
    ({"field": "a", "non_empty": True}, {"a": [0]}, True),
    ({"field": "a", "min_items": 2}, {"a": [1, 2, 3]}, True),
    ({"field": "a", "min_items": 2}, {"a": [1]}, False),
    ({"field": "links.1.href", "equals": "http://b"}, {"links": [{"href": "http://a"}, {"href": "http://b"}]}, True),
    ({"field": "a"}, {"a": "anything"}, False),                        # no test given: must not silently pass
    ({}, {"a": 1}, False),
])
def test_result_field_criteria(criteria, payload, ok):
    assert verify_step_outcome(_step({"type": "result_field", "criteria": criteria}), "executed", payload) is ok


def test_all_of_needs_every_check_and_never_passes_empty():
    both = {"type": "all_of", "criteria": {"checks": [
        {"type": "status_check"},
        {"type": "result_field", "criteria": {"field": "n", "min_items": 1}},
    ]}}
    assert verify_step_outcome(_step(both), "executed", {"n": [1]}) is True
    assert verify_step_outcome(_step(both), "executed", {"n": []}) is False
    assert verify_step_outcome(_step(both), "failed", {"n": [1]}) is False
    assert verify_step_outcome(_step({"type": "all_of", "criteria": {"checks": []}}), "executed", {}) is False


def test_existing_verification_types_are_unchanged():
    assert verify_step_outcome(_step({"type": "status_check"}), "executed") is True
    assert verify_step_outcome(_step({"type": "status_check"}), "failed") is False
    assert verify_step_outcome(_step({"type": "always"}), "failed") is True


# ── dotted bindings ─────────────────────────────────────────────────────────────

def _plan_with_completed_dep(result):
    dep = PlanStep(id="s1", action_type="web_extract", status="completed",
                   actual_outcome={"status": "executed", "verification_passed": True, "result": result})
    nxt = PlanStep(id="s2", action_type="web_extract", depends_on=["s1"], params={"static": 1},
                   param_bindings={"url": "s1.fields.detail_url", "first": "s1.links.0.href", "top": "s1.title",
                                   "missing": "s1.fields.nope"})
    return Plan(id="p", goal_id="", objective="o", status="active", steps=[dep, nxt], created_at=_now(), updated_at=_now()), nxt


def test_dotted_bindings_resolve_nested_values_and_keep_static_params():
    plan, nxt = _plan_with_completed_dep({
        "title": "Index", "fields": {"detail_url": "http://x/detail/7"}, "links": [{"href": "http://x/a"}]})
    params = _resolve_step_params(plan, nxt)
    assert params["url"] == "http://x/detail/7" and params["first"] == "http://x/a" and params["top"] == "Index"
    assert params["static"] == 1 and "missing" not in params
    assert "url" not in nxt.params, "the plan's own persisted params must not be mutated"


def test_literal_top_level_key_with_a_dot_still_wins():
    plan, nxt = _plan_with_completed_dep({"fields.detail_url": "literal", "fields": {"detail_url": "nested"}})
    assert _resolve_step_params(plan, nxt)["url"] == "literal"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
