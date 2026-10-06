"""Regression tests for nested gateway session context restoration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.session_context import clear_session_vars, get_session_env, set_session_vars


def test_nested_session_context_restores_enclosing_request() -> None:
    outer = set_session_vars(platform="telegram", chat_id="outer")
    try:
        inner = set_session_vars(platform="whatsapp", chat_id="inner")
        assert get_session_env("VECTOR_SESSION_CHAT_ID") == "inner"
        clear_session_vars(inner)
        assert get_session_env("VECTOR_SESSION_PLATFORM") == "telegram"
        assert get_session_env("VECTOR_SESSION_CHAT_ID") == "outer"
    finally:
        clear_session_vars(outer)


def test_completed_top_level_context_does_not_fall_back_to_stale_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VECTOR_SESSION_CHAT_ID", "stale-process-value")
    tokens = set_session_vars(chat_id="current")
    clear_session_vars(tokens)
    assert get_session_env("VECTOR_SESSION_CHAT_ID") == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
