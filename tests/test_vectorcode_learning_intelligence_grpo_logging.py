"""Regression for vectorcode/src/learning/intelligence/{__init__,grpo_trainer}.py:

grpo_trainer.py used plain stdlib `logging` with no loguru import at all
(not even a shadow -- loguru was simply never imported), with %-style and
exc_info=True calls that only "worked" because the logger genuinely was
stdlib. intelligence/__init__.py correctly imported loguru but passed
stdlib's exc_info=True kwarg to it, which loguru's .debug() silently
ignores (dropping the traceback); needs logger.opt(exception=True)
instead.

Reads source text directly rather than importing the module: importing
grpo_trainer.py a second time within one pytest session re-fires its
module-level `@LearningRegistry.register("grpo")` decorator, which
raises on an already-registered key -- a pre-existing test-isolation
property of LearningRegistry, unrelated to this fix.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parent.parent
_GRPO_PATH = _ROOT / "vectorcode" / "src" / "learning" / "intelligence" / "grpo_trainer.py"
_INIT_PATH = _ROOT / "vectorcode" / "src" / "learning" / "intelligence" / "__init__.py"


def test_grpo_trainer_imports_loguru_not_stdlib_logging():
    src = _GRPO_PATH.read_text(encoding="utf-8")
    assert "from loguru import logger" in src
    assert "import logging" not in src


def test_grpo_trainer_no_percent_style_placeholders_remain():
    src = _GRPO_PATH.read_text(encoding="utf-8")
    assert "%s" not in src
    assert "%d" not in src
    assert "%.4f" not in src


def test_intelligence_init_no_exc_info_kwarg_on_loguru():
    src = _INIT_PATH.read_text(encoding="utf-8")
    assert "exc_info=True" not in src
    assert src.count("logger.opt(exception=True)") == 2


if __name__ == "__main__":
    import pytest
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
