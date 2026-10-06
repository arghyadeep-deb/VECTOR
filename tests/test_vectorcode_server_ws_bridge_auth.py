"""Regression for vectorcode/src/server/ws_bridge.py: the agent-events
WebSocket endpoint was completely unauthenticated regardless of whether
OPENVECTOR_API_KEY was configured, because Starlette's BaseHTTPMiddleware
(what AuthMiddleware is built on) never runs for websocket connections --
only for scope["type"] == "http". /v1/* HTTP routes were protected but this
/v1/agents/events WebSocket silently bypassed auth entirely, leaking live
internal agent telemetry (tool calls, inference events) to any caller.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vectorcode.src.vc_core.events import EventBus
from server.ws_bridge import create_ws_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_ws_router(EventBus()))
    return TestClient(app)


def test_ws_connection_rejected_without_key_when_configured(monkeypatch):
    monkeypatch.setenv("OPENVECTOR_API_KEY", "real-key")
    client = _client()
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/agents/events"):
            pass


def test_ws_connection_rejected_with_wrong_key_when_configured(monkeypatch):
    monkeypatch.setenv("OPENVECTOR_API_KEY", "real-key")
    client = _client()
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/agents/events?api_key=wrong"):
            pass


def test_ws_connection_accepted_with_correct_key(monkeypatch):
    monkeypatch.setenv("OPENVECTOR_API_KEY", "real-key")
    client = _client()
    with client.websocket_connect("/v1/agents/events?api_key=real-key") as ws:
        pass


def test_ws_connection_accepted_when_unconfigured(monkeypatch):
    monkeypatch.delenv("OPENVECTOR_API_KEY", raising=False)
    client = _client()
    with client.websocket_connect("/v1/agents/events") as ws:
        pass


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
