"""Regression guard: skill execution in _act_on must pass the PermissionGateway.

Security fix 2026-06-21 (audit finding): the Phase-3B skill path called
sm.execute() directly whenever a skill matched with confidence > 0.6, bypassing
the gateway entirely — FORBIDDEN/RED were never enforced, violating RULE 3
("LLM has zero direct access. EVER."). These tests fail if that gate is removed.

Source-level guard (the convention used by scripts/integration_check.py): a full
behavioral test of _act_on would have to mock red-team review, the event bus,
the governor and episodic memory — fragile, and DB-touching while the soak runs.
This asserts the security-relevant structure instead.
"""
import inspect

from core.loop.autonomous_loop import AutonomousLoop


def _skill_region(src: str) -> str:
    start = src.index("Phase 3B: check VectorCode Skills")
    # rindex, not index: a 2026-09-16 comment (RR-3.1) mentions the literal
    # string "if not _skill_executed:" while explaining a past bug, and that
    # comment sits BEFORE the real branch statement. The real code line --
    # the one that actually ends this region -- is the LAST occurrence.
    end = src.rindex("if not _skill_executed:", start)
    return src[start:end]


def test_skill_path_consults_gateway():
    region = _skill_region(inspect.getsource(AutonomousLoop._act_on))
    assert ".classify(" in region, "skill path no longer classifies via the gateway"
    assert "FORBIDDEN" in region, "skill path no longer blocks FORBIDDEN actions"
    assert "_skill_allowed" in region, "skill path missing the _skill_allowed gate"


def test_gate_precedes_skill_execution():
    region = _skill_region(inspect.getsource(AutonomousLoop._act_on))
    assert region.index("_skill_allowed") < region.index("sm.execute(skill.name"), (
        "sm.execute runs before the gateway gate — bypass reintroduced"
    )


def test_skill_execute_guarded_by_allowed_flag():
    region = _skill_region(inspect.getsource(AutonomousLoop._act_on))
    preceding = region[: region.index("sm.execute(skill.name")]
    assert "if _skill_allowed:" in preceding, (
        "sm.execute is not guarded by the _skill_allowed gate"
    )


# ---------------------------------------------------------------------------
# Behavioral tests — VECTOR_TECHNICAL_KNOWLEDGE/53_PERMISSION_BOUNDARY_
# INTEGRITY.md Finding 2.
#
# The static guards above (pre-existing) only prove the skill path
# classifies via the gateway and blocks FORBIDDEN. They do not prove WHICH
# tiers actually reach gw.execute() at runtime — and until this fix, only
# RED did: a YELLOW-classified action_type matched to a skill silently got
# GREEN (no-confirmation) treatment, since the code only checked
# `if _level == "RED":`. The fix widened that to
# `if _level in ("RED", "YELLOW"):`, reusing gw.execute()'s own existing
# YELLOW semantics (trust ladder / owner-confirmation) rather than adding
# new logic. These tests drive the REAL AutonomousLoop._act_on() end to
# end (only the gateway and SkillManager are mocked) to prove it behaviorally.
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import MagicMock

import pytest


class _FakeGatewayResult:
    def __init__(self, approved: bool, reason: str = ""):
        self.approved = approved
        self.reason = reason


class _FakeGateway:
    """Stands in for PermissionGateway: classify() is synchronous and
    real-shaped (GREEN/YELLOW/RED/FORBIDDEN), execute() is the one thing
    under test — whether it gets called at all, and for which tiers."""

    def __init__(self, level: str, approved: bool = True):
        self._level = level
        self._approved = approved
        self.execute_calls: list[str] = []

    def classify(self, action_type: str) -> str:
        return self._level

    async def execute(self, action):
        self.execute_calls.append(action.action_type)
        return _FakeGatewayResult(self._approved)


def _make_loop_with_stubbed_skill(monkeypatch, matched_skill, skill_result):
    """A bare AutonomousLoop with just enough stubbed out that _act_on can
    reach and execute the skill-matching block without touching real
    infrastructure (episodic memory, red-team LLM calls, event bus, etc.)."""
    loop = AutonomousLoop()

    async def _noop_publish(*a, **kw):
        return None
    monkeypatch.setattr(loop, "_publish_event", _noop_publish)

    monkeypatch.setattr(loop, "_scan_threats", lambda *a, **kw: False)

    from vectorcode.src.skills.manager import SkillManager
    monkeypatch.setattr(
        SkillManager, "match",
        lambda self, *a, **kw: [matched_skill] if matched_skill else [],
    )
    monkeypatch.setattr(
        SkillManager, "execute",
        lambda self, name, context=None: skill_result,
    )

    # Everything past the skill block (reward/policy/goal bookkeeping) is
    # individually try/except-wrapped in the real _act_on — matching the
    # established pattern in test_phase_a3_counterfactual_act_on.py, no
    # further stubbing is required for it to run without raising.
    return loop


def test_yellow_skill_action_reaches_gateway_execute(monkeypatch):
    """A. Before this fix, YELLOW never reached gw.execute() in this path —
    only classify() was consulted. Confirm execute() is now actually called
    for a YELLOW-classified, skill-matched action."""
    from vectorcode.src.skills.types import MatchedSkill

    matched = MatchedSkill(name="test-skill", confidence=0.9)
    skill_result = MagicMock(status="ok")
    loop = _make_loop_with_stubbed_skill(monkeypatch, matched, skill_result)

    fake_gw = _FakeGateway(level="YELLOW", approved=True)
    monkeypatch.setattr(loop, "_get_gateway", lambda: fake_gw)

    from core.loop.decision_engine import Candidate
    candidate = Candidate(action_type="commit_code", params={}, goal_ids=[])

    asyncio.run(loop._act_on(candidate))

    assert fake_gw.execute_calls == ["commit_code"], (
        f"YELLOW skill-matched action must call gw.execute() — got calls: {fake_gw.execute_calls}"
    )


def test_yellow_skill_denied_does_not_execute_skill(monkeypatch):
    """Permission denial must actually prevent execution for YELLOW too,
    not just RED — sm.execute() must not run when the gateway denies."""
    from vectorcode.src.skills.types import MatchedSkill

    matched = MatchedSkill(name="test-skill", confidence=0.9)
    skill_result = MagicMock(status="ok")
    loop = _make_loop_with_stubbed_skill(monkeypatch, matched, skill_result)

    fake_gw = _FakeGateway(level="YELLOW", approved=False)
    monkeypatch.setattr(loop, "_get_gateway", lambda: fake_gw)

    from vectorcode.src.skills.manager import SkillManager
    execute_calls = []
    monkeypatch.setattr(
        SkillManager, "execute",
        lambda self, name, context=None: execute_calls.append(name) or skill_result,
    )

    from core.loop.decision_engine import Candidate
    candidate = Candidate(action_type="commit_code", params={}, goal_ids=[])

    asyncio.run(loop._act_on(candidate))

    assert fake_gw.execute_calls == ["commit_code"]
    assert execute_calls == [], (
        "sm.execute() ran even though the YELLOW gate denied the action"
    )


def test_green_skill_action_does_not_require_gateway_execute(monkeypatch):
    """GREEN must keep its existing low-friction behavior — this fix must
    not add a gate to harmless auto-execute actions. gw.execute() should
    never be called for a GREEN-classified skill match."""
    from vectorcode.src.skills.types import MatchedSkill

    matched = MatchedSkill(name="test-skill", confidence=0.9)
    skill_result = MagicMock(status="ok")
    loop = _make_loop_with_stubbed_skill(monkeypatch, matched, skill_result)

    fake_gw = _FakeGateway(level="GREEN", approved=True)
    monkeypatch.setattr(loop, "_get_gateway", lambda: fake_gw)

    from core.loop.decision_engine import Candidate
    candidate = Candidate(action_type="search_web", params={}, goal_ids=[])

    asyncio.run(loop._act_on(candidate))

    assert fake_gw.execute_calls == [], (
        f"GREEN skill-matched action must NOT call gw.execute() — got calls: {fake_gw.execute_calls}"
    )


def test_forbidden_skill_action_still_blocked(monkeypatch):
    """Regression guard alongside the new YELLOW behavior: FORBIDDEN must
    still short-circuit before either gw.execute() or sm.execute()."""
    from vectorcode.src.skills.types import MatchedSkill

    matched = MatchedSkill(name="test-skill", confidence=0.9)
    skill_result = MagicMock(status="ok")
    loop = _make_loop_with_stubbed_skill(monkeypatch, matched, skill_result)

    fake_gw = _FakeGateway(level="FORBIDDEN", approved=True)
    monkeypatch.setattr(loop, "_get_gateway", lambda: fake_gw)

    from vectorcode.src.skills.manager import SkillManager
    execute_calls = []
    monkeypatch.setattr(
        SkillManager, "execute",
        lambda self, name, context=None: execute_calls.append(name) or skill_result,
    )

    from core.loop.decision_engine import Candidate
    candidate = Candidate(action_type="format_drive", params={}, goal_ids=[])

    asyncio.run(loop._act_on(candidate))

    assert fake_gw.execute_calls == []
    assert execute_calls == []
