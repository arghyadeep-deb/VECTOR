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


def test_openai_compat_rejects_streaming_until_sse_added():
    app = FastAPI()
    app.include_router(openai_compat.router)
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={
        "stream": True,
        "messages": [{"role": "user", "content": "hi"}],
    })

    assert response.status_code == 400
