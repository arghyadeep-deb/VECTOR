"""Regression tests for the external OpenClaw evaluation backend."""

from pathlib import Path
from types import SimpleNamespace

from vectorcode.src.evals.backends.external import openclaw


def test_openclaw_credentials_are_passed_via_environment(monkeypatch):
    """Secrets must not be observable in the subprocess argument vector."""
    captured = {}

    def fake_run_one_shot(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            parsed_json={"content": "ok"},
            latency_seconds=0.1,
            energy_joules=None,
            peak_power_w=None,
            error=None,
        )

    monkeypatch.setattr(openclaw, "run_one_shot", fake_run_one_shot)

    backend = openclaw.OpenClawBackend.__new__(openclaw.OpenClawBackend)
    backend._base_url = "https://inference.invalid/v1"
    backend._api_key = "super-secret-key"
    backend._timeout = 30.0
    backend._entry = SimpleNamespace(
        node_executable="node",
        runner_script="runner.mjs",
        path=Path("openclaw"),
        pinned_commit="deadbeef",
    )

    result = backend.generate_full("task", model="model")

    assert result["content"] == "ok"
    assert "super-secret-key" not in captured["cmd"]
    assert "https://inference.invalid/v1" not in captured["cmd"]
    assert captured["env"]["OPENCLAW_API_KEY"] == "super-secret-key"
    assert captured["env"]["OPENCLAW_BASE_URL"] == "https://inference.invalid/v1"


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
