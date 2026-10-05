"""Regression coverage for eval logging compatibility."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from loguru import logger


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    ROOT / "vectorcode/src/evals/cli.py",
    ROOT / "vectorcode/src/evals/core/config.py",
    ROOT / "vectorcode/src/evals/datasets/deepplanning.py",
    ROOT / "vectorcode/src/evals/datasets/workarena.py",
)


@pytest.mark.parametrize("module_path", MODULES)
def test_reviewed_eval_modules_use_loguru_compatible_calls(module_path: Path) -> None:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "logging.getLogger" not in source
    assert "exc_info=" not in source
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "loguru"
        and any(alias.name == "logger" for alias in node.names)
        for node in ast.walk(tree)
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function = node.func
        if not isinstance(function, ast.Attribute):
            continue
        if function.attr not in {"debug", "info", "warning", "error", "critical"}:
            continue
        message = node.args[0]
        if isinstance(message, ast.Constant) and isinstance(message.value, str):
            assert "%s" not in message.value
            assert "%d" not in message.value
            assert "%r" not in message.value


def test_loguru_interpolates_eval_warning_and_attaches_exception() -> None:
    messages: list[str] = []
    sink_id = logger.add(messages.append, format="{message}|{exception}")
    try:
        logger.warning("Unknown benchmark name: '{}'", "custom-bench")
        try:
            raise ValueError("broken archive")
        except ValueError:
            logger.opt(exception=True).warning("Failed to read {}", "cases.tar.gz")
    finally:
        logger.remove(sink_id)

    rendered = "".join(messages)
    assert "Unknown benchmark name: 'custom-bench'" in rendered
    assert "Failed to read cases.tar.gz" in rendered
    assert "ValueError: broken archive" in rendered


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
