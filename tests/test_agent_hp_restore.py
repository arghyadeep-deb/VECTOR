"""
Regression tests for the 2026-08-04 agent-HP restore fix.

Audit finding: VECTOR's headline architectural claim is a Darwinian agent
city (HP 0-1000, earned from real outcomes, death at 0, ghost inheritance).
The project's own Critical Rule #4 says "HP system must be wired to real
task outcomes — fake HP = fake evolution."

Measured in production: over a 4d17h run agents saturated at the 1000 cap
(1,098 award events vs 4 deducts, 0 deaths). Immediately after a restart,
the live API reported every agent back at exactly 500 — the hardcoded birth
default in AgentBase.__init__.

Root cause was NOT "no persistence exists". `restore_agent_hp()` existed and
was called from the autonomous loop — but it matched snapshot entries on
`agent.id`, while 129 of the 201 district agent files construct themselves
with `str(uuid.uuid4())`, a fresh random UUID every process start. So the
saved ids could never match live ids, `restored` stayed 0, and because the
success log was gated behind `if restored:` the no-op was completely
invisible.

The fix matches on the STABLE identity (district, name) — which the snapshot
already stored — with exact-id matching kept as a first pass.

These tests pin the behaviour so it cannot silently regress to a no-op again.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loop.loop_state import restore_agent_hp  # noqa: E402


class _FakeAgent:
    """Minimal stand-in with the attributes restore_agent_hp touches."""

    def __init__(self, agent_id, name, district, health_points=500):
        self.id = agent_id
        self.name = name
        self.district = district
        self.health_points = health_points


class _FakeRegistry:
    def __init__(self, agents):
        self._agents = agents

    def get_all_agents(self):
        return list(self._agents)


def _snapshot(agents):
    """Build the same shape save_agent_hp() persists."""
    return {
        a.id: {"name": a.name, "district": a.district, "hp": a.health_points}
        for a in agents
    }


def test_restore_matches_on_stable_identity_across_fresh_uuids(monkeypatch):
    """THE regression test: new random UUIDs must still restore.

    Simulates a real restart — same agents by (district, name), completely
    different `id` values, exactly as uuid.uuid4() produces.
    """
    before = [
        _FakeAgent("uuid-old-1", "SEOSpecialist", "marketing", 1000),
        _FakeAgent("uuid-old-2", "HindiCoach", "languages", 780),
    ]
    snap = _snapshot(before)

    # Restart: same agents, brand-new ids, back at the 500 birth default.
    after = [
        _FakeAgent("uuid-NEW-a", "SEOSpecialist", "marketing", 500),
        _FakeAgent("uuid-NEW-b", "HindiCoach", "languages", 500),
    ]

    monkeypatch.setattr("core.loop.loop_state.load_agent_hp", lambda: snap)
    restored = restore_agent_hp(_FakeRegistry(after))

    assert restored == 2, "both agents must restore despite new UUIDs"
    assert after[0].health_points == 1000
    assert after[1].health_points == 780


def test_restore_still_works_on_exact_id_match(monkeypatch):
    """Agents that DO keep a stable id must keep working (no regression)."""
    agents = [_FakeAgent("stable-id-1", "ChiefOfStaff", "chief_of_staff", 500)]
    snap = {"stable-id-1": {"name": "ChiefOfStaff", "district": "chief_of_staff", "hp": 900}}

    monkeypatch.setattr("core.loop.loop_state.load_agent_hp", lambda: snap)
    assert restore_agent_hp(_FakeRegistry(agents)) == 1
    assert agents[0].health_points == 900


def test_unknown_agent_in_snapshot_is_skipped(monkeypatch):
    """A snapshot entry with no live counterpart must not crash or misapply."""
    agents = [_FakeAgent("new-1", "HindiCoach", "languages", 500)]
    snap = {
        "old-1": {"name": "HindiCoach", "district": "languages", "hp": 700},
        "old-2": {"name": "DeletedAgent", "district": "nowhere", "hp": 999},
    }

    monkeypatch.setattr("core.loop.loop_state.load_agent_hp", lambda: snap)
    assert restore_agent_hp(_FakeRegistry(agents)) == 1
    assert agents[0].health_points == 700


def test_two_snapshot_rows_cannot_both_claim_one_agent(monkeypatch):
    """Duplicate identities must not double-apply to the same live agent."""
    agents = [_FakeAgent("new-1", "HindiCoach", "languages", 500)]
    snap = {
        "old-1": {"name": "HindiCoach", "district": "languages", "hp": 700},
        "old-2": {"name": "HindiCoach", "district": "languages", "hp": 300},
    }

    monkeypatch.setattr("core.loop.loop_state.load_agent_hp", lambda: snap)
    assert restore_agent_hp(_FakeRegistry(agents)) == 1


def test_no_snapshot_returns_zero(monkeypatch):
    monkeypatch.setattr("core.loop.loop_state.load_agent_hp", lambda: None)
    assert restore_agent_hp(_FakeRegistry([_FakeAgent("a", "X", "d")])) == 0


def test_malformed_snapshot_entry_is_skipped(monkeypatch):
    """A row missing 'hp' must be skipped, not raise."""
    agents = [_FakeAgent("new-1", "HindiCoach", "languages", 500)]
    snap = {"old-1": {"name": "HindiCoach", "district": "languages"}}  # no hp

    monkeypatch.setattr("core.loop.loop_state.load_agent_hp", lambda: snap)
    assert restore_agent_hp(_FakeRegistry(agents)) == 0
    assert agents[0].health_points == 500
