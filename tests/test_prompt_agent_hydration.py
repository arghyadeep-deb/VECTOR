"""Regression test for a real RULE 1 gap in the shared PromptAgent base class.

Review finding (P8 self-dev package, second round; verified real by Claude 2026-09-29):
PromptAgent.ask() -- the shared LLM call site for every .md-driven district citizen that
never overrides run()/ask() (12 agents across coding/research/finance/qa/governance/
data_analytics, e.g. finance-bookkeeper-controller.md self-loaded by FinanceSwarm) -- built
its message list from only the agent's own system prompt plus context/query, with NO
session_hydration_prompt() call at all. Fixed once in the shared base class rather than
per-agent, since every PromptAgent subclass shares this exact code path.

Per .claude/rules/testing.md: session_hydration_prompt() itself is never mocked below --
only the external LLM transport is, so the real ContextEngine output is what gets asserted on.
"""
from __future__ import annotations

import asyncio

import pytest

from core.city.prompt_agent import PromptAgent


@pytest.mark.asyncio
async def test_prompt_agent_ask_hydrates_session_before_llm_call(monkeypatch, tmp_path):
    md_path = tmp_path / "test-persona.md"
    md_path.write_text(
        "---\ndescription: Test persona\n---\nYou are a test persona for VECTOR.\n",
        encoding="utf-8",
    )
    agent = PromptAgent(str(md_path), "test_persona_hydration_001", "coding")

    captured = {}

    def fake_chat(model, messages, timeout=45.0, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr("core.inference.vectorcode_llm.chat", fake_chat)
    result = await agent.ask("what is the current status?")

    assert result == "ok"
    messages = captured["messages"]
    system_messages = [m["content"] for m in messages if m["role"] == "system"]
    assert len(system_messages) >= 2, "expected a hydration system message plus the persona's own system prompt"
    assert "[SESSION CONTEXT" in system_messages[0]  # real ContextEngine().session_hydration_prompt() output
    assert "test persona" in system_messages[1].lower()  # the agent's own .md-derived system prompt, unchanged


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
