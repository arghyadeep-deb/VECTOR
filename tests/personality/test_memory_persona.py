import tempfile
from pathlib import Path

from core.personality.memory_persona import MemoryPersona, PersonalityLesson


def _make_memory(db_path: str | None = None) -> MemoryPersona:
    if db_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
    return MemoryPersona(db_path=str(db_path))


def test_detect_positive_feedback():
    mp = _make_memory()
    result = mp.detect_feedback("That was perfect, great work!")
    assert result is not None
    assert result["outcome"] == 0.9
    assert result["source"] == "explicit_feedback"


def test_detect_negative_feedback():
    mp = _make_memory()
    result = mp.detect_feedback("That is too verbose, be more concise")
    assert result is not None
    assert result["outcome"] < 0.5
    assert result["source"] == "explicit_feedback"


def test_detect_neutral_feedback():
    mp = _make_memory()
    result = mp.detect_feedback("okay, fine")
    assert result is not None
    assert result["outcome"] == 0.6


def test_detect_no_feedback():
    mp = _make_memory()
    result = mp.detect_feedback("What is the weather today?")
    assert result is None


def test_store_and_query_lesson():
    mp = _make_memory()
    mp.store_lesson(PersonalityLesson(
        context="debugging", user_sentiment="frustrated",
        response_type="concise", outcome=0.9,
        timestamp="2025-01-01T00:00:00", source="explicit_feedback", confidence=1.0,
    ))
    mp.store_lesson(PersonalityLesson(
        context="debugging", user_sentiment="frustrated",
        response_type="concise", outcome=0.8,
        timestamp="2025-01-01T00:00:01", source="explicit_feedback", confidence=1.0,
    ))
    results = mp.query_top_preferences(context="debugging")
    assert len(results) > 0
    assert results[0]["response_type"] == "concise"


def test_query_preferences_with_sentiment():
    mp = _make_memory()
    mp.store_lesson(PersonalityLesson(
        context="general", user_sentiment="frustrated",
        response_type="direct", outcome=0.8,
        timestamp="2025-01-01T00:00:00", source="explicit_feedback", confidence=1.0,
    ))
    mp.store_lesson(PersonalityLesson(
        context="general", user_sentiment="frustrated",
        response_type="direct", outcome=0.9,
        timestamp="2025-01-01T00:00:01", source="explicit_feedback", confidence=1.0,
    ))
    results = mp.query_top_preferences(context="general", sentiment="frustrated")
    assert len(results) > 0


def test_query_empty_when_no_lessons():
    mp = _make_memory()
    results = mp.query_top_preferences(context="nonexistent")
    assert len(results) == 0


def test_context_classification_debugging():
    mp = _make_memory()
    ctx = mp.get_context("There is a bug in this code, the error trace shows a crash")
    assert ctx == "debugging"


def test_context_classification_coding():
    mp = _make_memory()
    ctx = mp.get_context("Can you implement a new function for sorting?")
    assert ctx == "coding"


def test_context_classification_general():
    mp = _make_memory()
    ctx = mp.get_context("What do you think about AI?")
    assert ctx == "general"


def test_implicit_feedback_rephrase():
    mp = _make_memory()
    lesson = mp.infer_implicit_feedback(
        "Show me the code for sorting",
        "Show me the code for sorting algorithm",
    )
    assert lesson is not None
    assert lesson.source == "implicit"


def test_implicit_feedback_positive():
    mp = _make_memory()
    lesson = mp.infer_implicit_feedback("some text", "ok")
    assert lesson is not None
    assert lesson.outcome == 0.7


def test_implicit_feedback_none():
    mp = _make_memory()
    lesson = mp.infer_implicit_feedback("some text", "")
    assert lesson is None


def test_infer_target_concise():
    mp = _make_memory()
    target = mp._infer_target("too verbose")
    assert target == "concise"
