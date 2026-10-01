"""Phase-3 audit: chief_of_staff silent suppression / false all-clear fixes."""
from __future__ import annotations

import asyncio
import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.chief_of_staff.chief_of_staff import ChiefOfStaff


class _Mem:
    def __init__(self, fail=False):
        self.fail = fail
        self.stored = []
        outer = self

        class _Conn:
            def cursor(self_inner):
                if outer.fail:
                    raise RuntimeError("db locked")
                raise RuntimeError("db locked")

        self.conn = _Conn()

    def store(self, **kw):
        self.stored.append(kw)

    def store_chain(self, **kw):
        pass

    def recall_fact(self, key):
        return None


class _Obs:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = 0

    def write_note(self, **kw):
        self.calls += 1
        if not self.ok:
            raise OSError("vault down")


def _cos(obs_ok=True):
    c = ChiefOfStaff.__new__(ChiefOfStaff)
    c.name = "ChiefOfStaff"
    c.health_points = 500
    c.points = []
    c.award_points = lambda n, why="": c.points.append((n, why))
    c.deduct_points = lambda n, why="": c.points.append((-n, why))
    c._memory = _Mem()
    c._obsidian = _Obs(obs_ok)
    c._context = SimpleNamespace(
        get_world_state=lambda: {}, session_hydration_prompt=lambda: "h"
    )
    c._call_chairman = lambda *a, **k: ""
    c._agent_hp_leaderboard = lambda: []
    c._goal_progress_summary = lambda: "g"
    c._kiit_today = lambda: "k"
    c._karpathy_streak = lambda: "s"
    return c


# ── filter_noise ──────────────────────────────────────────────────────────────

def test_json_encoded_tags_are_recognised():
    ev = {"event_type": "alert", "content": "x", "tags": '["security", "threat"]'}
    assert len(_cos().filter_noise([ev])) == 1


def test_security_scan_is_not_dropped_as_routine():
    evs = [
        {"event_type": "security_scan", "content": "malware found", "tags": '["security"]'},
        {"event_type": "heartbeat", "content": "CRITICAL disk full", "tags": ""},
        {"event_type": "deadline_sync", "content": "due tomorrow", "tags": ""},
    ]
    assert len(_cos().filter_noise(evs)) == 3


def test_unparseable_hp_drop_is_shown():
    ev = {"event_type": "hp_drop", "content": "agent lost lots", "tags": ""}
    assert _cos().filter_noise([ev]) == [ev]


def test_malformed_event_fails_toward_showing():
    class Bad:
        def __str__(self):
            raise ValueError("unparseable")

    c = _cos()
    out = c.filter_noise([{"event_type": "x", "content": "y", "tags": Bad()}])
    assert len(out) == 1  # classifier blew up -> surfaced, not hidden
    assert c.filter_noise(["garbage"]) == []  # non-dict no longer crashes


# ── failed data pull must not read as all-clear ──────────────────────────────

def test_failed_event_pull_flagged_in_executive_brief():
    c = _cos()
    c._fetch_events_since = ChiefOfStaff._fetch_events_since.__get__(c)
    res = asyncio.run(c.generate_executive_brief())
    assert res["events_unavailable"] is True
    assert "all-clear" in res["brief_text"].lower() or "unavailable" in res["brief_text"].lower()
    assert "No significant signals today" not in res["brief_text"]


def test_fallback_brief_lists_signals():
    c = _cos()
    c._fetch_events_since = lambda hours=24: [
        {"event_type": "security_alert", "content": "intruder at gate", "tags": "", "timestamp": "2026-10-01T01:00:00"}
    ]
    res = asyncio.run(c.generate_executive_brief())
    assert res["llm_ok"] is False
    assert "intruder at gate" in res["brief_text"]


def test_evening_pending_pull_failure_not_all_clear():
    c = _cos()
    c._fetch_events_since = lambda hours=16: []
    captured = {}

    def chair(sys_, prompt, timeout=0):
        captured["p"] = prompt
        return "recap"

    c._call_chairman = chair
    asyncio.run(c.evening_brief())
    assert "UNAVAILABLE" in captured["p"]
    assert "No pending tasks found" not in captured["p"]


# ── routing ───────────────────────────────────────────────────────────────────

def test_council_failure_not_reported_as_success(monkeypatch):
    import districts.governance.llm_council as lc

    class Boom:
        async def convene(self, **kw):
            raise RuntimeError("council down")

    monkeypatch.setattr(lc, "LLMCouncil", Boom)
    c = _cos()
    res = asyncio.run(c.route_escalation({"type": "zzz_unknown_thing_qq"}))
    assert res["escalation_ok"] is False
    assert "council down" in res["escalation_error"]
    assert "ESCALATION_FAILED" in c._memory.stored[-1]["content"]


def test_run_route_with_none_params():
    c = _cos()
    c.last_active = None
    called = {}

    async def fake_route(issue):
        called["issue"] = issue
        return {"routed_to": "governance"}

    c.route_escalation = fake_route
    out = asyncio.run(c.run({"type": "route", "params": None}))
    assert out["status"] == "ok" and called["issue"] == {}


def test_route_escalation_non_dict_issue():
    c = _cos()
    res = asyncio.run(c.route_escalation(None))
    assert res["issue_type"] == "unknown"


# ── dead district ─────────────────────────────────────────────────────────────

def test_all_dead_district_is_flagged(monkeypatch):
    import core.city.agent_registry as ar
    import core.city.evolution_engine as ee

    dead = SimpleNamespace(health_points=0)

    class Reg:
        def count_by_district(self):
            return {"coding": 1}

        def get_by_district(self, d):
            return [dead]

    class Eng:
        async def check_and_evolve(self, agents):
            return {"respawned": 1}

    monkeypatch.setattr(ar, "get_registry", lambda: Reg())
    monkeypatch.setattr(ee, "get_evolution_engine", lambda: Eng())
    res = asyncio.run(_cos().enforce_consistency())
    assert res["flagged_districts"] == ["coding"]


# ── subconscious failure not reported as ok/noop ─────────────────────────────

def test_subconscious_error_not_ok(monkeypatch):
    import districts.chief_of_staff.subconscious_loop as sl

    async def fake_once(self):
        return {"decision": "noop", "error": "boom"}

    monkeypatch.setattr(sl.SubconsciousLoop, "run_once", fake_once)
    monkeypatch.setattr(sl.SubconsciousLoop, "__init__", lambda self: None)
    c = _cos()
    out = asyncio.run(c.run_subconscious())
    assert out["status"] == "error"


def test_subconscious_empty_llm_reply_is_error(monkeypatch):
    import districts.chief_of_staff.subconscious_loop as sl
    import core.inference.provider_client as pc

    class Cli:
        async def complete(self, *a, **k):
            return SimpleNamespace(content="")

    monkeypatch.setattr(pc, "get_client", lambda: Cli())
    s = sl.SubconsciousLoop.__new__(sl.SubconsciousLoop)
    s._last_report = ""
    s._last_run = None
    s.award_points = lambda *a, **k: None
    s.deduct_points = lambda *a, **k: None
    out = asyncio.run(s.run_once())
    assert out.get("error")


# ── run_forever scheduling ────────────────────────────────────────────────────

def test_run_forever_sleeps_one_second_ticks_and_dedupes(monkeypatch):
    import districts.chief_of_staff.chief_of_staff as mod

    c = _cos()
    sleeps = []
    brief_calls = []

    async def fake_sleep(n):
        sleeps.append(n)
        if len(sleeps) >= 130:
            c.health_points = 0

    async def fake_morning():
        brief_calls.append("m")
        return {"obsidian_ok": True}

    async def noop():
        return {"obsidian_ok": True}

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 1, 8, 2, 0)

    c.morning_brief = fake_morning
    c.evening_brief = noop
    c.enforce_consistency = noop
    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(mod.datetime, "datetime", FakeDT)
    asyncio.run(c.run_forever())
    assert max(sleeps) <= 1
    assert brief_calls == ["m"]  # once per day, not once per tick


def test_run_forever_catches_up_and_retries_failed_delivery(monkeypatch):
    import districts.chief_of_staff.chief_of_staff as mod

    c = _cos()
    n = {"sleep": 0, "m": 0}

    async def fake_sleep(_):
        n["sleep"] += 1
        if n["sleep"] >= 60:
            c.health_points = 0

    async def failing_morning():
        n["m"] += 1
        return {"obsidian_ok": False}

    async def noop():
        return {"obsidian_ok": True}

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 1, 9, 30, 0)  # window missed; catch-up

    c.morning_brief = failing_morning
    c.evening_brief = noop
    c.enforce_consistency = noop
    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(mod.datetime, "datetime", FakeDT)
    asyncio.run(c.run_forever())
    assert n["m"] == 1  # attempted at 09:30 despite missed window; throttled retry
