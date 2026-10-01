"""Phase 3 audit regressions for districts/relationships (privacy + silent-failure fixes)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from districts.relationships import communication_analyst as ca_mod
from districts.relationships import contact_manager as cm_mod
from districts.relationships.communication_analyst import CommunicationAnalyst
from districts.relationships.contact_manager import ContactManager

_CHAT = "core.inference.vectorcode_llm.chat"
_HYDRATE = "core.loop.context_engine.ContextEngine.session_hydration_prompt"
SECRET_NAME = "Zebulon Quixote"


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def logs():
    lines: list[str] = []
    hid = logger.add(lambda m: lines.append(str(m)), level="DEBUG", format="{message}")
    yield lines
    logger.remove(hid)


def _run(c):
    return asyncio.run(c)


def _cm():
    with patch.object(cm_mod, "EpisodicMemory"), patch.object(cm_mod, "ObsidianSync"):
        a = ContactManager()
    a.memory = MagicMock()
    return a


def _ca(recall=None):
    with patch.object(ca_mod, "EpisodicMemory"), patch.object(ca_mod, "ObsidianSync"):
        a = CommunicationAnalyst()
    a.memory = MagicMock()
    a.memory.recall.return_value = recall or []
    return a


# ---- ContactManager -------------------------------------------------------
def test_re_adding_contact_keeps_interaction_history():
    cm = _cm()
    cm.add_contact("Alice", "1", "a@x.test", "old")
    cm.track_interaction("Alice", "lunch", "meeting")
    cm.add_contact("Alice", "2", "a@x.test", "updated notes")
    c = cm.get_contact("Alice")
    assert c["contact_count"] == 1 and c["last_contacted"]
    assert c["phone"] == "2" and c["notes"] == "updated notes"


def test_track_interaction_for_unknown_contact_is_error_and_not_stored():
    cm = _cm()
    res = cm.track_interaction("Ghost", "hello")
    assert res["status"] == "error"
    cm.memory.store.assert_not_called()
    conn = cm._get_conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0] == 0
    finally:
        conn.close()


def test_blank_contact_name_rejected():
    cm = _cm()
    assert cm.add_contact("  ", "1")["status"] == "error"
    assert cm.list_contacts()["total_contacts"] == 0


def test_contact_names_not_logged_or_kept_in_lessons(logs):
    cm = _cm()
    cm.add_contact(SECRET_NAME, "+911", "z@x.test", "n")
    cm.get_contact(SECRET_NAME)
    cm.track_interaction(SECRET_NAME, "met")
    assert SECRET_NAME not in "\n".join(logs)
    assert SECRET_NAME not in str(cm.lessons)


def test_run_tolerates_none_params_and_reports_missing_contact():
    cm = _cm()
    assert _run(cm.run({"type": "x", "params": None}))["status"] == "ok"
    res = _run(cm.run({"type": "x", "params": {"name": "Nobody"}}))
    assert res["status"] == "error"


def test_contact_llm_call_is_local_only():
    cm = _cm()
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="x") as chat:
        cm._call_ollama("p")
    kw = chat.call_args.kwargs
    assert kw["allow_cloud"] is False and kw["sensitive"] is True


# ---- CommunicationAnalyst -------------------------------------------------
def test_analyze_style_without_history_is_no_data_not_fabricated():
    a = _ca([])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value='{"style": "casual"}') as chat:
        res = a.analyze_communication_style("Alice")
    assert res["status"] == "no_data"
    chat.assert_not_called()
    a.memory.store.assert_not_called()
    assert "Alice" not in a.communication_profiles


def test_analyze_style_llm_failure_is_error_not_balanced_default():
    a = _ca([{"event_type": "message", "content": "hey", "timestamp": "2026-05-01T10:00:00Z", "source": "gmail"}])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value=""):
        res = a.analyze_communication_style("Alice")
    assert res["status"] == "error"
    a.memory.store.assert_not_called()
    assert "Alice" not in a.communication_profiles


def test_reconnect_uses_newest_real_interaction_and_ignores_own_events():
    a = _ca([
        {"event_type": "reconnect_suggested", "content": "Suggested reconnection", "timestamp": "2026-09-30T00:00:00+00:00", "source": "CommunicationAnalyst"},
        {"event_type": "interaction_tracked", "content": "old", "timestamp": "2026-01-01T00:00:00+00:00", "source": "ContactManager"},
        {"event_type": "interaction_tracked", "content": "newer", "timestamp": "2026-03-01T00:00:00+00:00", "source": "ContactManager"},
    ])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="Send a message"):
        res = a.suggest_reconnect("Alice")
    assert res["status"] == "ok"
    assert res["last_interaction"] == "2026-03-01T00:00:00+00:00"


def test_reconnect_empty_llm_is_error():
    a = _ca([])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="  "):
        res = a.suggest_reconnect("Alice")
    assert res["status"] == "error"
    a.memory.store.assert_not_called()


def test_insights_no_history_is_no_data_and_empty_contact_is_error():
    a = _ca([])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="strong 9/10") as chat:
        assert a.generate_relationship_insights("Alice")["status"] == "no_data"
        assert a.generate_relationship_insights("")["status"] == "error"
    chat.assert_not_called()


def test_analyst_run_tolerates_none_params():
    a = _ca([])
    res = _run(a.run({"type": "x", "params": None}))
    assert res["status"] == "error"


def test_analyst_names_not_logged_and_llm_local_only(logs):
    a = _ca([{"event_type": "message", "content": "please thank you", "timestamp": "2026-05-01T10:00:00Z", "source": "gmail"}])
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value='{"style": "formal"}') as chat:
        a.analyze_communication_style(SECRET_NAME)
        a.suggest_reconnect(SECRET_NAME)
        a.generate_relationship_insights(SECRET_NAME)
    assert SECRET_NAME not in "\n".join(logs)
    assert SECRET_NAME not in str(a.lessons)
    for call in chat.call_args_list:
        assert call.kwargs["allow_cloud"] is False and call.kwargs["sensitive"] is True
