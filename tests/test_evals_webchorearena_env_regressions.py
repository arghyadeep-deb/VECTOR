"""Regression tests for WebChoreArena evaluation helpers."""

from loguru import logger as loguru_logger

from core.loop.context_engine import ContextEngine
from vectorcode.src.evals.backends.vector_direct import VectorDirectBackend
from vectorcode.src.evals.execution.webchorearena_env import (
    LOGGER,
    WebChoreArenaTaskEnv,
)


def test_judge_uses_concrete_backend_with_hydration_and_closes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        ContextEngine,
        "session_hydration_prompt",
        lambda self, context: "hydrated context",
    )
    monkeypatch.setattr(
        VectorDirectBackend,
        "__init__",
        lambda self, engine_key=None: captured.update(engine_key=engine_key),
    )

    def fake_generate(self, prompt, **kwargs):
        captured.update(prompt=prompt, **kwargs)
        return "correct"

    monkeypatch.setattr(VectorDirectBackend, "generate", fake_generate)
    monkeypatch.setattr(
        VectorDirectBackend,
        "close",
        lambda self: captured.update(closed=True),
    )

    result = WebChoreArenaTaskEnv({})._call_judge("grade this")

    assert result == "correct"
    assert captured["system"] == "hydrated context"
    assert captured["closed"] is True


def test_webchorearena_env_uses_loguru() -> None:
    assert LOGGER is loguru_logger


if __name__ == "__main__":
    test_webchorearena_env_uses_loguru()
