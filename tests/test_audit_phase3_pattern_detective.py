"""Phase 3 audit regressions for districts/pattern_detective."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from districts.pattern_detective import behavior_analyst as ba_mod
from districts.pattern_detective import habit_finder as hf_mod
from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
from districts.pattern_detective.habit_finder import HabitFinder

_CHAT = "core.inference.vectorcode_llm.chat"
_HYDRATE = "core.loop.context_engine.ContextEngine.session_hydration_prompt"

LOG = [
    {"type": "coding", "timestamp": "2026-05-01T10:00:00Z", "duration": 120},
    {"type": "coding", "timestamp": "2026-05-02T10:00:00Z", "duration": 60},
]


@pytest.fixture
def logs():
    lines: list[str] = []
    hid = logger.add(lambda m: lines.append(str(m)), level="DEBUG", format="{message}")
    yield lines
    logger.remove(hid)


def _run(c):
    return asyncio.run(c)


def _ba(recall=None):
    with patch.object(ba_mod, "EpisodicMemory"), patch.object(ba_mod, "ObsidianSync"):
        a = BehaviorAnalyst()
    a.memory = MagicMock()
    a.memory.recall.return_value = recall or []
    return a


def _hf(recall=None):
    with patch.object(hf_mod, "EpisodicMemory"), patch.object(hf_mod, "ObsidianSync"):
        a = HabitFinder()
    a.memory = MagicMock()
    a.memory.recall.return_value = recall or []
    return a


# ---- BehaviorAnalyst ------------------------------------------------------
def test_empty_activity_log_is_no_data_not_analysis():
    a = _ba()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="Consistency 9/10") as chat:
        res = a.analyze_behavior([])
    assert res["status"] == "no_data"
    chat.assert_not_called()
    a.memory.store.assert_not_called()


def test_behavior_llm_failure_is_error_and_not_stored():
    a = _ba()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value=""):
        res = a.analyze_behavior(LOG)
    assert res["status"] == "error"
    a.memory.store.assert_not_called()


def test_bad_timestamp_and_string_duration_do_not_crash_or_use_literal_swallow(logs):
    a = _ba()
    entries = LOG + [{"type": "coding", "timestamp": "not-a-date", "duration": "45"}]
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="ok insights"):
        res = a.analyze_behavior(entries)
    assert res["status"] == "ok"
    assert res["behavior_profile"]["coding"]["total_duration"] == 225.0
    text = "\n".join(logs)
    assert "suppressed exception" not in text
    assert "unparseable timestamps" in text


def test_predict_without_any_history_is_no_data():
    a = _ba([])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value='{"predicted_action": "x", "confidence": 0.9}') as chat:
        res = a.predict_next_action({"day": "Monday"})
    assert res["status"] == "no_data" and res["prediction"] == {}
    chat.assert_not_called()


def test_predict_ignores_own_derived_events():
    a = _ba([{"event_type": "behavior_analyzed", "timestamp": "2026-05-01T10:00:00Z", "source": "BehaviorAnalyst"}])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="x") as chat:
        res = a.predict_next_action({})
    assert res["status"] == "no_data"
    chat.assert_not_called()


def test_suggest_improvements_empty_behavior_and_llm_failure():
    a = _ba()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="") as chat:
        assert a.suggest_improvements({})["status"] == "no_data"
        chat.assert_not_called()
        assert a.suggest_improvements({"coding": {"frequency": 1}})["status"] == "error"
    a.memory.store.assert_not_called()


def test_behavior_run_tolerates_none_params_and_actually_analyses():
    a = _ba([{"event_type": "coding", "timestamp": "2026-05-01T10:00:00Z", "source": "x"}])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="insight"):
        res = _run(a.run({"type": "x", "params": None}))
    assert res["status"] == "ok" and res["analysis"]["total_activities"] == 1


def test_behavior_run_with_no_data_is_not_ok():
    a = _ba([])
    res = _run(a.run({"type": "x", "params": {}}))
    assert res["status"] == "no_data"


def test_behavior_llm_local_only():
    a = _ba()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="x") as chat:
        a._call_ollama("p")
    assert chat.call_args.kwargs["allow_cloud"] is False
    assert chat.call_args.kwargs["sensitive"] is True


# ---- HabitFinder ----------------------------------------------------------
def test_screen_time_empty_is_no_data():
    a = _hf()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="all healthy") as chat:
        res = a.analyze_screen_time([])
    assert res["status"] == "no_data"
    chat.assert_not_called()
    a.memory.store.assert_not_called()


def test_missing_hour_does_not_fabricate_noon_peak():
    a = _hf()
    data = [{"date": "2026-05-01", "app": "Chrome", "duration_minutes": 60}]
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="insight"):
        res = a.analyze_screen_time(data)
    assert res["peak_hour"] is None and res["hourly_breakdown"] == {}


def test_screen_time_bad_duration_and_llm_failure():
    a = _hf()
    data = [{"date": "d", "app": "A", "duration_minutes": "x", "hour": 3},
            {"date": "d", "app": "A", "duration_minutes": "30", "hour": 3}]
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value=""):
        res = a.analyze_screen_time(data)
    assert res["status"] == "error" and res["total_minutes"] == 30.0
    a.memory.store.assert_not_called()


def test_find_habits_empty_is_no_data():
    a = _hf()
    res = a.find_habits([])
    assert res["status"] == "no_data"
    a.memory.store.assert_not_called()


def test_find_habits_bad_timestamp_logged_not_literal_swallow_and_none_content(logs):
    a = _hf()
    ev = [{"event_type": "coding", "timestamp": f"2026-05-0{d}T14:00:00Z", "content": None} for d in (1, 2, 3)]
    ev.append({"event_type": "coding", "timestamp": "garbage", "content": "x"})
    res = a.find_habits(ev)
    assert res["status"] == "ok" and res["patterns_found"] >= 1
    text = "\n".join(logs)
    assert "suppressed exception" not in text and "unparseable timestamps" in text


def test_habit_report_with_no_events_is_no_data_and_skips_llm():
    a = _hf([])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="Great habits!") as chat:
        res = a.generate_habit_report()
        run_res = _run(a.run({"type": "x", "params": None}))
    assert res["status"] == "no_data" and res["habit_report"] == ""
    assert run_res["status"] == "no_data"
    chat.assert_not_called()
    a.memory.store.assert_not_called()


def test_habit_report_ignores_own_events_and_reports_llm_failure():
    own = [{"event_type": "habits_found", "timestamp": f"2026-05-0{d}T14:00:00Z", "content": "c", "source": "HabitFinder"} for d in (1, 2, 3)]
    a = _hf(own)
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="r") as chat:
        assert a.generate_habit_report()["status"] == "no_data"
    chat.assert_not_called()

    real = [{"event_type": "coding", "timestamp": f"2026-05-0{d}T14:00:00Z", "content": "c", "source": "x"} for d in (1, 2, 3)]
    b = _hf(real)
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value=""):
        assert b.generate_habit_report()["status"] == "error"
    b.memory.store.assert_called_once()  # only the habits_found event, no fake report stored


def test_habit_llm_local_only():
    a = _hf()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="x") as chat:
        a._call_ollama("p")
    assert chat.call_args.kwargs["allow_cloud"] is False
    assert chat.call_args.kwargs["sensitive"] is True
