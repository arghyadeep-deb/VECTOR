"""Regression: FrontendDeveloper.scaffold_component()/generate_dashboard_plan()/
answer_question() called core.inference.vectorcode_llm.chat() directly with
no session_hydration_prompt() at all (that chat() wrapper does not inject it
itself) -- same RULE 1 gap fixed in districts/marketing's
amazon_ads_agent.py/attribution_agent.py/sgtm_agent.py this cycle.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.frontend_developer import FrontendDeveloper


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_scaffold_component_hydrates_before_chat():
    agent = FrontendDeveloper()
    with patch("districts.coding.frontend_developer.chat", return_value="code") as mock_chat:
        _run(agent.scaffold_component("Card", ["title: string"]))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


def test_generate_dashboard_plan_hydrates_before_chat():
    agent = FrontendDeveloper()
    with patch("districts.coding.frontend_developer.chat", return_value="plan") as mock_chat:
        _run(agent.generate_dashboard_plan())
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


def test_answer_question_hydrates_before_chat():
    agent = FrontendDeveloper()
    with patch("districts.coding.frontend_developer.chat", return_value="answer") as mock_chat:
        _run(agent.answer_question("how does the dashboard work?"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    # Both the hydration prompt and the original system prompt text must
    # survive the merge.
    assert "FrontendDeveloper" in messages[0]["content"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
