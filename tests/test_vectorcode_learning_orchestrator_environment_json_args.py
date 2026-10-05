"""Regression for vectorcode/src/learning/intelligence/orchestrator/environment.py's
OrchestratorEnvironment.step():

when action.tool_input doesn't already look like a JSON object (the
common case -- e.g. a plain calculator expression like "2+2"), step()
built the ToolCall's `arguments` string with
``f'{{"expression": {repr(action.tool_input)}}}'``. Python's repr()
produces single-quoted Python literal syntax for strings, not valid
JSON (which requires double quotes) -- but ToolExecutor.execute()
parses `arguments` with json.loads(). This meant every such tool call
was guaranteed to raise json.JSONDecodeError inside the executor,
turning into an "Invalid arguments JSON" error result instead of
actually running the tool -- the orchestrator's RL training/eval loop
never got real tool execution/reward signal for any non-pre-JSON
action.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from vc_core.types import ToolCall, ToolResult
from vc_tools._abc import BaseTool, ToolSpec
from learning.intelligence.orchestrator.environment import OrchestratorEnvironment
from learning.intelligence.orchestrator.types import OrchestratorAction


class _EchoArgsTool(BaseTool):
    """Minimal real tool that just echoes back the parsed params it received."""

    tool_id = "calculator"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="calculator", description="echo params")

    def execute(self, **params) -> ToolResult:
        return ToolResult(tool_name="calculator", content=str(params), success=True)


def test_plain_string_tool_input_reaches_the_tool_as_valid_json(tmp_path):
    tool = _EchoArgsTool()
    env = OrchestratorEnvironment(tools=[tool])
    state = env.reset(task="what is 2+2?")
    action = OrchestratorAction(
        thought="compute it",
        tool_name="calculator",
        tool_input="2+2",
    )

    _, observation = env.step(state, action)

    assert "Invalid arguments JSON" not in observation.content
    assert "2+2" in observation.content


def test_tool_input_with_a_single_quote_still_parses(tmp_path):
    tool = _EchoArgsTool()
    env = OrchestratorEnvironment(tools=[tool])
    state = env.reset(task="q")
    action = OrchestratorAction(
        thought="t",
        tool_name="calculator",
        tool_input="it's 2+2",
    )

    _, observation = env.step(state, action)

    assert "Invalid arguments JSON" not in observation.content


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
