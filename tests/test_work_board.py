"""The work board: practice drills for idle agents. Real GitBot, real git as ground truth, real bus/Governor/ledger."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import core.city.a2a_bus as bus_mod
import core.city.agent_registry as registry_mod
from core.city import experience as xp
from core.city import work_board as wb
from core.city.a2a_bus import A2ABus
from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry
from districts.coding.git_bot import GitBot


class Plain(AgentBase):
    async def run(self, task):
        return {"status": "ok"}


@pytest.fixture
def board(isolated_vector_db, monkeypatch):
    monkeypatch.delenv("VECTOR_GYM", raising=False)
    monkeypatch.delenv("VECTOR_GYM_LLM", raising=False)
    xp._reset_for_tests()
    original = registry_mod._registry_singleton
    reg = AgentRegistry()
    registry_mod._registry_singleton = reg
    bus = A2ABus(registry=reg)
    old_bus, bus_mod._BUS = bus_mod._BUS, bus
    git = GitBot()
    reg.register(git)
    plain = Plain(agent_id="id-plain", name="Plain", district="misc")
    reg.register(plain)
    monkeypatch.setattr(wb.WorkBoard, "_owner_busy", staticmethod(lambda: False))
    yield SimpleBoard(wb.WorkBoard(bus=bus, registry=reg), reg, git, plain)
    registry_mod._registry_singleton = original
    bus_mod._BUS = old_bus
    xp._reset_for_tests()


class SimpleBoard:
    def __init__(self, b, reg, git, plain):
        self.b, self.reg, self.git, self.plain = b, reg, git, plain


@pytest.mark.asyncio
async def test_off_by_default_and_does_nothing(board):
    out = await board.b.run_cycle()
    assert out["ran"] == [] and "VECTOR_GYM is off" in out["skipped"]


@pytest.mark.asyncio
async def test_a_drill_is_verified_against_git_itself_earns_reduced_xp_and_moves_no_hp(board):
    hp = board.git.health_points
    out = await board.b.run_cycle(force=True)
    assert [r["agent"] for r in out["ran"]] == ["GitBot"] and out["ran"][0]["passed"] is True
    assert board.git.health_points == hp, "practice must never change HP"
    rows = xp.skill_table(board.git)
    gym = [k for k in rows if k.startswith("gym:")]
    assert gym and rows[gym[0]]["success"] == 1 and rows[gym[0]]["verified"] == 1
    stats = xp.lineage_stats(board.git)
    assert stats["xp"] == pytest.approx(10 * 0.3 * 0.3, abs=0.001), "10 base x 0.3 difficulty x 0.3 gym weight (verified, first time)"


@pytest.mark.asyncio
async def test_a_wrong_answer_does_not_verify(board, monkeypatch):
    monkeypatch.setattr(wb, "_git", lambda *a: "some-other-branch" if a[0] == "rev-parse" else "")
    out = await board.b.run_cycle(force=True)
    assert out["ran"][0]["passed"] is False
    assert xp.skill_table(board.git)[out["ran"][0] and f"gym:{out['ran'][0]['drill']}"]["fail_own"] == 1


@pytest.mark.asyncio
async def test_agents_without_a_drill_are_left_alone_and_reported(board):
    cov = board.b.coverage()
    assert cov["agents"] == 2 and cov["with_drill"] == 1 and cov["without_drill"] == 1
    assert cov["districts_without_any_drill"] == ["misc"]
    out = await board.b.run_cycle(force=True, max_agents=5)
    assert {r["agent"] for r in out["ran"]} == {"GitBot"}


@pytest.mark.asyncio
async def test_per_agent_daily_cap_and_idle_window(board):
    for _ in range(wb.MAX_DRILLS_PER_AGENT_PER_DAY + 2):
        await board.b.run_cycle(force=True, idle_hours=0)        # idle_hours=0: everyone counts as idle every time
    assert board.b._drilled_today(board.git) == wb.MAX_DRILLS_PER_AGENT_PER_DAY
    fresh = await board.b.run_cycle(force=True)                  # GitBot just practised, so it is no longer idle for 24 h
    assert fresh["ran"] == []


@pytest.mark.asyncio
async def test_practice_waits_while_the_owner_is_coding(board, monkeypatch):
    monkeypatch.setattr(wb.WorkBoard, "_owner_busy", staticmethod(lambda: True))
    monkeypatch.setenv("VECTOR_GYM", "1")
    out = await board.b.run_cycle()
    assert out["ran"] == [] and "owner is coding" in out["skipped"]


@pytest.mark.asyncio
async def test_llm_drills_stay_off_unless_explicitly_enabled(board, monkeypatch):
    llm = wb.register_drill(wb.Drill(name="llm_thing", task_type="respond", matches=lambda a: a.name == "Plain",
                                     verify=lambda r: True, needs_llm=True))
    try:
        assert board.b.drills_for(board.plain) == []
        monkeypatch.setenv("VECTOR_GYM_LLM", "1")
        assert [d.name for d in board.b.drills_for(board.plain)] == ["llm_thing"]
    finally:
        wb._DRILLS[:] = [d for d in wb._DRILLS if d.name != llm.name]


@pytest.mark.asyncio
async def test_the_governor_does_not_reward_a_no_reward_request(board):
    hp = board.git.health_points
    r = await board.b._bus.ask("work_board", "git_status", {}, to=board.git.id, no_reward=True)
    assert r.ok and board.git.health_points == hp
    assert xp.lineage_stats(board.git)["outcomes"] == {}, "the Governor must not write a ledger row for a drill (the board does)"
    r2 = await board.b._bus.ask("work_board", "git_status", {}, to=board.git.id)
    assert board.git.health_points > hp and xp.lineage_stats(board.git)["outcomes"] == {"success": 1}

# ── district drills (2026-09-27): pure handlers, answers checked by an XML parser / Python's own ast ───────────────────────────

def _drill(name):
    return next(d for d in wb._DRILLS if d.name == name)


@pytest.mark.asyncio
async def test_ssml_drill_passes_with_the_real_voice_generator_and_catches_invalid_xml():
    from districts.content.voice_generator import VoiceGenerator

    d = _drill("ssml_is_well_formed_xml")
    result = await VoiceGenerator().run({"type": d.task_type, "params": d.params})
    assert d.verify(result) is True, result
    # the verifier is independent of the agent: broken XML and altered sentences both fail it
    assert d.verify({"ssml": "<speak><s>Hello world.</s>"}) is False
    assert d.verify({"ssml": "<speak><s>Hello world.</s></speak>"}) is False
    assert d.verify({"status": "ok"}) is False


@pytest.mark.asyncio
async def test_static_review_drill_passes_with_the_real_python_reviewer(monkeypatch):
    from districts.coding.python_reviewer import PythonReviewer

    monkeypatch.delenv("VECTOR_PYTHON_REVIEW_LLM", raising=False)
    d = _drill("static_review_flags_the_lines_ast_finds")
    reviewer = PythonReviewer()
    assert d.matches(reviewer) is True
    result = await reviewer.run({"type": d.task_type, "params": d.params})
    assert d.verify(result) is True, result
    assert d.verify({"issues": []}) is False
    assert d.verify({"issues": [{"line": 2, "severity": "MED"}, {"line": 3, "severity": "MED"}]}) is False


def test_static_review_drill_is_not_used_when_the_reviewer_would_call_an_llm(monkeypatch):
    from districts.coding.python_reviewer import PythonReviewer

    monkeypatch.setenv("VECTOR_PYTHON_REVIEW_LLM", "1")
    assert _drill("static_review_flags_the_lines_ast_finds").matches(PythonReviewer()) is False


def test_the_voice_generator_escapes_xml_special_characters():
    from districts.content.voice_generator import VoiceGenerator

    ssml = VoiceGenerator().text_to_ssml("Tom & Jerry <live>. Second one")
    assert "&amp;" in ssml and "&lt;live&gt;" in ssml

