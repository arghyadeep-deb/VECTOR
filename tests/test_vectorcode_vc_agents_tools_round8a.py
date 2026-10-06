from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


def test_calculator_uses_python_fallback_when_rust_module_is_absent(monkeypatch):
    from vectorcode.src import _rust_bridge
    from vectorcode.src.vc_tools.calculator import safe_eval

    monkeypatch.setattr(_rust_bridge, "get_rust_module", lambda: None)

    assert safe_eval("2^3 + sqrt(16)") == 12.0


def test_channel_agent_does_not_eagerly_stringify_result_with_content():
    from vectorcode.src.channels._abc import ChannelMessage
    from vectorcode.src.vc_agents.channel_agent import ChannelAgent

    class Result:
        content = "valid response"

        def __str__(self):
            raise AssertionError("__str__ must not run when content is available")

    class Agent:
        def run(self, _content):
            return Result()

    class Channel:
        def __init__(self):
            self.sent = []

        def on_message(self, _handler):
            return None

        def send(self, channel, content, **_kwargs):
            self.sent.append((channel, content))
            return True

    channel = Channel()
    agent = ChannelAgent(channel, Agent())
    try:
        agent._process_message(ChannelMessage("chat", "owner", "hello"))
    finally:
        agent.shutdown()

    assert channel.sent == [("chat", "valid response")]


def test_web_extract_blocks_private_redirect(monkeypatch):
    from vectorcode.src.vc_agents import web_search_agent

    class Response:
        is_redirect = True
        headers = {"location": "http://127.0.0.1/private"}

        def raise_for_status(self):
            return None

    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(web_search_agent.httpx, "get", fake_get)
    result = web_search_agent.WebSearchAgent().extract("https://example.com/start")

    assert result["error"] == "extraction failed"
    assert calls == ["https://example.com/start"]


@pytest.mark.parametrize("max_depth", [0, -1, True, "10"])
def test_browser_axtree_rejects_invalid_max_depth(max_depth):
    from vectorcode.src.vc_tools.browser_axtree import BrowserAXTreeTool

    result = BrowserAXTreeTool().execute(max_depth=max_depth)

    assert result.success is False
    assert "positive integer" in result.content


def test_knowledge_search_rejects_invalid_top_k_without_calling_backend():
    from vectorcode.src.vc_tools.knowledge_search import KnowledgeSearchTool

    class Store:
        def retrieve(self, *_args, **_kwargs):
            raise AssertionError("invalid top_k must not reach the backend")

    result = KnowledgeSearchTool(store=Store()).execute(query="test", top_k="many")

    assert result.success is False
    assert "between 1 and 100" in result.content


def test_knowledge_graph_rejects_invalid_direction_without_calling_backend():
    from vectorcode.src.vc_tools.knowledge_tools import KGNeighborsTool

    class Backend:
        def neighbors(self, *_args, **_kwargs):
            raise AssertionError("invalid direction must not reach the backend")

    result = KGNeighborsTool(Backend()).execute(entity_id="a", direction="sideways")

    assert result.success is False
    assert "'in', 'out', or 'both'" in result.content


def test_image_save_declares_file_write_capability():
    from vectorcode.src.vc_tools.image_tool import ImageGenerateTool

    assert ImageGenerateTool().spec.required_capabilities == [
        "network:fetch",
        "file:write",
    ]


def test_audio_transcribe_rejects_sensitive_resolved_target(tmp_path):
    from vectorcode.src.vc_tools.audio_tool import AudioTranscribeTool

    sensitive = tmp_path / "credentials.wav"
    sensitive.write_bytes(b"not audio")

    result = AudioTranscribeTool().execute(file_path=str(sensitive))

    assert result.success is False
    assert "sensitive" in result.content


def test_image_generate_rejects_sensitive_output_before_provider_call(tmp_path):
    from vectorcode.src.vc_tools.image_tool import ImageGenerateTool

    result = ImageGenerateTool().execute(
        prompt="test",
        output_path=str(tmp_path / "credentials.png"),
    )

    assert result.success is False
    assert "sensitive" in result.content


def test_image_generate_saves_via_atomic_replace(monkeypatch, tmp_path):
    import vectorcode.src.vc_tools.image_tool as image_tool

    class Images:
        def generate(self, **_kwargs):
            return SimpleNamespace(data=[SimpleNamespace(url="https://example.com/i")])

    fake_openai = SimpleNamespace(OpenAI=lambda: SimpleNamespace(images=Images()))
    fake_response = SimpleNamespace(
        content=b"image bytes",
        raise_for_status=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: fake_response)
    replacements = []
    real_replace = image_tool.os.replace

    def record_replace(source, target):
        replacements.append((source, target))
        real_replace(source, target)

    monkeypatch.setattr(image_tool.os, "replace", record_replace)
    output = tmp_path / "generated.png"

    result = image_tool.ImageGenerateTool().execute(
        prompt="test",
        output_path=str(output),
    )

    assert result.success is True
    assert output.read_bytes() == b"image bytes"
    assert len(replacements) == 1
    assert replacements[0][1] == output


def test_llm_tool_hydrates_before_calling_engine(monkeypatch):
    import core.loop.context_engine as context_engine
    from vectorcode.src.vc_tools.llm_tool import LLMTool

    class FakeContextEngine:
        def session_hydration_prompt(self, extra_context=None):
            assert extra_context == {"query": "sub-query"}
            return "hydrated context"

    class Engine:
        def generate(self, messages, *, model):
            assert model == "local-model"
            assert [message.content for message in messages] == [
                "hydrated context",
                "custom system",
                "sub-query",
            ]
            return {"content": "answer", "usage": {}}

    monkeypatch.setattr(context_engine, "ContextEngine", FakeContextEngine)

    result = LLMTool(Engine(), model="local-model").execute(
        prompt="sub-query",
        system="custom system",
    )

    assert result.success is True
    assert result.content == "answer"
