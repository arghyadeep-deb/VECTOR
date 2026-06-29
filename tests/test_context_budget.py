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


def test_persist_handle_writes_to_capped_non_fts_table(monkeypatch, tmp_path):
    """Persisted handles go to a dedicated, capped context_budget_handles table
    — NOT into FTS-indexed episodic_memory. Indexing these tens-of-KB prompt
    offloads is what ballooned the DB to multiple GB; this is the regression
    guard. Also verifies durability: a fresh manager (cold in-memory store)
    still retrieves the original text from the table."""
    import core.memory.episodic as ep
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "mem.db"))
    ep.close_db_connection()
    try:
        from districts.memory_curator.context_budget import ContextBudgetManager

        mgr = ContextBudgetManager(max_message_chars=50, head_chars=10, tail_chars=10)
        text = "y" * 500
        compact, handle = mgr.compact_text(text, label="test", persist=True)

        # Durability across a "restart": fresh instance, empty in-memory store.
        fresh = ContextBudgetManager()
        assert fresh.retrieve(handle.handle) == text

        with ep.get_temp_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM context_budget_handles WHERE handle=?", (handle.handle,)
            )
            assert cur.fetchone()[0] == 1
            # The whole point: it must never land in FTS-indexed episodic memory.
            cur.execute(
                "SELECT COUNT(*) FROM episodic_memory WHERE event_type='context_budget_handle'"
            )
            assert cur.fetchone()[0] == 0
    finally:
        ep.close_db_connection()


def test_persist_handle_caps_table_size(monkeypatch, tmp_path):
    """The handle table is bounded — it can't grow without limit."""
    import core.memory.episodic as ep
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "mem.db"))
    ep.close_db_connection()
    try:
        from districts.memory_curator.context_budget import ContextBudgetManager

        mgr = ContextBudgetManager(max_message_chars=50, head_chars=10, tail_chars=10)
        mgr._PERSIST_CAP = 5  # shrink the cap for the test
        for i in range(20):
            mgr.compact_text(f"{i:03d}-" + "q" * 500, label=f"m{i}", persist=True)
        with ep.get_temp_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM context_budget_handles")
            assert cur.fetchone()[0] <= 5
    finally:
        ep.close_db_connection()


def test_persist_handle_never_raises_on_db_failure(monkeypatch, tmp_path):
    import core.memory.episodic as ep
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "mem.db"))
    ep.close_db_connection()
    try:
        from districts.memory_curator.context_budget import ContextBudgetManager

        def _boom(*a, **k):
            raise RuntimeError("db unavailable")

        # _persist_handle imports get_temp_cursor from the episodic module at
        # call time, so patching it there breaks the persist path.
        monkeypatch.setattr(ep, "get_temp_cursor", _boom)

        mgr = ContextBudgetManager(max_message_chars=50, head_chars=10, tail_chars=10)
        # Must not raise even though persistence fails.
        compact, handle = mgr.compact_text("z" * 500, persist=True)
        assert handle is not None
    finally:
        ep.close_db_connection()


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
        def compact_messages(self, messages, persist=False):
            compact_calls.append(messages)
            return messages, []

    monkeypatch.setattr(
        "districts.memory_curator.context_budget.get_context_budget_manager",
        lambda: _SpyManager(),
    )

    # Don't actually dispatch to a real provider — patch the routing internals
    # to short-circuit immediately after the compaction step we're testing.
    async def _fail_fast(*a, **kw):
        raise RuntimeError("stop here intentionally — only testing compaction wiring")

    monkeypatch.setattr(mod.ProviderClient, "_call_with_retry", _fail_fast)

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
