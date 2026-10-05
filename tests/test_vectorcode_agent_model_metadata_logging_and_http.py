"""Regression for vectorcode/src/agent/model_metadata.py:

1. `from loguru import logger` was trapped inside the module's own docstring
   (never executes) -- the real `logger` name came from a plain
   `import logging; logging.getLogger(__name__)`. Every %-style placeholder
   across ~27 logger call sites would silently fail to substitute under a
   real loguru logger.

2. `fetch_model_metadata()`'s except-branch called the bare stdlib
   `logging.warning(...)` module-level function directly -- bypassing even
   the module's own (broken) `logger` object entirely, going to Python's
   root logger with no VECTOR formatting/sink at all.

3. The module used the project-banned `requests` package for every HTTP
   call (OpenRouter model list, endpoint /models probes, llama.cpp /props,
   Anthropic /v1/models, Codex OAuth /models) -- migrated to `httpx`.
"""
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from loguru import logger as _real_loguru_logger

from agent import model_metadata


def test_module_uses_the_real_loguru_logger():
    assert model_metadata.logger is _real_loguru_logger


def test_no_stdlib_logging_import_or_shadow():
    src = inspect.getsource(model_metadata)
    assert "import logging" not in src
    assert "logging.getLogger" not in src
    assert "logging.warning" not in src


def test_no_requests_package_usage():
    src = inspect.getsource(model_metadata)
    assert "import requests" not in src
    assert "requests." not in src
    assert "import httpx" in src


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(model_metadata)
    for m in re.finditer(r"logger\.\w+\(([\s\S]*?)\)(?=\n)", src, re.MULTILINE):
        call_text = m.group(0)
        assert not re.search(r"%[sdr]|%\.\d*f", call_text), (
            f"found a %-style placeholder in a logger call: {call_text!r}"
        )


def test_fetch_model_metadata_warning_goes_through_loguru(capfd, monkeypatch):
    """fetch_model_metadata()'s failure path must log via the real logger,
    not the bare stdlib logging module (which has no VECTOR sink/format)."""
    def _boom(*a, **k):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(model_metadata.httpx, "get", _boom)
    model_metadata._model_metadata_cache = {}
    model_metadata._model_metadata_cache_time = 0

    _real_loguru_logger.remove()
    _real_loguru_logger.add(sys.stderr, format="{message}")
    try:
        result = model_metadata.fetch_model_metadata(force_refresh=True)
    finally:
        _real_loguru_logger.remove()
        _real_loguru_logger.add(sys.stderr)

    assert result == {}
    captured = capfd.readouterr()
    assert "simulated network failure" in captured.err


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
