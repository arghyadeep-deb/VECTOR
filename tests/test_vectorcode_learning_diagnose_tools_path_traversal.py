"""Regression for vectorcode/src/learning/distillation/diagnose/tools.py:

build_diagnostic_tools()'s get_agent_prompt tool built
``vector_home / "agents" / agent_name / "system_prompt.md"`` with zero
confinement check. agent_name is a tool-call argument chosen by the
*teacher LLM* in a tool-calling loop (TeacherAgent.run() in
teacher_agent.py calls ``tool.fn(**tc_args)`` with args parsed straight
out of the model's tool call) -- a value like "../../../../etc" would
walk the read outside ``vector_home/agents/``, breaking this module's
own documented invariant that its tools are "read-only relative to the
user's config".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from learning.distillation.diagnose.tools import build_diagnostic_tools


def _tools(vector_home):
    built = build_diagnostic_tools(
        trace_store=None,
        config={"config_path": vector_home / "config.toml", "vector_home": vector_home},
        benchmark_samples=[],
        student_runner=None,
        teacher_engine=None,
        teacher_model="m",
        judge=None,
        session_id="s1",
    )
    return {t.name: t for t in built}


def test_get_agent_prompt_rejects_path_traversal(tmp_path):
    secret = tmp_path / "system_prompt.md"
    secret.write_text("TOP SECRET", encoding="utf-8")
    (tmp_path / "agents").mkdir()

    tools = _tools(tmp_path)
    result = tools["get_agent_prompt"].fn(agent_name="../")

    assert "TOP SECRET" not in result
    assert "Invalid agent_name" in result


def test_get_agent_prompt_rejects_separator_containing_name(tmp_path):
    (tmp_path / "agents").mkdir()
    tools = _tools(tmp_path)
    result = tools["get_agent_prompt"].fn(agent_name="foo/../../bar")
    assert "Invalid agent_name" in result


def test_get_agent_prompt_still_works_for_a_real_agent(tmp_path):
    agent_dir = tmp_path / "agents" / "simple"
    agent_dir.mkdir(parents=True)
    (agent_dir / "system_prompt.md").write_text("You are simple.", encoding="utf-8")

    tools = _tools(tmp_path)
    result = tools["get_agent_prompt"].fn(agent_name="simple")
    assert result == "You are simple."


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
