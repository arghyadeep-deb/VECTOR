"""
Tests for the Headroom-inspired context budget manager — closes the two
"Next" items left open in docs/repo_analysis/_PROMOTED_UPGRADES_IMPLEMENTED.md:
  1. persist handles to SQLite/episodic memory (so a restart doesn't lose
     the ability to retrieve a compacted message's original text)
  2. wire it before provider calls (it was built but never actually used
     anywhere — confirmed via grep before this session)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_compact_text_short_text_is_noop():
    from districts.memory_curator.context_budget import ContextBudgetManager

    mgr = ContextBudgetManager(max_message_chars=100)
    text = "short text"
    compact, handle = mgr.compact_text(text)
    assert compact == text
    assert handle is None


def test_compact_text_long_text_creates_handle():
    from districts.memory_curator.context_budget import ContextBudgetManager

    mgr = ContextBudgetManager(max_message_chars=50, head_chars=10, tail_chars=10)
    text = "x" * 500
    compact, handle = mgr.compact_text(text)
    assert handle is not None
    assert len(compact) < len(text)
    assert mgr.retrieve(handle.handle) == text


def test_persist_handle_writes_to_episodic_memory(monkeypatch):
    from districts.memory_curator.context_budget import ContextBudgetManager

    stored = []

    class _FakeEpisodic:
        def store(self, **kwargs):
            stored.append(kwargs)
            return "fake-id"

    monkeypatch.setattr(
        "districts.memory_curator.context_budget.EpisodicMemory", lambda: _FakeEpisodic()
    )

    mgr = ContextBudgetManager(max_message_chars=50, head_chars=10, tail_chars=10)
    text = "y" * 500
    compact, handle = mgr.compact_text(text, label="test", persist=True)

    assert len(stored) == 1
    assert stored[0]["event_type"] == "context_budget_handle"
    assert handle.handle in stored[0]["content"]


def test_persist_handle_never_raises_on_episodic_failure(monkeypatch):
    from districts.memory_curator.context_budget import ContextBudgetManager

    class _BrokenEpisodic:
        def store(self, **kwargs):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "districts.memory_curator.context_budget.EpisodicMemory", lambda: _BrokenEpisodic()
    )

    mgr = ContextBudgetManager(max_message_chars=50, head_chars=10, tail_chars=10)
    # Must not raise even though persistence fails.
    compact, handle = mgr.compact_text("z" * 500, persist=True)
    assert handle is not None


def test_get_context_budget_manager_is_singleton():
    from districts.memory_curator.context_budget import get_context_budget_manager

    a = get_context_budget_manager()
    b = get_context_budget_manager()
    assert a is b


def test_provider_client_compacts_oversized_messages(monkeypatch):
    """The actual wiring: provider_client.chat() must run messages through
    the budget manager before routing — confirmed via a spy, not by making
    a real LLM call."""
    from core.inference import provider_client as mod

    compact_calls = []

    class _SpyManager:
        def compact_messages(self, messages):
            compact_calls.append(messages)
            return messages, []

    monkeypatch.setattr(mod, "get_context_budget_manager", lambda: _SpyManager())

    # Don't actually dispatch to a real provider — patch the routing internals
    # to short-circuit immediately after the compaction step we're testing.
    async def _fail_fast(*a, **kw):
        raise RuntimeError("stop here intentionally — only testing compaction wiring")

    monkeypatch.setattr(mod.ProviderClient, "_try_providers", _fail_fast, raising=False)

    import asyncio
    client = mod.ProviderClient()
    try:
        asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}], caller_id="test"))
    except Exception:
        pass

    assert len(compact_calls) == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
