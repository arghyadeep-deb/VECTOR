"""Regression: CodeConductorAgent.run()'s read_files/write_file branches used
p.get("cwd", self._cwd), which only falls back to self._cwd when the "cwd"
key is ABSENT from params -- a caller-supplied {"cwd": null} (or "") in the
Governor-dispatched task JSON passed through as a real None/empty cwd,
disabling read_files()/write_file()'s path confinement entirely instead of
falling back to the real configured repo workspace.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.code_conductor_agent import CodeConductorAgent


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_write_file_explicit_null_cwd_still_confined_to_agent_workspace(tmp_path):
    agent = CodeConductorAgent()
    agent._cwd = str(tmp_path)
    outside_target = str(tmp_path.parent / "escape.py")

    result = _run(agent.run({"params": {
        "action": "write_file",
        "cwd": None,
        "file": outside_target,
        "content": "x = 1\n",
    }}))

    assert result["status"] == "error"
    assert not Path(outside_target).exists()


def test_read_files_explicit_null_cwd_still_confined_to_agent_workspace(tmp_path):
    agent = CodeConductorAgent()
    agent._cwd = str(tmp_path)
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("top secret")

    result = _run(agent.run({"params": {
        "action": "read_files",
        "cwd": None,
        "paths": [str(outside)],
    }}))

    assert result["files"] == []


def test_write_file_without_cwd_key_still_defaults_to_agent_workspace(tmp_path):
    agent = CodeConductorAgent()
    agent._cwd = str(tmp_path)

    result = _run(agent.run({"params": {
        "action": "write_file",
        "file": "inside.py",
        "content": "x = 1\n",
    }}))

    assert result["status"] == "ok"
    assert (tmp_path / "inside.py").exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
