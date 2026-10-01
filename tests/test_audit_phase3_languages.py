"""Audit phase 3 (languages): an empty LLM response must not be reported as a successful result."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.languages.assamese_coach import AssameseCoach
from districts.languages.bengali_coach import BengaliCoach
from districts.languages.english_coach import EnglishCoach
from districts.languages.hindi_coach import HindiCoach
from districts.languages.japanese_coach import JapaneseCoach

COACHES = [HindiCoach, EnglishCoach, BengaliCoach, AssameseCoach, JapaneseCoach]


def _dead_llm(coach):
    stored = []
    coach._call_ollama = lambda prompt, model=None: ""  # vectorcode_llm.chat returns "" on total failure
    coach.memory.store = lambda **kw: stored.append(kw)
    return stored


@pytest.mark.parametrize("cls", COACHES)
async def test_grammar_check_llm_failure_is_error_not_ok(cls):
    coach = cls()
    stored = _dead_llm(coach)
    result = await coach.run({"type": "grammar_check", "params": {"text": "sample"}})
    assert result["status"] == "error"
    assert "corrections" not in result
    assert stored == []


@pytest.mark.parametrize("cls", COACHES)
async def test_generate_sentences_llm_failure_is_error_not_ok(cls):
    coach = cls()
    stored = _dead_llm(coach)
    result = await coach.run({"type": "generate_sentences", "params": {"word": "x"}})
    assert result["status"] == "error"
    assert "sentences" not in result
    assert stored == []


@pytest.mark.parametrize("cls", COACHES)
async def test_real_llm_text_still_ok(cls):
    coach = cls()
    coach._call_ollama = lambda prompt, model=None: "line1\nline2"
    coach.memory.store = lambda **kw: None
    r = await coach.run({"type": "grammar_check", "params": {"text": "t"}})
    assert r["status"] == "ok" and r["corrections"] == "line1\nline2"
    r = await coach.run({"type": "generate_sentences", "params": {"word": "w"}})
    assert r["status"] == "ok" and r["count"] == 2
