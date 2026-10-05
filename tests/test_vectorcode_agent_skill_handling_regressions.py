"""Regression tests for skill metadata/config handling."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from loguru import logger


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


def test_skill_modules_use_loguru():
    for name in (
        "agent.skill_commands",
        "agent.skill_preprocessing",
        "agent.skill_utils",
    ):
        assert importlib.import_module(name).logger is logger


def test_skill_config_injection_preserves_explicit_zero(monkeypatch):
    commands = importlib.import_module("agent.skill_commands")
    utils = importlib.import_module("agent.skill_utils")
    monkeypatch.setattr(utils, "parse_frontmatter", lambda _raw: ({}, ""))
    monkeypatch.setattr(
        utils,
        "extract_skill_config_vars",
        lambda _frontmatter: [{"key": "retry_count", "description": "Retries"}],
    )
    monkeypatch.setattr(
        utils,
        "resolve_skill_config_values",
        lambda _vars: {"retry_count": 0, "enabled": False},
    )

    parts: list[str] = []
    commands._inject_skill_config({"raw_content": "---\n---\n"}, parts)
    output = "\n".join(parts)

    assert "retry_count = 0" in output
    assert "enabled = False" in output
    assert "retry_count = (not set)" not in output
