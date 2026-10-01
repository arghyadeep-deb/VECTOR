"""Regression: vectorcode/src/tools/direct_executor.py's
DirectTaskExecutor._execute_internal() checked `any(t["type"] == "bash" for t
in tools)` but then always executed tools[0] regardless of which entry
actually matched -- if the bash tool wasn't first in the list, it ran the
wrong tool's (possibly nonexistent) "command" key instead. Zero real callers
exist today (confirmed via repo-wide grep); fixed anyway since the fix is
narrow/mechanical.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.tools.direct_executor import DirectTaskExecutor


def test_finds_bash_tool_when_not_first_in_list():
    executor = DirectTaskExecutor()
    tools = [
        {"type": "other"},
        {"type": "bash", "command": "echo hello"},
    ]
    result = asyncio.run(executor.execute("task", tools))
    assert result.validated is True
    assert "hello" in result.output


def test_still_works_when_bash_tool_is_first():
    executor = DirectTaskExecutor()
    tools = [{"type": "bash", "command": "echo world"}]
    result = asyncio.run(executor.execute("task", tools))
    assert "world" in result.output


def test_no_bash_tool_falls_back_to_generic_execution():
    executor = DirectTaskExecutor()
    tools = [{"type": "other"}]
    result = asyncio.run(executor.execute("my task", tools))
    assert "Executed: my task" in result.output


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
