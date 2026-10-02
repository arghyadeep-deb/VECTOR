"""Regression for districts/coding/minimal_change_engineer.py's two bugs
found in the Phase 3 audit:
1. analyze_change_scope() read any caller-supplied path with no
   confinement, directly Governor-dispatchable via run()'s
   task_type == "analyze" -- same bug class fixed in code_reviewer.py/
   architect_bot.py/bug_hunter.py/code_explorer.py this cycle.
2. answer_question()/run()'s diff_prompt call_llm branch called chat()
   with no session_hydration_prompt() -- same RULE 1 gap fixed in
   frontend_developer.py/gui_automation_agent.py this cycle.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.minimal_change_engineer import MinimalChangeEngineer


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_analyze_change_scope_rejects_path_outside_repo(tmp_path):
    agent = MinimalChangeEngineer()
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'real-secret'\n")
    result = agent.analyze_change_scope(str(outside), "fix a bug")
    assert result["scope_risk"] == "unknown"
    assert "outside repo" in result["suggestion"].lower() or "not a .py file" in result["suggestion"].lower()


def test_analyze_change_scope_still_works_on_real_in_repo_file():
    agent = MinimalChangeEngineer()
    real_py = str(Path(__file__).resolve())
    result = agent.analyze_change_scope(real_py, "fix a test")
    assert result["scope_risk"] != "unknown"


def test_answer_question_hydrates_before_chat():
    agent = MinimalChangeEngineer()
    with patch("districts.coding.minimal_change_engineer.chat", return_value="answer") as mock_chat:
        _run(agent.answer_question("what do you do?"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "MinimalChangeEngineer" in messages[0]["content"]


def test_diff_prompt_call_llm_hydrates_before_chat():
    agent = MinimalChangeEngineer()
    with patch("districts.coding.minimal_change_engineer.chat", return_value="diff") as mock_chat:
        _run(agent.run({
            "type": "diff_prompt",
            "task": "add a type annotation",
            "code": "def f(x):\n    return x\n",
            "call_llm": True,
        }))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
