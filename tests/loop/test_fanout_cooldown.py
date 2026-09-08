"""Tests for Task 89B — event fan-out cooldown/dedup.

Covers core/loop/autonomous_loop.py::_fanout_edge_should_fire() (the cooldown
primitive) and AutonomousLoop._fanout_handler() (its integration point), plus
a regression check on core/event_bus/wiring.py's EVENT_TRIGGER_MAP for the
one "strategy" edge retired in the same change.

Safety: governor.dispatch is mocked in every test. No real district agent
execution, no real external action, no real network/subprocess.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.event_bus.types import EventType


# ── Shared fixtures / helpers ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_fanout_cooldowns():
    """The cooldown store is a module-level dict — clear it before and after
    every test so tests never see state left behind by a previous test."""
    from core.loop import autonomous_loop
    autonomous_loop._fanout_edge_last_fired.clear()
    yield
    autonomous_loop._fanout_edge_last_fired.clear()


def _make_event(event_type: EventType):
    event = MagicMock()
    event.event_type = event_type
    event.data = {}
    return event


async def _run_fanout_collect(loop, event, governor_mock, registry_mock=None):
    """Run AutonomousLoop._fanout_handler with governor + agent registry
    mocked, and with asyncio.create_task intercepted so the fire-and-forget
    governor.dispatch(...) coroutines it schedules are awaited (and any
    exception swallowed) synchronously inside the test instead of leaking
    into the event loop as unretrieved-exception warnings.
    """
    if registry_mock is None:
        registry_mock = MagicMock()
        registry_mock.get_all_agents.return_value = []

    created = []

    def _fake_create_task(coro, *a, **kw):
        created.append(coro)
        return MagicMock()

    with patch("core.city.agent_registry.get_registry", return_value=registry_mock), \
         patch.object(loop, "_get_governor", return_value=governor_mock), \
         patch("core.loop.autonomous_loop.asyncio.create_task", side_effect=_fake_create_task):
        await loop._fanout_handler(event)

    for coro in created:
        try:
            await coro
        except Exception:
            pass


# ── Unit tests: the cooldown primitive itself ───────────────────────────────

class TestFanoutEdgeShouldFire:
    def test_first_event_on_edge_fires(self):
        from core.loop.autonomous_loop import _fanout_edge_should_fire
        edge = ("marketing_published", "data_analytics", "analyze_campaign_metrics")
        assert _fanout_edge_should_fire(edge) is True

    def test_duplicate_within_cooldown_window_dropped(self):
        from core.loop.autonomous_loop import _fanout_edge_should_fire
        edge = ("marketing_published", "data_analytics", "analyze_campaign_metrics")
        assert _fanout_edge_should_fire(edge) is True
        assert _fanout_edge_should_fire(edge) is False

    def test_fires_again_after_cooldown_elapses(self, monkeypatch):
        from core.loop import autonomous_loop
        edge = ("marketing_published", "data_analytics", "analyze_campaign_metrics")
        clock = [1_000_000.0]
        monkeypatch.setattr(autonomous_loop.time, "monotonic", lambda: clock[0])
        assert autonomous_loop._fanout_edge_should_fire(edge) is True
        clock[0] += autonomous_loop._FANOUT_EDGE_COOLDOWN_SEC + 0.5
        assert autonomous_loop._fanout_edge_should_fire(edge) is True

    def test_different_edges_have_independent_cooldowns(self):
        from core.loop.autonomous_loop import _fanout_edge_should_fire
        edge_a = ("marketing_published", "data_analytics", "analyze_campaign_metrics")
        edge_b = ("marketing_published", "intelligence", "track_campaign_performance")
        assert _fanout_edge_should_fire(edge_a) is True
        # a different edge is unaffected by edge_a's freshly-started cooldown
        assert _fanout_edge_should_fire(edge_b) is True
        # but each edge is now independently cooling down
        assert _fanout_edge_should_fire(edge_a) is False
        assert _fanout_edge_should_fire(edge_b) is False

    def test_restart_resets_cooldowns(self):
        from core.loop import autonomous_loop
        edge = ("marketing_published", "data_analytics", "analyze_campaign_metrics")
        assert autonomous_loop._fanout_edge_should_fire(edge) is True
        assert autonomous_loop._fanout_edge_should_fire(edge) is False
        # simulate a process restart: a fresh, empty cooldown dict
        autonomous_loop._fanout_edge_last_fired.clear()
        assert autonomous_loop._fanout_edge_should_fire(edge) is True


# ── Integration tests: through AutonomousLoop._fanout_handler ──────────────

class TestFanoutHandlerCooldown:
    @pytest.mark.asyncio
    async def test_first_dispatch_fires(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})
        event = _make_event(EventType.CONTENT_REVIEWED)  # single downstream edge

        await _run_fanout_collect(loop, event, governor)

        assert governor.dispatch.call_count == 1

    @pytest.mark.asyncio
    async def test_duplicate_event_inside_window_dropped(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1  # NOT called a second time

    @pytest.mark.asyncio
    async def test_fires_again_after_cooldown_elapses(self, monkeypatch):
        from core.loop import autonomous_loop
        loop = autonomous_loop.AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})

        clock = [2_000_000.0]
        monkeypatch.setattr(autonomous_loop.time, "monotonic", lambda: clock[0])

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1

        clock[0] += autonomous_loop._FANOUT_EDGE_COOLDOWN_SEC + 1.0
        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_failed_dispatch_still_consumes_cooldown(self):
        """B4: cooldown starts on ACCEPT, before the result is known — a
        dispatch that raises must still block a duplicate inside the window."""
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(side_effect=RuntimeError("simulated dispatch failure"))

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1  # still dropped despite the failure

    @pytest.mark.asyncio
    async def test_no_agents_result_still_consumes_cooldown(self):
        """B4: a 'no_agents' outcome (e.g. today's dead strategy edge, or any
        district with zero registered agents) must consume the cooldown
        exactly like a successful dispatch — no special-casing."""
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "no_agents", "district": "content"})

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1  # still dropped

    @pytest.mark.asyncio
    async def test_two_different_edges_from_same_event_are_independent(self):
        """MARKETING_PUBLISHED fans out to two distinct districts; both edges
        must fire on the first event and both must be independently tracked."""
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})

        await _run_fanout_collect(loop, _make_event(EventType.MARKETING_PUBLISHED), governor)

        assert governor.dispatch.call_count == 2
        districts = {c.args[0]["district"] for c in governor.dispatch.call_args_list}
        assert districts == {"intelligence", "data_analytics"}

    @pytest.mark.asyncio
    async def test_restart_via_fresh_instance_resets_cooldown(self):
        """A fresh AutonomousLoop + fresh module cooldown dict (simulating a
        process restart) must not inherit an in-window cooldown."""
        from core.loop import autonomous_loop
        loop1 = autonomous_loop.AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})

        await _run_fanout_collect(loop1, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1

        # simulate restart: clear the (module-level, in-process-only) cooldown
        # store and construct a brand new loop instance
        autonomous_loop._fanout_edge_last_fired.clear()
        loop2 = autonomous_loop.AutonomousLoop()

        await _run_fanout_collect(loop2, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 2  # fired immediately post-restart

    @pytest.mark.asyncio
    async def test_event_type_not_in_trigger_map_dispatches_nothing(self):
        """Unchanged prior behavior: an event with no EVENT_TRIGGER_MAP entry
        produces zero downstream dispatches, cooldown gate or not."""
        from core.loop.autonomous_loop import AutonomousLoop
        from core.event_bus.wiring import get_downstream_tasks
        assert get_downstream_tasks(EventType.TASK_SCHEDULED) == []

        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})

        await _run_fanout_collect(loop, _make_event(EventType.TASK_SCHEDULED), governor)

        assert governor.dispatch.call_count == 0

    @pytest.mark.asyncio
    async def test_cooldown_gate_does_not_alter_governor_dispatch_call(self):
        """The cooldown gate only decides WHETHER governor.dispatch() is
        called — never mutates the task payload. Compare the exact dict the
        fan-out handler passes against the dict get_downstream_tasks() +
        the same param-formatting logic would produce completely outside
        the cooldown gate (i.e. Governor.dispatch's own routing/inputs are
        unaffected by whether the cooldown gate sits in front of it)."""
        from core.loop.autonomous_loop import AutonomousLoop
        from core.event_bus.wiring import get_downstream_tasks
        loop = AutonomousLoop()
        governor = MagicMock()
        governor.dispatch = AsyncMock(return_value={"status": "ok"})

        await _run_fanout_collect(loop, _make_event(EventType.CONTENT_REVIEWED), governor)
        assert governor.dispatch.call_count == 1
        called_task = governor.dispatch.call_args.args[0]

        # Reconstruct the task exactly as _fanout_handler would, with no
        # cooldown gate involved at all.
        district, task_type, params_template = get_downstream_tasks(EventType.CONTENT_REVIEWED)[0]
        et = EventType.CONTENT_REVIEWED.value
        expected_params = {
            k: v.format(event_type=et, event_data="{}")
            for k, v in params_template.items()
        }
        expected_task = {
            "type": task_type,
            "district": district,
            "params": expected_params,
            "source_event": et,
        }

        assert called_task == expected_task


# ── Regression: EVENT_TRIGGER_MAP edge set unchanged except the retired one ─

# Snapshot of every (event_type, district, task_type) edge as it existed in
# EVENT_TRIGGER_MAP BEFORE Task 89B's B6 change (retiring the dead
# "strategy" edge under ANALYTICS_READY). Recorded by reading wiring.py
# directly before editing it.
_BASELINE_EDGES: set[tuple[EventType, str, str]] = {
    (EventType.DESIGN_COMPLETE, "coding", "implement_design"),
    (EventType.DESIGN_COMPLETE, "content", "plan_content_from_design"),
    (EventType.CONTENT_READY, "marketing", "distribute_content"),
    (EventType.CONTENT_READY, "qa", "review_content"),
    (EventType.CODING_COMPLETE, "qa", "test_feature"),
    (EventType.CODING_COMPLETE, "documentation", "document_feature"),
    (EventType.CONTENT_REVIEWED, "content", "update_content_from_review"),
    (EventType.RESEARCH_COMPLETE, "content", "create_content_from_research"),
    (EventType.RESEARCH_COMPLETE, "intelligence", "analyze_research_findings"),
    (EventType.RESEARCH_COMPLETE, "investment", "evaluate_research_opportunities"),
    (EventType.SECURITY_ALERT, "emergency", "respond_to_security_threat"),
    (EventType.SECURITY_ALERT, "governance", "review_security_incident"),
    (EventType.EMERGENCY_SIGNAL, "health", "check_user_safety"),
    (EventType.EMERGENCY_SIGNAL, "security", "lockdown_systems"),
    (EventType.HEALTH_ALERT, "emergency", "assess_health_crisis"),
    (EventType.HEALTH_ALERT, "predictive_analytics", "update_health_forecast"),
    (EventType.MARKETING_PUBLISHED, "intelligence", "track_campaign_performance"),
    (EventType.MARKETING_PUBLISHED, "data_analytics", "analyze_campaign_metrics"),
    (EventType.ANALYTICS_READY, "strategy", "review_analytics_insights"),
    (EventType.ANALYTICS_READY, "content", "optimize_from_analytics"),
    (EventType.ANALYTICS_READY, "marketing", "adjust_campaign_from_analytics"),
    (EventType.SYSTEM_ERROR, "emergency", "diagnose_system_error"),
    (EventType.SYSTEM_ERROR, "security", "investigate_error_source"),
}

# Edges this change is explicitly allowed to have removed. Empty set would
# mean "wiring.py should be byte-for-byte identical to baseline"; here we
# allow exactly the one confirmed-dead strategy edge (see 89B_EVENT_FANOUT.md
# for the verification evidence).
_ALLOWED_RETIRED_EDGES: set[tuple[EventType, str, str]] = {
    (EventType.ANALYTICS_READY, "strategy", "review_analytics_insights"),
}


def test_event_trigger_map_edges_unchanged_except_retired_strategy_edge():
    from core.event_bus.wiring import EVENT_TRIGGER_MAP

    current_edges = {
        (event_type, district, task_type)
        for event_type, entries in EVENT_TRIGGER_MAP.items()
        for (district, task_type, _params) in entries
    }

    new_edges = current_edges - _BASELINE_EDGES
    missing_edges = _BASELINE_EDGES - current_edges

    assert new_edges == set(), f"unexpected new edge(s) introduced: {new_edges}"
    assert missing_edges <= _ALLOWED_RETIRED_EDGES, (
        f"unexpected missing edge(s) beyond the allowed retirement: "
        f"{missing_edges - _ALLOWED_RETIRED_EDGES}"
    )


if __name__ == "__main__":
    import sys
    result = pytest.main([__file__, "-v"])
    print("✅ test_fanout_cooldown OK" if result == 0 else "❌ FAILED")
    sys.exit(result)
