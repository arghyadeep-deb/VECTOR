"""Regression for two bugs found in districts/coding/test_writer.py during
the Phase 3 whole-repo audit (2026-10-02):

1. write_tests_for_file() read any caller-supplied path (reachable via
   Governor dispatch -- run()'s params["file"]) with zero confinement, then
   sent its content into an LLM prompt (_build_llm_prompt). Same bug class
   as architect_bot.py/bug_hunter.py/code_explorer.py's fixes this cycle.

2. _get_llm_test_suggestions()/_answer_query() both called
   ProviderClient.chat() directly with no session_hydration_prompt() --
   same RULE 1 gap fixed in 7 other files this cycle. Confirmed
   ProviderClient.chat()'s own docstring pipeline (personality injection,
   rate limit, routing, retry, consistency) never mentions hydration.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.test_writer import TestWriter


def _run(coro):
    return asyncio.run(coro)


def test_write_tests_for_file_rejects_path_outside_repo(tmp_path):
    writer = TestWriter()
    outside = tmp_path / "secret.py"
    outside.write_text("def f(): pass\n")
    try:
        writer.write_tests_for_file(str(outside))
        assert False, "expected ValueError for out-of-repo path"
    except ValueError as e:
        assert "outside repo" in str(e)


def test_write_tests_for_file_rejects_non_py_suffix():
    writer = TestWriter()
    inside_non_py = Path(__file__).resolve().parent.parent / "docs" / "OPEN_ISSUES.md"
    try:
        writer.write_tests_for_file(str(inside_non_py))
        assert False, "expected ValueError for non-.py path"
    except ValueError as e:
        assert "not .py" in str(e)


def test_get_llm_test_suggestions_hydrates_before_chat():
    writer = TestWriter()
    fake_result = MagicMock()
    fake_result.content = "generated"

    async def fake_chat(*args, **kwargs):
        return fake_result

    with patch("core.inference.provider_client.ProviderClient.chat", side_effect=fake_chat) as mock_chat:
        writer._get_llm_test_suggestions("analyze this module")
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


def test_answer_query_hydrates_before_chat():
    writer = TestWriter()
    fake_result = MagicMock()
    fake_result.content = "answer"

    async def fake_chat(*args, **kwargs):
        return fake_result

    with patch("core.inference.provider_client.ProviderClient.chat", side_effect=fake_chat) as mock_chat:
        _run(writer._answer_query("what does this agent do?"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0
    # the role-specific TestWriter system prompt must still be present too
    assert any("TestWriter" in m.get("content", "") for m in messages if m["role"] == "system")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
