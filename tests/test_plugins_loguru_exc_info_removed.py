"""Regression: loguru does not recognize stdlib logging's `exc_info=True`
kwarg -- it is silently absorbed as an unused str.format() keyword and the
exception traceback is never attached to the log record. 15 call sites
across vectorcode/src/plugins/ passed `exc_info=True` to a loguru logger
call, so every one of them silently dropped its traceback. The fix is
`logger.opt(exception=True).<level>(...)`, loguru's real equivalent.

This test asserts the source no longer contains the broken pattern,
rather than trying to capture loguru's internal record (which would
require loguru-specific sink plumbing) -- the fix is a source-level
substitution, so a source-level regression test is the right fidelity.
"""
from __future__ import annotations

from pathlib import Path

PLUGINS_DIR = Path(__file__).parent.parent / "vectorcode" / "src" / "plugins"

_AFFECTED_FILES = [
    "image_gen/openai/__init__.py",
    "image_gen/openai-codex/__init__.py",
    "memory/hindsight/__init__.py",
    "memory/honcho/cli.py",
    "memory/supermemory/__init__.py",
]


def test_no_exc_info_kwarg_remains_in_plugins():
    offenders = []
    for rel_path in _AFFECTED_FILES:
        source = (PLUGINS_DIR / rel_path).read_text(encoding="utf-8")
        if "exc_info=True" in source:
            offenders.append(rel_path)
    assert offenders == [], f"exc_info=True (silently ignored by loguru) still present in: {offenders}"


def test_opt_exception_true_used_in_place_of_exc_info():
    for rel_path in _AFFECTED_FILES:
        source = (PLUGINS_DIR / rel_path).read_text(encoding="utf-8")
        assert "logger.opt(exception=True)" in source, (
            f"{rel_path} should use logger.opt(exception=True) to actually "
            "attach the exception traceback"
        )
