"""Regression tests for the external VECTOR eval runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from vectorcode.src.evals.backends.external._runners import vector_runner


def test_vector_runner_parses_output_path_and_reports_missing_agent_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "result.json"
    monkeypatch.delenv("VECTOR_AGENT_PATH", raising=False)
    monkeypatch.delenv("VECTOR_EVAL_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vector_runner.py",
            "--task",
            "test task",
            "--model",
            "test-model",
            "--base-url",
            "http://127.0.0.1:8000",
            "--output-json",
            str(output_path),
        ],
    )

    assert vector_runner.main() == 2
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["error"] == "VECTOR_AGENT_PATH not set"


def test_vector_runner_loads_agent_from_configured_path_without_cli_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "result.json"
    agent_path = tmp_path / "agent"
    agent_path.mkdir()
    (agent_path / "run_agent.py").write_text(
        "class AIAgent:\n"
        "    def __init__(self, **kwargs):\n"
        "        assert kwargs['api_key'] == 'secret-from-env'\n"
        "        self.session_prompt_tokens = 0\n"
        "        self.session_completion_tokens = 0\n"
        "    def run_conversation(self, task, **kwargs):\n"
        "        return {'final_response': 'ok', 'messages': []}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VECTOR_AGENT_PATH", str(agent_path))
    monkeypatch.setenv("VECTOR_EVAL_API_KEY", "secret-from-env")
    monkeypatch.delitem(sys.modules, "run_agent", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vector_runner.py",
            "--task",
            "test task",
            "--model",
            "test-model",
            "--base-url",
            "http://127.0.0.1:8000",
            "--output-json",
            str(output_path),
        ],
    )

    assert vector_runner.main() == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["content"] == "ok"
    assert result["error"] is None


def test_vector_backend_never_places_api_key_on_command_line() -> None:
    source = (
        Path(vector_runner.__file__).parents[1] / "vector_agent.py"
    ).read_text(encoding="utf-8")
    assert '"--api-key"' not in source
    assert 'env["VECTOR_EVAL_API_KEY"] = self._api_key' in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
