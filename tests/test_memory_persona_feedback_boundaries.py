"""Regression for core/personality/memory_persona.py MemoryPersona.detect_feedback():

detect_feedback() matched feedback phrases with a plain substring check
(``phrase in lower``) against the short, common words in
_FEEDBACK_NEGATIVE/_POSITIVE/_NEUTRAL. Substring matching on short words is
unsound: "no" matches inside "know"/"now"/"not"/"nowhere"/"nonstarter",
"yes" matches inside "yesterday", "ok" matches inside "book"/"broken",
"sure" matches inside "ensure"/"assure". This engine is on the hot path for
every LLM turn (core/personality/__init__.py's PersonalityEngine.process()
calls detect_feedback(user_text) every time), so almost any natural-language
message containing one of these extremely common letter sequences got
silently recorded as explicit positive/negative feedback -- corrupting the
learned-preference signal (MemoryPersona.store_lesson() /
query_top_preferences()) that VECTOR's personality adaptation relies on.

Fixed by matching each phrase with a \\b-word-boundary regex instead of a
bare substring check.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from core.personality.memory_persona import MemoryPersona


def _mp(tmp_path: Path) -> MemoryPersona:
    return MemoryPersona(db_path=str(tmp_path / "test.db"))


def test_no_false_positive_on_words_containing_no():
    with tempfile.TemporaryDirectory() as d:
        mp = _mp(Path(d))
        for text in ["I know the answer", "please go now", "a nonstarter idea", "fly to nowhere"]:
            assert mp.detect_feedback(text) is None, f"false positive on {text!r}"


def test_no_false_positive_on_words_containing_yes():
    with tempfile.TemporaryDirectory() as d:
        mp = _mp(Path(d))
        assert mp.detect_feedback("yesterday I went out") is None


def test_no_false_positive_on_words_containing_ok():
    with tempfile.TemporaryDirectory() as d:
        mp = _mp(Path(d))
        for text in ["please book a flight", "the screen looks broken", "here's a token"]:
            assert mp.detect_feedback(text) is None, f"false positive on {text!r}"


def test_no_false_positive_on_words_containing_sure():
    with tempfile.TemporaryDirectory() as d:
        mp = _mp(Path(d))
        for text in ["ensure this works correctly", "assure me you tried your best"]:
            assert mp.detect_feedback(text) is None, f"false positive on {text!r}"


def test_real_feedback_still_detected():
    with tempfile.TemporaryDirectory() as d:
        mp = _mp(Path(d))
        assert mp.detect_feedback("no, that is wrong")["outcome"] < 0.5
        assert mp.detect_feedback("perfect, thanks")["outcome"] > 0.5
        assert mp.detect_feedback("that's too verbose")["response_type"] == "concise"


if __name__ == "__main__":
    test_no_false_positive_on_words_containing_no()
    test_no_false_positive_on_words_containing_yes()
    test_no_false_positive_on_words_containing_ok()
    test_no_false_positive_on_words_containing_sure()
    test_real_feedback_still_detected()
    print("OK - test_memory_persona_feedback_boundaries.py")
