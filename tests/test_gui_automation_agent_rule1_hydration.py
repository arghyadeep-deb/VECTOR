"""Regression: GUIAutomationAgent.click_screen()/_answer_query() called
core.inference.vectorcode_llm.chat() directly with no
session_hydration_prompt() at all -- same RULE 1 gap fixed in
districts/marketing's/frontend_developer.py's LLM calls this cycle.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.gui_automation_agent import GUIAutomationAgent


def _run(coro):
    return asyncio.run(coro)


def test_answer_query_hydrates_before_chat():
    agent = GUIAutomationAgent()
    with patch("core.inference.vectorcode_llm.chat", return_value="answer") as mock_chat:
        _run(agent._answer_query("what can you do?"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "GUIAutomationAgent" in messages[0]["content"]


def test_click_screen_hydrates_before_chat():
    agent = GUIAutomationAgent()
    fake_operator = AsyncMock()
    fake_operator.screenshot = AsyncMock(return_value={"width": 100, "height": 100, "base64": "x"})
    fake_operator.execute = AsyncMock(return_value={})

    with patch("districts.coding.gui_automation_agent.VisionOperator", return_value=fake_operator), \
         patch("core.inference.vectorcode_llm.chat", return_value="click(start_box='<point>5 5</point>')") as mock_chat, \
         patch("districts.coding.gui_automation_agent.action_parser", return_value=[{"start_coords": (5, 5)}]):
        _run(agent.click_screen("the save button"))

    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "GUI element locator" in messages[0]["content"]
    assert len(messages[0]["content"]) > len("You are a GUI element locator. Respond with only an action string.")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
