"""Task 1.1-1.3 of plans/wire-absorbed-repos-autonomy.md — Hand Execution
Engine: HandResult persistence, HandRunner dispatch, and the closed
result→memory→HP→policy feedback loop.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    import core.memory.episodic as ep
    ep.close_db_connection()
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "hands_test.db"))
    yield ep
    try:
        ep.close_db_connection()
    except Exception:
        pass


def test_hand_result_persists(isolated_db):
    from hands.result import HandResult
    r = HandResult(hand="researcher", district="research", output="body", status="ok", hp_delta=50)
    assert r.persist() > 0
    assert r.to_dict()["status"] == "ok"


def test_hand_result_to_dict_has_all_fields(isolated_db):
    from hands.result import HandResult
    r = HandResult(hand="trader", district="investment", output="x", status="error", hp_delta=-30, error="boom")
    d = r.to_dict()
    assert d["hand"] == "trader"
    assert d["district"] == "investment"
    assert d["status"] == "error"
    assert d["hp_delta"] == -30
    assert d["error"] == "boom"


def test_run_hand_plumbing(monkeypatch, isolated_db):
    from hands.runner import HandRunner
    from hands.registry import HandRegistry
    runner = HandRunner()
    monkeypatch.setattr(runner, "_dispatch", lambda h, c: "stub")
    r = asyncio.run(runner.run_hand(HandRegistry().get("researcher"), {}))
    assert r.status == "ok" and r.output


def test_run_hand_never_raises_on_dispatch_failure(monkeypatch, isolated_db):
    from hands.runner import HandRunner
    from hands.registry import HandRegistry

    async def _boom(h, c):
        raise RuntimeError("dispatch exploded")

    runner = HandRunner()
    monkeypatch.setattr(runner, "_dispatch", _boom)
    r = asyncio.run(runner.run_hand(HandRegistry().get("researcher"), {}))
    assert r.status == "error"
    assert "dispatch exploded" in (r.error or "")


def test_alert_status_propagates_from_dispatch_output(monkeypatch, isolated_db):
    """Task 3.1: a district agent can signal status='alert' through its own
    return dict (e.g. collector finding a HIGH-significance OSINT change),
    and HandResult must carry that through instead of always hardcoding
    'ok' on any non-exception dispatch."""
    from hands.runner import HandRunner
    from hands.registry import HandRegistry

    runner = HandRunner()
    runner._dispatch = lambda h, c: {"status": "alert", "summary": "something significant happened"}
    r = asyncio.run(runner.run_hand(HandRegistry().get("collector"), {}))
    assert r.status == "alert"


def test_alert_and_error_results_notify_pushover_not_routine_success(monkeypatch, isolated_db):
    """High-signal results (alert/error) page the owner; routine successes
    do not — paging on every ordinary +50 success would be spam, defeating
    the point of 'high-signal' filtering."""
    from hands.runner import HandRunner
    from hands.registry import HandRegistry

    notified = []

    async def _fake_notify(message, priority=0):
        notified.append((message, priority))

    monkeypatch.setattr("core.loop.permission_gateway.PermissionGateway.notify", _fake_notify)

    runner = HandRunner()
    hand = HandRegistry().get("vault_sync")

    runner._dispatch = lambda h, c: "routine, nothing to report"
    asyncio.run(runner.run_hand(hand, {}))
    assert notified == [], "routine success must not page"

    runner._dispatch = lambda h, c: {"status": "alert", "summary": "exposure found"}
    asyncio.run(runner.run_hand(hand, {}))
    assert len(notified) == 1
    assert "vault_sync" in notified[0][0]

    async def _boom(h, c):
        raise RuntimeError("dispatch exploded")
    runner._dispatch = _boom
    asyncio.run(runner.run_hand(hand, {}))
    assert len(notified) == 2


def test_closed_feedback_loop_calls_each_once(monkeypatch, isolated_db):
    from hands.runner import HandRunner
    from hands.registry import HandRegistry

    runner = HandRunner()
    monkeypatch.setattr(runner, "_dispatch", lambda h, c: "stub output")

    calls = {"episodic": 0, "hp": 0, "policy": 0}
    monkeypatch.setattr(runner, "_record_episodic", lambda *a, **kw: calls.__setitem__("episodic", calls["episodic"] + 1))
    monkeypatch.setattr(runner, "_award_hp", lambda *a, **kw: calls.__setitem__("hp", calls["hp"] + 1))
    monkeypatch.setattr(runner, "_update_policy", lambda *a, **kw: calls.__setitem__("policy", calls["policy"] + 1))

    asyncio.run(runner.run_hand(HandRegistry().get("researcher"), {}))

    assert calls["episodic"] == 1
    assert calls["hp"] == 1
    assert calls["policy"] == 1


if __name__ == "__main__":
    print("✅ test_hand_runner.py module loads")
