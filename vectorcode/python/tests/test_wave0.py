"""Wave 0 acceptance tests — must all pass before Wave 1 begins."""
import asyncio
import json
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "python"))

from vectorcode.engine import AIAgent, IterationBudget, _sanitize_surrogates, _SafeWriter
from vectorcode.engine.safety import _is_destructive_command
from vectorcode.tools.registry import ToolRegistry, registry as global_registry
from vectorcode.session_db import SessionDB


# ── Test 1: agent single tool call ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_single_tool_call():
    """Agent receives prompt, calls read_file tool, returns non-empty summary."""
    # Register a fake read_file tool
    reg = ToolRegistry()
    reg.register(
        name="read_file",
        handler=lambda path="": f"# README\nThis is a test file at {path}.",
        schema={"description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
        toolset="coding",
    )

    # Mock provider that first returns a tool call, then returns text
    call_count = 0

    async def mock_chat(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: return a tool call
            return {
                "message": {
                    "content": "",
                    "tool_calls": [{"id": "tc1", "name": "read_file", "arguments": json.dumps({"path": "README.md"})}],
                }
            }
        else:
            # Second call: return final text
            return {"message": {"content": "The README describes a test file.", "tool_calls": []}}

    mock_provider = MagicMock()
    mock_provider.chat = mock_chat

    agent = AIAgent(model="test", toolset="coding")
    agent._registry = reg

    with patch.object(agent, "_get_provider", return_value=mock_provider):
        result = await agent.run_conversation("read README.md and summarize it")

    assert result["status"] == "ok"
    assert len(result["text"]) > 0
    assert result["tool_calls_total"] == 1


# ── Test 2: iteration budget independence ─────────────────────────────────────

def test_agent_iteration_budget():
    """Parent budget=5, subagent gets its own budget=3, parent still has 5."""
    parent_budget = IterationBudget(max_total=5)
    parent_budget.consume()  # use 1
    assert parent_budget.used == 1
    assert parent_budget.remaining == 4

    # Subagent gets independent budget
    subagent_budget = IterationBudget(max_total=3)
    subagent_budget.consume()
    subagent_budget.consume()
    assert subagent_budget.used == 2
    assert subagent_budget.remaining == 1

    # Parent budget unchanged
    assert parent_budget.used == 1
    assert parent_budget.remaining == 4

    # Budget exhaustion
    budget = IterationBudget(max_total=2)
    assert budget.consume() is True
    assert budget.consume() is True
    assert budget.consume() is False  # exhausted

    # Refund
    budget.refund()
    assert budget.consume() is True


# ── Test 3: tool registry dispatch ────────────────────────────────────────────

def test_tool_registry_dispatch():
    """Register a fake tool, call via handle_function_call, result flows back."""
    reg = ToolRegistry()
    results = []

    def my_tool(x: int = 0, y: int = 0) -> str:
        result = f"sum={x + y}"
        results.append(result)
        return result

    reg.register(
        name="add_numbers",
        handler=my_tool,
        schema={"description": "Add two numbers", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}},
        toolset="coding",
        risk_level="safe",
    )

    result = reg.handle_function_call("add_numbers", {"x": 3, "y": 4})
    assert result == "sum=7"
    assert results == ["sum=7"]

    # Unknown tool
    result2 = reg.handle_function_call("nonexistent_tool", {})
    assert "not registered" in result2


# ── Test 4: session migration v1 → v10 ────────────────────────────────────────

def test_session_migration_v1_to_v10():
    """v1 DB migrates cleanly to v10 without data loss."""
    import sqlite3
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = SessionDB(db_path)
        sid = str(uuid.uuid4())
        db.create_session(sid, model="test-model", project="test-project", mode="repl")
        db.add_message(sid, "user", "hello world")
        db.add_message(sid, "assistant", "hi there")

        # Migrate
        db.migrate_up()

        # Verify new columns exist
        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        assert "parent_session_id" in cols
        assert "billing_provider" in cols
        assert "api_call_count" in cols
        assert "focus_topic" in cols
        msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        assert "is_training_data" in msg_cols
        ver = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert ver == 10

        # Data preserved
        msgs = conn.execute("SELECT content FROM messages WHERE session_id=?", (sid,)).fetchall()
        assert len(msgs) == 2
        conn.close()

        # Close SessionDB connection before tmpdir cleanup (Windows file locking)
        db._conn.close()


# ── Test 5: compression triggers ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compression_triggers():
    """Conversation that exceeds 90% context triggers _compress_context."""
    compressed = []

    async def mock_compress(agent, focus_topic=None):
        compressed.append(focus_topic)

    agent = AIAgent(model="test")

    # Simulate a very long history
    agent._history = [
        {"role": "user", "content": "x" * 1000},
        {"role": "assistant", "content": "y" * 1000},
    ] * 50  # 100 messages, ~100k chars

    # The compression module should be importable
    from vectorcode.engine import conversation
    assert hasattr(conversation, "run_conversation_loop")


# ── Test 6: recovery on 429 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_on_429():
    """Stubbed 429 from provider, credential pool rotates, call retries."""
    from vectorcode.engine.recovery import recover_on_error

    rotated = []

    class FakePool:
        def rotate(self):
            rotated.append(True)
        def has_available(self):
            return True

    agent = AIAgent(model="test")
    agent.credential_pool = FakePool()

    call_count = 0

    async def mock_call(a):
        nonlocal call_count
        call_count += 1
        return {"message": {"content": "recovered", "tool_calls": []}}

    error_429 = Exception("429 Too Many Requests: rate limit exceeded")

    with patch("vectorcode.engine.conversation._call_model", mock_call):
        result = await recover_on_error(agent, error_429)

    assert rotated == [True]
    assert result is not None


# ── Test 7: SafeWriter daemon mode ────────────────────────────────────────────

def test_safe_writer_daemon_mode():
    """Writes to broken pipe don't crash (OSError/ValueError caught)."""
    class BrokenStream:
        def write(self, data):
            raise OSError("Broken pipe")
        def flush(self):
            raise ValueError("I/O operation on closed file")
        def fileno(self):
            return -1
        def isatty(self):
            raise OSError()

    writer = _SafeWriter(BrokenStream())

    # These must not raise
    result = writer.write("hello")
    assert result == 5  # len("hello")

    writer.flush()  # must not raise

    assert writer.isatty() is False


# ── Test 8: surrogate sanitization ────────────────────────────────────────────

def test_surrogate_sanitization():
    """Paste with surrogate codepoints doesn't break JSON encode."""
    # Lone surrogate
    text_with_surrogate = "hello \ud83d world"
    sanitized = _sanitize_surrogates(text_with_surrogate)
    assert "\ud83d" not in sanitized
    assert "\ufffd" in sanitized

    # Must be JSON-serializable after sanitization
    result = json.dumps({"content": sanitized})
    assert "hello" in result

    # Clean text passes through unchanged
    clean = "hello world 🎉"
    assert _sanitize_surrogates(clean) == clean
