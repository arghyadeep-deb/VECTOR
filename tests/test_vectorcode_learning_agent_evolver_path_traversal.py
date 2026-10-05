"""Regression for vectorcode/src/learning/agents/agent_evolver.py:

AgentConfigEvolver.write_config()/list_versions()/rollback() all built
filesystem paths from a caller-supplied agent_name with zero
confinement. agent_name ultimately traces back to a stored Trace's
``agent`` field (learning_orchestrator.py calls
``evolver.analyze()`` -> ``rec["recommended_agent"]`` ->
``evolver.write_config(agent_name, ...)``) -- a value like
"../../../../.ssh/authorized_keys" would let write_config's
``path.write_text()`` call write outside config_dir entirely, and
list_versions/rollback's glob + shutil.copy2 calls read/copy outside
history_dir. This is a write primitive, not just a read.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest

from learning.agents.agent_evolver import AgentConfigEvolver


def _evolver(tmp_path):
    config_dir = tmp_path / "configs"
    return AgentConfigEvolver(trace_store=None, config_dir=config_dir)


def test_write_config_rejects_path_traversal(tmp_path):
    evolver = _evolver(tmp_path)
    with pytest.raises(ValueError):
        evolver.write_config("../../../../escaped", tools=[])
    # Nothing should have escaped the config dir.
    assert not (tmp_path / "escaped.toml").exists()


def test_write_config_rejects_separator_containing_name(tmp_path):
    evolver = _evolver(tmp_path)
    with pytest.raises(ValueError):
        evolver.write_config("foo/bar", tools=[])


def test_list_versions_rejects_path_traversal(tmp_path):
    evolver = _evolver(tmp_path)
    with pytest.raises(ValueError):
        evolver.list_versions("../../escaped")


def test_write_config_still_works_for_a_real_agent_name(tmp_path):
    evolver = _evolver(tmp_path)
    path = evolver.write_config("simple", tools=["web_search"], max_turns=12)
    assert path.exists()
    assert path.name == "simple.toml"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
