import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.routers import openai_compat
from core.sensing.presence_detector import PresenceDetector
from core.voice.engines.omnivoice_engine import OmniVoiceConfig, OmniVoiceEngine


def test_omnivoice_disabled_does_not_load_heavy_backend():
    engine = OmniVoiceEngine(OmniVoiceConfig(enabled=False))

    assert engine.loaded is False
    with pytest.raises(RuntimeError, match="disabled"):
        engine.synthesize_to_file("hello")


def test_presence_detector_disabled_returns_fallback():
    detector = PresenceDetector(enabled=False)

    result = detector.detect()

    assert result.status == "disabled"
    assert result.backend == "face_detector_fallback"
    assert result.person_count == 0


def test_openai_compat_models_shape():
    app = FastAPI()
    app.include_router(openai_compat.router)
    client = TestClient(app)

    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["data"]
    assert {"id", "object", "owned_by"}.issubset(body["data"][0])


def test_openai_compat_chat_completion_shape(monkeypatch):
    class FakeProviderClient:
        async def chat(self, **kwargs):
            class Result:
                content = "hello from vector"
                model = "vector-test"
                provider = "test"
                input_tokens = 3
                output_tokens = 4
                finish_reason = "stop"

            return Result()

    monkeypatch.setattr(openai_compat, "ProviderClient", FakeProviderClient)
    app = FastAPI()
    app.include_router(openai_compat.router)
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={
        "model": "vector-test",
        "messages": [{"role": "user", "content": "hi"}],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "hello from vector"
    assert body["usage"]["total_tokens"] == 7


def test_openai_compat_streaming_returns_sse_content_type(monkeypatch):
    class FakeProviderClient:
        async def chat(self, **kwargs):
            class Result:
                content = "hello streamed"
                model = "vector-test"
                provider = "test"
                input_tokens = 2
                output_tokens = 2
                finish_reason = "stop"

            return Result()

    monkeypatch.setattr(openai_compat, "ProviderClient", FakeProviderClient)
    app = FastAPI()
    app.include_router(openai_compat.router)
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    })

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")


def test_openai_compat_streaming_emits_valid_chunks_and_done_marker(monkeypatch):
    import json as _json

    class FakeProviderClient:
        async def chat(self, **kwargs):
            class Result:
                content = "hello streamed"
                model = "vector-test"
                provider = "test"
                input_tokens = 2
                output_tokens = 2
                finish_reason = "stop"

            return Result()

    monkeypatch.setattr(openai_compat, "ProviderClient", FakeProviderClient)
    app = FastAPI()
    app.include_router(openai_compat.router)
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    })

    lines = [l for l in response.text.split("\n\n") if l.strip()]
    assert lines[-1] == "data: [DONE]"

    data_lines = [l[len("data: "):] for l in lines[:-1]]
    assert data_lines, "expected at least one chunk before [DONE]"
    chunk = _json.loads(data_lines[0])
    assert chunk["object"] == "chat.completion.chunk"
    assert "delta" in chunk["choices"][0]
    full_text = "".join(_json.loads(l)["choices"][0]["delta"].get("content", "") for l in data_lines)
    assert full_text == "hello streamed"
    last_chunk = _json.loads(data_lines[-1])
    assert last_chunk["choices"][0]["finish_reason"] == "stop"


def test_openai_compat_streaming_requires_messages():
    app = FastAPI()
    app.include_router(openai_compat.router)
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={"stream": True, "messages": []})

    assert response.status_code == 400
