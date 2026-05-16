import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
import tempfile
from unittest.mock import patch, MagicMock


# ── Init ──────────────────────────────────────────────────────────────────────

def test_llm_council_init():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()
    assert bot.health_points == 500
    assert bot.name == "LLMCouncil"
    assert bot.district == "governance"


def test_llm_council_inherits_ghost():
    from agents.governance.llm_council import LLMCouncil
    ghost = {"lessons_learned": ["be decisive"], "best_decisions": [], "personality_traits": {}, "generation": 1}
    bot = LLMCouncil(generation=2, ghost=ghost)
    assert "be decisive" in bot.lessons


# ── Parse ranking ─────────────────────────────────────────────────────────────

def test_parse_ranking_extracts_final_section():
    from agents.governance.llm_council import LLMCouncil
    text = "Response A is good. Response B is average.\nFINAL RANKING:\n1. Response A\n2. Response B"
    result = LLMCouncil._parse_ranking(text)
    assert result == ["Response A", "Response B"]


def test_parse_ranking_fallback_when_no_header():
    from agents.governance.llm_council import LLMCouncil
    text = "I think Response B is best, then Response A."
    result = LLMCouncil._parse_ranking(text)
    assert "Response B" in result
    assert "Response A" in result


def test_parse_ranking_empty_text():
    from agents.governance.llm_council import LLMCouncil
    result = LLMCouncil._parse_ranking("")
    assert result == []


# ── Aggregate rankings ────────────────────────────────────────────────────────

def test_calculate_aggregate_correct_order():
    from agents.governance.llm_council import LLMCouncil
    stage2 = [
        {"parsed": ["Response A", "Response B", "Response C"]},
        {"parsed": ["Response A", "Response C", "Response B"]},
    ]
    label_to_model = {
        "Response A": "model-alpha",
        "Response B": "model-beta",
        "Response C": "model-gamma",
    }
    agg = LLMCouncil._calculate_aggregate(stage2, label_to_model)
    assert agg[0]["model"] == "model-alpha"
    assert agg[0]["avg_rank"] == 1.0


def test_calculate_aggregate_empty_stage2():
    from agents.governance.llm_council import LLMCouncil
    result = LLMCouncil._calculate_aggregate([], {})
    assert result == []


# ── HP gate ────────────────────────────────────────────────────────────────────

def test_convene_hp_gate_blocks_low_hp():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()
    result = asyncio.run(bot.convene("test question", stakes="high", requester_hp=100))
    assert "HP gate" in result["verdict"]
    assert result["stage1"] == []


def test_convene_hp_gate_allows_high_hp():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()

    def fake_call(model, system, user):
        return f"Response from {model}: this is my answer."

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Council").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "_call_model", side_effect=fake_call):
            result = asyncio.run(bot.convene("test question", stakes="high", requester_hp=750))

    assert "HP gate" not in result["verdict"]
    assert result["session_id"] != ""


# ── Weekly throttle ───────────────────────────────────────────────────────────

def test_convene_throttle_blocks_when_maxed():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()

    with patch.object(bot, "_sessions_this_week", return_value=10):
        result = asyncio.run(bot.convene("test question", stakes="high", requester_hp=750))

    assert "throttled" in result["verdict"].lower()


# ── Full session ──────────────────────────────────────────────────────────────

def test_convene_full_session_returns_verdict():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()

    call_count = [0]

    def fake_call(model, system, user):
        call_count[0] += 1
        if "Chairman" in system or "Chairman" in user or "synthesize" in user.lower():
            return "Chairman verdict: the answer is 42."
        if "FINAL RANKING" in user:
            return "Response A is best.\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"
        return f"My answer from {model}: this is a thoughtful response."

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Council").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "_call_model", side_effect=fake_call):
            result = asyncio.run(
                bot.convene("What is the meaning of life?", stakes="high", requester_hp=800)
            )

    assert isinstance(result["verdict"], str)
    assert len(result["verdict"]) > 0
    assert "session_id" in result
    assert isinstance(result["stage1"], list)
    assert len(result["stage1"]) == 3  # all 3 council members responded


def test_convene_awards_hp_on_success():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()
    initial_hp = bot.health_points

    def fake_call(model, system, user):
        return f"Response from {model}."

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Council").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "_call_model", side_effect=fake_call):
            asyncio.run(bot.convene("test", stakes="high", requester_hp=750))

    assert bot.health_points > initial_hp


def test_convene_deducts_hp_on_all_models_fail():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()
    initial_hp = bot.health_points

    with patch.object(bot, "_call_model", return_value=""):
        result = asyncio.run(bot.convene("test", stakes="high", requester_hp=750))

    assert bot.health_points < initial_hp
    assert "failed" in result["verdict"].lower()


def test_convene_increments_weekly_count():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()

    week_key = bot._week_key()
    # Clear any existing count for this week
    bot._memory.remember(key=week_key, value="0", category="council_throttle", confidence=1.0)
    before = bot._sessions_this_week()

    def fake_call(model, system, user):
        return f"Response from {model}."

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Council").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "_call_model", side_effect=fake_call):
            asyncio.run(bot.convene("test", stakes="high", requester_hp=750))

    after = bot._sessions_this_week()
    assert after == before + 1


def test_convene_writes_obsidian_note():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()

    def fake_call(model, system, user):
        return f"Response from {model}."

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Council").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "_call_model", side_effect=fake_call):
            asyncio.run(bot.convene("test question", stakes="high", requester_hp=750))

        notes = list((vault / "Council").glob("*.md"))
        assert len(notes) >= 1


def test_convene_stores_session_in_memory():
    from agents.governance.llm_council import LLMCouncil
    bot = LLMCouncil()

    def fake_call(model, system, user):
        return f"Response from {model}."

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Council").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "_call_model", side_effect=fake_call):
            result = asyncio.run(bot.convene("store test", stakes="high", requester_hp=750))

    # Session should be stored — verify a council event exists in episodic memory
    events = bot._memory.recall("store test", limit=5, event_type="council_session")
    assert len(events) > 0
