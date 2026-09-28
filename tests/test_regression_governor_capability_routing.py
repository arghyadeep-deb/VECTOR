"""
Regression tests for KNOWN_ISSUES.md #10 — Governor capability-match /
HP-lottery misroute.

Live-reproduced bug: typing "Remember that my favorite color is teal." into
the real HUD chat classified as an action but landed in `chief_of_staff`
(zero agents there declare a "remember"-shaped capability). `chief_of_staff`'s
highest-HP agent then just ran its own unrelated default action (a daily
brief) and returned it looking exactly as confident as a real answer.

Root cause, confirmed by reading core/city/governor.py:
1. `classify_chat_intent()` asks an LLM to invent a free-text `task_type`
   per request and only auto-corrected the LLM's guessed `district` when
   that invented string happened to equal a `DISTRICT_TASK_MAP` key
   *verbatim* — "save_preference" (a plausible LLM guess for "remember
   this") never equals the literal key "remember", even though the user's
   own words did.
2. `Governor.dispatch()` then picked a candidate agent via
   `max(capable or agents, key=HP)` — when no agent in the (possibly
   wrongly-guessed) district declared the task_type as a capability,
   `capable` was empty and it silently fell back to the single
   highest-HP agent in that district, regardless of whether that agent
   could plausibly do the job at all. That is the "HP lottery."

Fix (core/city/governor.py):
- `_authoritative_district_from_text()`: scans the RAW query text (not the
  LLM's invented task_type) for an unambiguous, literal match against
  DISTRICT_TASK_MAP's keys, wired into `classify_chat_intent()` before the
  existing exact-task_type-match correction. General, data-driven — no
  hardcoded "remember" string check; the same mechanism corrects any
  district whose trigger word appears unambiguously in the raw text.
- `Governor.dispatch()`: for LLM-classified chat actions
  (`task["_llm_classified"]`) only — established API routes keep their
  exact old behavior — candidate selection is now capability-first: if no
  agent in the resolved district is capable, search the WHOLE registry for
  one that is (HP breaks ties only among capable agents, never across all
  agents); if no agent anywhere is capable, return an honest
  `status: "no_capable_agent"` + `reason` instead of running the
  district's HP-lottery winner.
"""
import uuid

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.city.governor import (
    Governor,
    classify_chat_intent,
    _authoritative_district_from_text,
)
from core.city.agent_base import AgentBase
from core.city.agent_registry import get_registry


@pytest.fixture(autouse=True)
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


def make_agent(district, capabilities=None, hp=500):
    a = AgentBase(str(uuid.uuid4()), f"TestAgent_{district}_{uuid.uuid4().hex[:6]}", district)
    a.capabilities = capabilities or []
    a.health_points = hp
    get_registry().register(a)
    return a


class _FakeResult:
    def __init__(self, content):
        self.content = content


def _mock_llm_json(monkeypatch_target_content: str):
    """Patch core.inference.provider_client.get_client() so
    classify_chat_intent()'s single chat() call returns the given raw JSON
    string, exactly like a real (mocked) LLM classifier response."""
    fake_client = MagicMock()
    fake_client.chat = AsyncMock(return_value=_FakeResult(monkeypatch_target_content))
    return patch("core.inference.provider_client.get_client", return_value=fake_client)


# ---------------------------------------------------------------------------
# Part 1 — _authoritative_district_from_text() unit tests (pure function)
# ---------------------------------------------------------------------------

def test_authoritative_district_from_text_remember():
    result = _authoritative_district_from_text(
        "Remember that my favorite color is teal.", "chief_of_staff"
    )
    assert result == ("memory_curator", "remember")


def test_authoritative_district_from_text_recall():
    result = _authoritative_district_from_text(
        "Can you recall what I told you yesterday?", "chief_of_staff"
    )
    assert result == ("memory_curator", "recall")


def test_authoritative_district_from_text_no_conflict_returns_none():
    # LLM already guessed the district the text implies — nothing to correct.
    result = _authoritative_district_from_text(
        "Remember that my favorite color is teal.", "memory_curator"
    )
    assert result is None


def test_authoritative_district_from_text_ambiguous_returns_none():
    # "remember" (memory_curator) and "budget" (finance) disagree —
    # must NOT guess.
    result = _authoritative_district_from_text(
        "Remember to check my budget this week.", "chief_of_staff"
    )
    assert result is None


def test_authoritative_district_from_text_no_match_returns_none():
    result = _authoritative_district_from_text(
        "What is the weather like today?", "chief_of_staff"
    )
    assert result is None


# ---------------------------------------------------------------------------
# Part 2 — Verification requirement #1: classify_chat_intent() routes
# "Remember that ..." (and other districts' representative phrasings) to
# the CORRECT district, even when the LLM classifier itself guesses wrong.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remember_routes_to_memory_curator_despite_wrong_llm_guess():
    """The exact live-reproduced #10 repro: LLM invents a task_type that
    does NOT literally equal "remember" and guesses the wrong district
    (chief_of_staff) — the text-based correction must still land this on
    memory_curator with task_type "remember"."""
    llm_raw = (
        '{"is_action": true, "task_type": "save_preference", '
        '"district": "chief_of_staff", "confidence": 0.9}'
    )
    with _mock_llm_json(llm_raw):
        result = await classify_chat_intent("Remember that my favorite color is teal.")
    assert result["district"] == "memory_curator"
    assert result["type"] == "remember"


@pytest.mark.asyncio
async def test_languages_routes_correctly_despite_wrong_llm_guess():
    """Representative phrasing for the 'languages' district — LLM guesses
    'learning' (a genuinely confusable neighbor per this file's own
    _DISTRICT_DISAMBIGUATION_HINTS), text correction must fix it."""
    llm_raw = (
        '{"is_action": true, "task_type": "quiz_vocabulary", '
        '"district": "learning", "confidence": 0.9}'
    )
    with _mock_llm_json(llm_raw):
        result = await classify_chat_intent("Quiz me on some Hindi vocabulary")
    assert result["district"] == "languages"
    # The deterministic regex pre-classifier answers before the LLM; its
    # `quiz_vocabulary` matches data/golden_intent_dataset.jsonl.
    assert result["type"] == "quiz_vocabulary"


@pytest.mark.asyncio
async def test_news_trends_routes_correctly_despite_wrong_llm_guess():
    """Representative phrasing for the 'news_trends' district."""
    llm_raw = (
        '{"is_action": true, "task_type": "fetch_latest", '
        '"district": "research", "confidence": 0.9}'
    )
    with _mock_llm_json(llm_raw):
        result = await classify_chat_intent("Give me the latest AI news")
    assert result["district"] == "news_trends"
    assert result["type"] == "news"


# ---------------------------------------------------------------------------
# Part 3 — Verification requirement #2: the HP lottery is dead. A very
# high-HP agent that is NOT capable must lose to a lower-HP agent that IS
# capable, even across districts.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hp_lottery_dead_capable_agent_wins_across_districts():
    high_hp_noncapable = make_agent(
        "chief_of_staff", capabilities=["daily_brief", "morning_brief"], hp=950
    )
    low_hp_capable = make_agent(
        "memory_curator", capabilities=["remember", "recall"], hp=50
    )

    called = {}

    async def _noncapable_run(task):
        called["ran"] = "chief_of_staff_agent"
        return {"status": "ok", "response": "Here is your daily brief."}

    async def _capable_run(task):
        called["ran"] = "memory_curator_agent"
        return {"status": "ok", "response": "Noted: favorite color is teal."}

    high_hp_noncapable.run = _noncapable_run
    low_hp_capable.run = _capable_run

    # 2026-09-24: "remember" is now YELLOW-tier (real memory_curator write,
    # previously UNKNOWN-passthrough) -- Governor.dispatch() itself now
    # requires a real gateway-issued receipt for YELLOW/RED, closing the
    # authorization-boundary gap this session's work found. Real chat
    # traffic reaches this via PermissionGateway.execute() first
    # (core/api/routers/commands.py's classify_chat_intent() path), which
    # issues this receipt itself -- this test drives Governor.dispatch()
    # directly to isolate the HP-lottery fix, so it issues the same real
    # receipt PermissionGateway would, matching production behavior.
    from core.loop.permission_gateway import PermissionGateway
    PermissionGateway()._issue_approval_receipt("remember", purpose="governor_dispatch")

    gov = Governor()
    result = await gov.dispatch({
        "type": "remember",
        "district": "chief_of_staff",  # simulates the LLM's wrong guess
        "params": {"query": "my favorite color is teal"},
        "_llm_classified": True,
    })

    assert called.get("ran") == "memory_curator_agent", (
        f"expected the capable low-HP agent to win over the non-capable "
        f"high-HP agent, got: {called}"
    )
    assert result.get("district") == "memory_curator"


# ---------------------------------------------------------------------------
# Part 4 — Verification requirement #3: no capable agent anywhere ->
# honest refusal, not a silent misroute to the HP-lottery winner.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_capable_agent_returns_honest_refusal_not_hp_lottery():
    high_hp_noncapable = make_agent(
        "chief_of_staff", capabilities=["daily_brief"], hp=999
    )

    called = {}

    async def _noncapable_run(task):
        called["ran"] = True
        return {"status": "ok", "response": "Here is your daily brief."}

    high_hp_noncapable.run = _noncapable_run

    gov = Governor()
    result = await gov.dispatch({
        "type": "totally_uncovered_llm_invented_task_type_xyz",
        "district": "chief_of_staff",
        "params": {"query": "do something nobody can do"},
        "_llm_classified": True,
    })

    assert called.get("ran") is None, (
        "the non-capable HP-lottery winner must NOT have run"
    )
    assert result.get("status") == "no_capable_agent"
    assert "reason" in result
    assert "totally_uncovered_llm_invented_task_type_xyz" in result["reason"]


@pytest.mark.asyncio
async def test_undeclared_route_without_llm_marker_is_blocked():
    """Unknown caller-supplied routes cannot bypass capability checks by
    naming a district. This locks in the governor's dispatch hardening."""
    agent = make_agent("coding", capabilities=["unrelated"], hp=900)

    called = {}

    async def _run(task):
        called["ran"] = True
        return {"status": "ok"}

    agent.run = _run

    gov = Governor()
    result = await gov.dispatch({
        "type": "totally_uncovered_task_type_established_route",
        "district": "coding",
        "params": {},
        # deliberately no "_llm_classified" key
    })

    assert called.get("ran") is None
    assert result.get("status") == "blocked"
    assert "not a known task type" in result.get("reason", "")


if __name__ == "__main__":
    import sys
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_regression_governor_capability_routing" if ok else "FAIL")
    sys.exit(0 if ok else 1)
