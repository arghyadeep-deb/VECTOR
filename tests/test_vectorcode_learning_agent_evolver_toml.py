import tomllib
from pathlib import Path

from vectorcode.src.learning.agents.agent_evolver import _write_toml


def test_agent_evolver_escapes_model_generated_text(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    prompt = 'line one\\path\n"injected" = true\r\nnext'

    _write_toml(path, {"agent": {"system_prompt": prompt}})

    with path.open("rb") as file:
        assert tomllib.load(file)["agent"]["system_prompt"] == prompt
