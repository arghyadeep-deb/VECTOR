"""Regression for vectorcode/src/cli/chat_cmd.py: the `vector chat` REPL
seeded its conversation `history` with an optional user-supplied
--system prompt but no mandatory context_engine.session_hydration_prompt()
call (CLAUDE.md Rule 1: "before EVERY LLM call -- no exceptions"). Since
`history` is the exact list sent to engine.generate()/agent.run() on every
turn, a chat session invoked without --system ran with zero session
hydration for its entire lifetime.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from click.testing import CliRunner

from vectorcode.src.cli.chat_cmd import chat
from vectorcode.src.vc_core.types import Role


def _run_chat_once(monkeypatch, system_prompt_flag=None):
    """Drive the `chat` click command through exactly one /quit turn and
    capture the `history` list it built, without touching a real engine."""
    captured = {}

    class FakeEngine:
        def generate(self, history, model=None):
            captured["history"] = list(history)
            return {"content": "ok"}

    config = SimpleNamespace(
        intelligence=SimpleNamespace(default_model="fake-model"),
        agent=SimpleNamespace(default_agent="none", max_turns=5, tools=None),
        tools=SimpleNamespace(enabled=None),
    )

    monkeypatch.setattr("vectorcode.src.cli.chat_cmd.load_config", lambda: config)
    monkeypatch.setattr(
        "vectorcode.src.engine.get_engine", lambda cfg, key: ("fake", FakeEngine())
    )
    monkeypatch.setattr(
        "vectorcode.src.intelligence.register_builtin_models", lambda: None
    )
    monkeypatch.setattr(
        "vectorcode.src.cli._bg_state.get_status", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        "vectorcode.src.cli._chat_banner.render_startup_banner", lambda status: ""
    )

    class _NullDispatcher:
        def __init__(self, status):
            pass

        def diff(self, status):
            return []

    monkeypatch.setattr(
        "vectorcode.src.cli._chat_notifications.NotificationDispatcher",
        _NullDispatcher,
    )

    runner = CliRunner()
    args = ["--engine", "fake", "--model", "fake-model"]
    if system_prompt_flag:
        args += ["--system", system_prompt_flag]
    result = runner.invoke(chat, args, input="hello\n/quit\n")
    assert result.exit_code == 0, result.output
    return captured


def test_chat_history_is_seeded_with_session_hydration_even_without_system_flag(
    monkeypatch,
):
    hydration_text = "HYDRATION-MARKER-xyz"
    monkeypatch.setattr(
        "core.loop.context_engine.ContextEngine.session_hydration_prompt",
        lambda self, extra_context=None: hydration_text,
    )

    captured = _run_chat_once(monkeypatch)
    history = captured["history"]

    system_messages = [m for m in history if m.role == Role.SYSTEM]
    assert any(m.content == hydration_text for m in system_messages), (
        "chat REPL history must always include the session hydration prompt, "
        "even when --system is not supplied"
    )
