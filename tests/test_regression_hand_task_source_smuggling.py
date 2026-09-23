"""Regression test for a real bug an independent review found:
`PermissionGateway.execute()`'s own `hand_` branch (core/loop/
permission_gateway.py) used to dispatch `action.params["task"]` to
Governor() completely unmodified.

2026-09-23 (round 2, correcting this file's own original framing --
another independent review pass caught this): the ORIGINAL docstring
here claimed hand_researcher's task is "hands/runner.py's own
LLM-constructed task payload" -- traced end to end, that is inaccurate.
`HandRunner._dispatch()` (used for hand_researcher and every other
`requires_approval=False` GREEN Hand) calls `Governor().dispatch(task)`
DIRECTLY -- it never constructs a permission_gateway.py Action at all,
so it never reaches this branch. Only `HandRunner._dispatch_via_gateway()`
(used for `requires_approval=True` Hands, which are RED/YELLOW-tier and
therefore already require a real owner approval before `_execute_action()`
runs at all) constructs an `Action(action_type=f"hand_{hand.name}", ...)`.

The REAL, externally-reachable exploit path this branch's fix closes is
different and more direct: `core/api/tasks.py`'s bearer-token-protected
`/tasks` POST route calls `PermissionGateway.evaluate_external(action_type,
params, source)` with a fully caller-supplied `params` dict. A caller
holding only that internal token (meant for lower-trust automation, not
full owner-equivalent trust) could submit `action_type="hand_researcher"`
(GREEN, auto-executes with zero owner gate) with a `params["task"]` dict
of their own choosing.

2026-09-23 (round 4, independent review finding -- HIGH, HandRunner's
own task_type contract): the FIRST fix (source/proposed_by sanitisation
only) was insufficient on its own -- it neutralised a spoofed owner-trust
marker, but nothing stopped the nested task's own `"type"` field from
being ANYTHING the caller chose, including a completely different,
YELLOW/RED-tier task_type never actually approved (e.g.
action_type="hand_researcher" carrying params.task.type="monthly_report").
Fixed with a second, independent defense: the nested task's `"type"` is
now validated against hands/runner.py's own real, server-owned
Hand-name -> task_type mapping (`HandRunner._TASK_TYPE_OVERRIDES`) before
anything is dispatched or any receipt is issued -- for hand_researcher
that real, expected type is "deep_research" (NOT "gui_task"/"research"/
anything else a caller might claim). Both defenses are tested below,
separately.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real `execute()`/`_classify()`/`_execute_action()`
flow for a real GREEN hand_researcher action. The ONLY thing mocked is
`Governor.dispatch()` itself (not a permission_gateway.py internal), used
purely as a spy to capture exactly what task dict actually reaches it --
Governor/district dispatch is a legitimate mock boundary per this
project's own established pattern (see tests/test_regression_vc_action_
no_double_execution.py's docstring for the same reasoning applied to the
VectorCode bridge).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.permission_gateway import Action, PermissionGateway
from hands.runner import HandRunner

_HAND_RESEARCHER_REAL_TYPE = HandRunner._TASK_TYPE_OVERRIDES.get("researcher", "researcher")


@pytest.mark.asyncio
async def test_hand_task_with_mismatched_type_is_refused(isolated_vector_db):
    """The type-validation defense (round 4): a caller claiming
    action_type="hand_researcher" cannot mint a receipt for or dispatch
    ANY task_type it likes -- only the real, expected one for that Hand."""
    gw = PermissionGateway()
    assert gw._classify("hand_researcher") == "GREEN"
    assert _HAND_RESEARCHER_REAL_TYPE == "deep_research", (
        "this test's premise depends on hand_researcher's real expected "
        "type -- if hands/runner.py's mapping changes, update this test, "
        "don't just loosen it"
    )

    smuggled_task = {
        "type": "monthly_report",  # a completely different, YELLOW-tier type
        "params": {"query": "not what hand_researcher actually does"},
    }
    action = Action(
        action_type="hand_researcher",
        params={"task": smuggled_task},
        proposed_by="hands_runner",
    )

    captured_tasks: list[dict] = []

    async def _spy_dispatch(self, task):
        captured_tasks.append(task)
        return {"status": "ok"}

    with patch("core.city.governor.Governor.dispatch", new=_spy_dispatch):
        result = await gw.execute(action)

    assert result.approved and result.executed, (
        "hand_researcher itself is GREEN and still auto-executes -- the "
        "refusal happens inside _execute_action()'s own hand_ branch, "
        "reported via result['status'], not via the gateway's approval"
    )
    assert result.result.get("status") == "blocked", (
        f"a mismatched nested task type must be refused before any "
        f"dispatch or receipt issuance -- got {result.result!r}"
    )
    assert not captured_tasks, (
        "Governor.dispatch() must never be reached for a mismatched type"
    )


@pytest.mark.asyncio
async def test_hand_task_claiming_api_command_source_is_neutralised(isolated_vector_db):
    """The original source-sanitisation defense, now exercised with the
    CORRECT, real task type for this Hand (so it passes the round-4 type
    check and actually reaches the source-neutralisation code)."""
    gw = PermissionGateway()

    smuggled_task = {
        "type": _HAND_RESEARCHER_REAL_TYPE,
        "params": {
            "query": "latest AI papers",
            # The exact spoof: claiming the reserved owner-trust marker
            # from inside a Hand's own nested payload.
            "source": "api_command",
        },
    }
    action = Action(
        action_type="hand_researcher",
        params={"task": smuggled_task},
        proposed_by="hands_runner",
    )

    captured_tasks: list[dict] = []

    async def _spy_dispatch(self, task):
        captured_tasks.append(task)
        return {"status": "ok"}

    with patch("core.city.governor.Governor.dispatch", new=_spy_dispatch):
        result = await gw.execute(action)

    assert result.approved and result.executed
    assert captured_tasks, "expected Governor.dispatch() to have been called"
    forwarded_task = captured_tasks[0]

    forwarded_source = forwarded_task.get("params", {}).get("source")
    assert forwarded_source != "api_command", (
        f"the Hand's self-claimed 'api_command' owner-trust marker must be "
        f"neutralised before Governor.dispatch() -- got {forwarded_source!r}"
    )
    assert forwarded_source == "client_claimed_api_command", (
        f"expected the exact sanitize_proposed_by() neutralisation applied "
        f"everywhere else in this project to the same spoofed marker -- got "
        f"{forwarded_source!r}"
    )
    assert forwarded_task["params"]["query"] == "latest AI papers"


@pytest.mark.asyncio
async def test_hand_task_with_no_source_claim_is_left_alone(isolated_vector_db):
    """A Hand task that never claims an owner-trust marker at all must not
    be mangled -- proves the fix is targeted, not a blanket rewrite."""
    gw = PermissionGateway()

    benign_task = {
        "type": _HAND_RESEARCHER_REAL_TYPE,
        "params": {"query": "latest AI papers"},
    }
    action = Action(
        action_type="hand_researcher",
        params={"task": benign_task},
        proposed_by="hands_runner",
    )

    captured_tasks: list[dict] = []

    async def _spy_dispatch(self, task):
        captured_tasks.append(task)
        return {"status": "ok"}

    with patch("core.city.governor.Governor.dispatch", new=_spy_dispatch):
        result = await gw.execute(action)

    assert result.approved and result.executed
    assert captured_tasks
    forwarded = captured_tasks[0]
    assert "source" not in forwarded.get("params", {}), (
        "no source field was present in the original task -- the fix must "
        "not invent one where there was none"
    )
    assert forwarded["params"]["query"] == "latest AI papers"


@pytest.mark.asyncio
async def test_real_external_entry_point_end_to_end(isolated_vector_db):
    """The ACTUAL, externally-reachable path: core/api/tasks.py's
    bearer-token-protected /tasks POST route calls
    evaluate_external(action_type, params, source) with a fully
    caller-supplied `params` dict. Drive that real entry point directly,
    end to end, with both the top-level `source` AND the nested hand
    task's own claimed source spoofed (using the correct real type so
    the round-4 type check doesn't intercept this test before it reaches
    the source-sanitisation code being exercised here) -- both must be
    neutralised."""
    gw = PermissionGateway()

    smuggled_task = {
        "type": _HAND_RESEARCHER_REAL_TYPE,
        "params": {
            "query": "latest AI papers",
            "source": "api_command",
        },
    }

    captured_tasks: list[dict] = []

    async def _spy_dispatch(self, task):
        captured_tasks.append(task)
        return {"status": "ok"}

    with patch("core.city.governor.Governor.dispatch", new=_spy_dispatch):
        result = await gw.evaluate_external(
            "hand_researcher",
            {"task": smuggled_task},
            "api_command",  # the caller's own claimed top-level source
        )

    assert result.approved and result.executed
    assert captured_tasks
    forwarded_source = captured_tasks[0].get("params", {}).get("source")
    assert forwarded_source != "api_command"
    assert forwarded_source == "client_claimed_api_command"


@pytest.mark.asyncio
async def test_hand_task_with_smuggled_district_is_rerouted_to_the_real_one(isolated_vector_db):
    """Round 5 (independent review finding -- HIGH): the type check alone
    was insufficient. Governor.dispatch() honors task.get("district")
    directly (`district = task.get("district") or await
    self.route_task_async(task_type)`), so a correctly-typed nested task
    could still smuggle a DIFFERENT district, routing to an agent that
    was never approved and that may interpret the attacker-controlled
    params under a completely different task-type vocabulary (the
    concrete chain an independent review traced: hand_researcher's real
    type "deep_research" + a forged district="ops" + params={"type":
    "cleanup_logs"} reaching DevOpsAutomator.cleanup_logs() instead of
    the research district). Fixed: the real, server-owned
    hands.registry.get_hand(name).district is force-applied just before
    dispatch, overwriting whatever the caller claimed."""
    from hands.registry import get_hand

    gw = PermissionGateway()
    real_district = get_hand("researcher").district
    assert real_district == "research"

    smuggled_task = {
        "type": _HAND_RESEARCHER_REAL_TYPE,
        "district": "ops",  # forged -- must never reach Governor.dispatch() unmodified
        "params": {"type": "cleanup_logs", "query": "latest AI papers"},
    }
    action = Action(
        action_type="hand_researcher",
        params={"task": smuggled_task},
        proposed_by="hands_runner",
    )

    captured_tasks: list[dict] = []

    async def _spy_dispatch(self, task):
        captured_tasks.append(task)
        return {"status": "ok"}

    with patch("core.city.governor.Governor.dispatch", new=_spy_dispatch):
        result = await gw.execute(action)

    assert result.approved and result.executed
    assert captured_tasks, "expected Governor.dispatch() to have been called"
    forwarded_district = captured_tasks[0].get("district")
    assert forwarded_district == "research", (
        f"the caller-supplied district='ops' must be overwritten with the "
        f"real, server-owned district for hand_researcher -- got "
        f"{forwarded_district!r}"
    )


@pytest.mark.asyncio
async def test_hand_metadata_lookup_failure_fails_closed(isolated_vector_db, monkeypatch):
    """Round 5 (independent review finding -- HIGH): the original code
    caught any exception resolving Hand metadata (import error, registry
    lookup failure) and silently fell back to trusting the bare hand name
    as the expected task_type -- fail-OPEN. Fixed: a lookup failure now
    refuses the dispatch outright, same as a real type mismatch."""
    import hands.registry as _registry

    monkeypatch.setattr(_registry, "get_hand", lambda name: None)

    gw = PermissionGateway()
    action = Action(
        action_type="hand_researcher",
        params={"task": {"type": "deep_research", "params": {"query": "x"}}},
        proposed_by="hands_runner",
    )

    captured_tasks: list[dict] = []

    async def _spy_dispatch(self, task):
        captured_tasks.append(task)
        return {"status": "ok"}

    with patch("core.city.governor.Governor.dispatch", new=_spy_dispatch):
        result = await gw.execute(action)

    assert result.result.get("status") == "blocked", (
        f"a Hand metadata lookup failure must fail closed, not fall back "
        f"to trusting the bare hand name -- got {result.result!r}"
    )
    assert not captured_tasks, (
        "Governor.dispatch() must never be reached when Hand metadata "
        "cannot be resolved"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
