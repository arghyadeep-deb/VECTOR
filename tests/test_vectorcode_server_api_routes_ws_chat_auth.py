"""Regression for vectorcode/src/server/api_routes.py: the /v1/chat/stream
WebSocket endpoint -- which actually invokes the configured LLM engine --
was completely unauthenticated regardless of whether OPENVECTOR_API_KEY was
configured. Starlette's BaseHTTPMiddleware (what AuthMiddleware is built on)
never runs for websocket connections, only for scope["type"] == "http", so
every /v1/* HTTP route was protected but this WebSocket silently bypassed
auth entirely -- the same gap already fixed in ws_bridge.py's
/v1/agents/events this cycle.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api_routes import websocket_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(websocket_router)
    return TestClient(app)


def test_chat_stream_ws_rejected_without_key_when_configured(monkeypatch):
    monkeypatch.setenv("OPENVECTOR_API_KEY", "real-key")
    client = _client()
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/chat/stream"):
            pass


def test_chat_stream_ws_rejected_with_wrong_key_when_configured(monkeypatch):
    monkeypatch.setenv("OPENVECTOR_API_KEY", "real-key")
    client = _client()
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/chat/stream?api_key=wrong"):
            pass


def test_chat_stream_ws_accepted_with_correct_key(monkeypatch):
    monkeypatch.setenv("OPENVECTOR_API_KEY", "real-key")
    client = _client()
    with client.websocket_connect("/v1/chat/stream?api_key=real-key"):
        pass


def test_chat_stream_ws_accepted_when_unconfigured(monkeypatch):
    monkeypatch.delenv("OPENVECTOR_API_KEY", raising=False)
    client = _client()
    with client.websocket_connect("/v1/chat/stream"):
        pass


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
