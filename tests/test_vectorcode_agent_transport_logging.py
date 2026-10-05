"""Regression tests for Loguru formatting in agent transport helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from loguru import logger


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


def test_codex_session_uses_loguru_and_formats_unknown_method():
    module = importlib.import_module("agent.transports.codex_app_server_session")
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        class Client:
            def respond_error(self, request_id, **error):
                self.response = (request_id, error)

        session = object.__new__(module.CodexAppServerSession)
        session._client = Client()
        session._handle_server_request({"id": 7, "method": "unexpected/method"})
    finally:
        logger.remove(sink_id)

    assert module.logger is logger
    assert session._client.response[0] == 7
    assert "unexpected/method" in "".join(messages)
    assert "%s" not in "".join(messages)


def test_video_registry_uses_loguru_and_formats_provider_name():
    module = importlib.import_module("agent.video_gen_registry")
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="DEBUG", format="{message}")
    try:
        module._reset_for_tests()
        class Provider(module.VideoGenProvider):
            @property
            def name(self):
                return "proof-provider"

            def generate(self, **_kwargs):
                return {}

        module.register_provider(Provider())
    finally:
        module._reset_for_tests()
        logger.remove(sink_id)

    assert module.logger is logger
    assert "proof-provider" in "".join(messages)
    assert "%s" not in "".join(messages)


def test_transport_sources_have_no_stdlib_only_loguru_arguments():
    paths = [
        VECTORCODE_SRC / "agent" / "transports" / "__init__.py",
        VECTORCODE_SRC / "agent" / "transports" / "chat_completions.py",
        VECTORCODE_SRC / "agent" / "transports" / "codex_app_server.py",
        VECTORCODE_SRC / "agent" / "transports" / "codex_app_server_session.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "exc_info=True" not in combined
    assert "suppressed Exception: %s" not in combined
