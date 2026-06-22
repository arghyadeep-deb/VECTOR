"""
Module: tests/test_languages_district_run_wiring.py
District: languages | Focus: regression tests for run() task-type routing

AgentBase.run() is a fake-success stub that ignores task content. The governor
dispatches via `await agent.run(task)` where task = {"type": ..., "params": {...}}.
These tests confirm AssameseCoach, BengaliCoach, EnglishCoach, and HindiCoach
actually branch on task["type"] instead of always returning track_progress().

JapaneseCoach (already correctly wired) is the reference pattern and is NOT
touched or tested here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.agent_base import AgentBase
from districts.languages.assamese_coach import AssameseCoach
from districts.languages.bengali_coach import BengaliCoach
from districts.languages.english_coach import EnglishCoach
from districts.languages.hindi_coach import HindiCoach


# ---------------------------------------------------------------------------
# AssameseCoach
# ---------------------------------------------------------------------------

def test_assamese_coach_is_agent_base_subclass():
    assert issubclass(AssameseCoach, AgentBase)


async def test_assamese_coach_run_routes_practice_vocabulary():
    agent = AssameseCoach()
    result = await agent.run({"type": "practice_vocabulary", "params": {"word_count": 4}})
    assert result["status"] == "ok"
    assert result["language"] == "assamese"
    assert result["practice_type"] == "vocabulary"


async def test_assamese_coach_run_routes_grammar_check():
    agent = AssameseCoach()
    result = await agent.run({"type": "grammar_check", "params": {"text": "মই পানী খাও"}})
    assert result["status"] == "ok"
    assert "corrections" in result


async def test_assamese_coach_run_routes_generate_sentences():
    agent = AssameseCoach()
    result = await agent.run({"type": "generate_sentences", "params": {"word": "জ্ঞান"}})
    assert result["status"] == "ok"
    assert "sentences" in result


async def test_assamese_coach_run_routes_track_progress():
    agent = AssameseCoach()
    result = await agent.run({"type": "track_progress", "params": {}})
    assert result["status"] == "ok"
    assert "total_words" in result


async def test_assamese_coach_run_unhandled_type_returns_error():
    agent = AssameseCoach()
    result = await agent.run({"type": "nonexistent_task", "params": {}})
    assert result["status"] == "error"
    assert "nonexistent_task" in result["error"]
    assert "supported" in result


# ---------------------------------------------------------------------------
# BengaliCoach
# ---------------------------------------------------------------------------

def test_bengali_coach_is_agent_base_subclass():
    assert issubclass(BengaliCoach, AgentBase)


async def test_bengali_coach_run_routes_practice_vocabulary():
    agent = BengaliCoach()
    result = await agent.run({"type": "practice_vocabulary", "params": {"word_count": 4}})
    assert result["status"] == "ok"
    assert result["language"] == "bengali"
    assert result["practice_type"] == "vocabulary"


async def test_bengali_coach_run_routes_grammar_check():
    agent = BengaliCoach()
    result = await agent.run({"type": "grammar_check", "params": {"text": "আমি জল খাই"}})
    assert result["status"] == "ok"
    assert "corrections" in result


async def test_bengali_coach_run_routes_generate_sentences():
    agent = BengaliCoach()
    result = await agent.run({"type": "generate_sentences", "params": {"word": "জ্ঞান"}})
    assert result["status"] == "ok"
    assert "sentences" in result


async def test_bengali_coach_run_routes_track_progress():
    agent = BengaliCoach()
    result = await agent.run({"type": "track_progress", "params": {}})
    assert result["status"] == "ok"
    assert "total_words" in result


async def test_bengali_coach_run_unhandled_type_returns_error():
    agent = BengaliCoach()
    result = await agent.run({"type": "nonexistent_task", "params": {}})
    assert result["status"] == "error"
    assert "nonexistent_task" in result["error"]
    assert "supported" in result


# ---------------------------------------------------------------------------
# EnglishCoach
# ---------------------------------------------------------------------------

def test_english_coach_is_agent_base_subclass():
    assert issubclass(EnglishCoach, AgentBase)


async def test_english_coach_run_routes_practice_vocabulary():
    agent = EnglishCoach()
    result = await agent.run({"type": "practice_vocabulary", "params": {"word_count": 4}})
    assert result["status"] == "ok"
    assert result["language"] == "english"
    assert result["practice_type"] == "vocabulary"


async def test_english_coach_run_routes_grammar_check():
    agent = EnglishCoach()
    result = await agent.run({"type": "grammar_check", "params": {"text": "I have went to the store"}})
    assert result["status"] == "ok"
    assert "corrections" in result


async def test_english_coach_run_routes_generate_sentences():
    agent = EnglishCoach()
    result = await agent.run({"type": "generate_sentences", "params": {"word": "ubiquitous"}})
    assert result["status"] == "ok"
    assert "sentences" in result


async def test_english_coach_run_routes_track_progress():
    agent = EnglishCoach()
    result = await agent.run({"type": "track_progress", "params": {}})
    assert result["status"] == "ok"
    assert "total_words" in result


async def test_english_coach_run_unhandled_type_returns_error():
    agent = EnglishCoach()
    result = await agent.run({"type": "nonexistent_task", "params": {}})
    assert result["status"] == "error"
    assert "nonexistent_task" in result["error"]
    assert "supported" in result


# ---------------------------------------------------------------------------
# HindiCoach
# ---------------------------------------------------------------------------

def test_hindi_coach_is_agent_base_subclass():
    assert issubclass(HindiCoach, AgentBase)


async def test_hindi_coach_run_routes_practice_vocabulary():
    agent = HindiCoach()
    result = await agent.run({"type": "practice_vocabulary", "params": {"word_count": 4}})
    assert result["status"] == "ok"
    assert result["language"] == "hindi"
    assert result["practice_type"] == "vocabulary"


async def test_hindi_coach_run_routes_grammar_check():
    agent = HindiCoach()
    result = await agent.run({"type": "grammar_check", "params": {"text": "मैं किताब पढ़ा"}})
    assert result["status"] == "ok"
    assert "corrections" in result


async def test_hindi_coach_run_routes_generate_sentences():
    agent = HindiCoach()
    result = await agent.run({"type": "generate_sentences", "params": {"word": "ज्ञान"}})
    assert result["status"] == "ok"
    assert "sentences" in result


async def test_hindi_coach_run_routes_track_progress():
    agent = HindiCoach()
    result = await agent.run({"type": "track_progress", "params": {}})
    assert result["status"] == "ok"
    assert "total_words" in result


async def test_hindi_coach_run_unhandled_type_returns_error():
    agent = HindiCoach()
    result = await agent.run({"type": "nonexistent_task", "params": {}})
    assert result["status"] == "error"
    assert "nonexistent_task" in result["error"]
    assert "supported" in result


if __name__ == "__main__":
    import asyncio

    async def _run_all():
        await test_assamese_coach_run_routes_practice_vocabulary()
        await test_assamese_coach_run_routes_grammar_check()
        await test_assamese_coach_run_routes_generate_sentences()
        await test_assamese_coach_run_routes_track_progress()
        await test_assamese_coach_run_unhandled_type_returns_error()
        await test_bengali_coach_run_routes_practice_vocabulary()
        await test_bengali_coach_run_routes_grammar_check()
        await test_bengali_coach_run_routes_generate_sentences()
        await test_bengali_coach_run_routes_track_progress()
        await test_bengali_coach_run_unhandled_type_returns_error()
        await test_english_coach_run_routes_practice_vocabulary()
        await test_english_coach_run_routes_grammar_check()
        await test_english_coach_run_routes_generate_sentences()
        await test_english_coach_run_routes_track_progress()
        await test_english_coach_run_unhandled_type_returns_error()
        await test_hindi_coach_run_routes_practice_vocabulary()
        await test_hindi_coach_run_routes_grammar_check()
        await test_hindi_coach_run_routes_generate_sentences()
        await test_hindi_coach_run_routes_track_progress()
        await test_hindi_coach_run_unhandled_type_returns_error()

    test_assamese_coach_is_agent_base_subclass()
    test_bengali_coach_is_agent_base_subclass()
    test_english_coach_is_agent_base_subclass()
    test_hindi_coach_is_agent_base_subclass()
    asyncio.run(_run_all())
    print("OK test_languages_district_run_wiring.py")
