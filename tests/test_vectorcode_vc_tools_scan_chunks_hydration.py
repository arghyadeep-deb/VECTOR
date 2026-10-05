"""Regression test: scan_chunks.py must hydrate before calling the LLM (Rule 1).

ScanChunksTool.execute() called self._engine.generate() with only a single USER
message and no context_engine.session_hydration_prompt() call, violating
VECTOR's non-negotiable Rule 1 ("context_engine.session_hydration_prompt()
before EVERY LLM call -- no exceptions"). The sibling llm_tool.py handles the
identical self._engine.generate() call correctly by prepending a SYSTEM
message built from ContextEngine().session_hydration_prompt().
"""

from __future__ import annotations

import sqlite3

import pytest

from vectorcode.src.vc_core.types import Role
from vectorcode.src.vc_tools.scan_chunks import ScanChunksTool


class _FakeStore:
    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            "CREATE TABLE knowledge_chunks ("
            "content TEXT, source TEXT, title TEXT, author TEXT,"
            " doc_type TEXT, timestamp TEXT)"
        )
        self._conn.execute(
            "INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?, ?, ?)",
            ("some chunk text", "granola", "Meeting Notes", "Alice", "document", "2026-01-01"),
        )
        self._conn.commit()


class _RecordingEngine:
    def __init__(self) -> None:
        self.calls: list[list] = []

    def generate(self, messages, model="", max_tokens=None):
        self.calls.append(list(messages))
        return {"content": "NOTHING_RELEVANT"}


@pytest.fixture
def tool_and_engine():
    engine = _RecordingEngine()
    tool = ScanChunksTool(store=_FakeStore(), engine=engine, model="test-model")
    return tool, engine


def test_scan_chunks_hydrates_before_generate(tool_and_engine):
    tool, engine = tool_and_engine
    tool.execute(question="what did Alice say?")

    assert engine.calls, "engine.generate() was never called"
    first_call_messages = engine.calls[0]
    assert first_call_messages, "generate() was called with no messages"
    assert first_call_messages[0].role == Role.SYSTEM, (
        "first message must be a SYSTEM hydration message per Rule 1 "
        "(context_engine.session_hydration_prompt() before every LLM call)"
    )


def test_scan_chunks_hydration_contains_query(tool_and_engine):
    tool, engine = tool_and_engine
    tool.execute(question="what did Alice say?")

    hydration_content = engine.calls[0][0].content
    assert isinstance(hydration_content, str)
    assert len(hydration_content) > 0
