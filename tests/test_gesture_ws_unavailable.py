"""/gesture/ws used to accept the socket and then die with `mediapipe has no attribute 'solutions'`
(mediapipe 0.10.35 dropped the legacy API); the HUD retried once per second. It must say clearly
that the feature is unavailable. (2026-09-27: the handler now uses the Tasks API; the message names it.)"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.routers import gesture


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(gesture.router)
    return TestClient(app)


def test_reports_unavailable_when_mediapipe_has_no_solutions_api(monkeypatch):
    monkeypatch.setitem(sys.modules, "mediapipe", types.SimpleNamespace(__version__="0.10.35"))
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    with _client().websocket_connect("/gesture/ws") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "unavailable"
    assert "0.10.35" in msg["error"] and "Tasks API" in msg["error"]


def test_reports_unavailable_when_mediapipe_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "mediapipe", None)  # import raises ImportError
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    with _client().websocket_connect("/gesture/ws") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "unavailable"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
