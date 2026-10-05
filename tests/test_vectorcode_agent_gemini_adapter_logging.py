"""Regression tests for Gemini adapter Loguru integration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from loguru import logger


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


def _capture_debug(callable_):
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="DEBUG", format="{message}")
    try:
        callable_()
    finally:
        logger.remove(sink_id)
    return "".join(messages)


def test_native_adapter_keeps_loguru_and_formats_network_error(monkeypatch):
    module = importlib.import_module("agent.gemini_native_adapter")

    class BrokenClient:
        def __init__(self, **_kwargs):
            raise RuntimeError("native probe failed")

    monkeypatch.setattr(module.httpx, "Client", BrokenClient)
    output = _capture_debug(lambda: module.probe_gemini_tier("secret"))

    assert module.logger is logger
    assert "native probe failed" in output
    assert "%s" not in output


def test_cloudcode_adapter_keeps_loguru_and_formats_bad_sse():
    module = importlib.import_module("agent.gemini_cloudcode_adapter")

    class Response:
        def iter_text(self):
            yield "data: not-json\n\n"

    output = _capture_debug(lambda: list(module._iter_sse_events(Response())))

    assert module.logger is logger
    assert "not-json" in output
    assert "%s" not in output
