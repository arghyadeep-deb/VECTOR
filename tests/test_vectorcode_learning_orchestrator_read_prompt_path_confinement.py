"""Regression for vectorcode/src/learning/distillation/orchestrator.py's
DistillationOrchestrator._read_prompt():

``target`` is passed as ``prompt_reader(edit.target)`` from
plan/prompt_diff.py, i.e. it comes directly from the teacher/planner LLM's
edit output -- an untrusted, model-produced string. The method split it on
"." and used the second segment as ``agent_name`` directly in
``self._home / "agents" / agent_name / "system_prompt.md"`` with zero path
confinement. Note a literal ".."-based traversal can't actually be
smuggled through parts[1] here, since any ".." substring is itself
composed of the "." delimiter the code splits on. The real escape is
pathlib's absolute-path-override behavior: if agent_name is an absolute
path, `base / agent_name` discards `base` entirely (confirmed live:
``Path("a/b") / "C:/x" / "y" == Path("C:/x/y")``), so an absolute
agent_name reads from anywhere on the filesystem the agents/ tree's
caller can specify. The identical unconfined-identifier shape was
already found and fixed as a *write* primitive in
execute/appliers/agent.py; this is the *read*-path counterpart.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from learning.distillation.orchestrator import DistillationOrchestrator


def _orchestrator(vector_home: Path) -> DistillationOrchestrator:
    return DistillationOrchestrator(
        teacher_engine=None,
        teacher_model="mock",
        trace_store=None,
        benchmark_samples=[],
        student_runner=None,
        judge=None,
        session_store=None,
        checkpoint_store=None,
        vector_home=vector_home,
    )


def test_read_prompt_confines_agent_name_to_agents_dir(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "simple").mkdir()
    (agents_dir / "simple" / "system_prompt.md").write_text(
        "the real prompt", encoding="utf-8"
    )

    # Normal case still works.
    assert orch._read_prompt("agents.simple.system_prompt") == "the real prompt"


def test_read_prompt_rejects_absolute_path_agent_name_escape(tmp_path: Path):
    """pathlib's `/` operator discards the left side entirely when the right
    side is an absolute path -- so an agent_name that IS an absolute path
    (no ".." or dots required) fully overrides self._home/"agents" and
    reads from wherever that absolute path points. Confirmed live:
    Path("a/b") / "C:/x" / "y" == Path("C:/x/y"), not "a/b/C:/x/y".
    """
    orch = _orchestrator(tmp_path)
    (tmp_path / "agents").mkdir()

    # Plant a secret file OUTSIDE the agents/ tree entirely.
    escape_dir = tmp_path / "escaped"
    escape_dir.mkdir()
    (escape_dir / "system_prompt.md").write_text("TOP SECRET", encoding="utf-8")

    # agent_name is the absolute path to escape_dir -- no dots in it, so
    # target.split(".") won't fragment it.
    malicious_target = f"agents.{escape_dir}.system_prompt"
    result = orch._read_prompt(malicious_target)
    assert result == ""
    assert "TOP SECRET" not in result


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
