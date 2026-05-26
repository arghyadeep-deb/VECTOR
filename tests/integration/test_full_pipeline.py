"""integration_tests/test_full_pipeline.py — End-to-end WebSocket + voice + map test."""

import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from core.api.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_websocket_status_endpoint(client):
    """The /ws endpoint should accept connections and return status."""
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "status"
        assert "timestamp" in msg


def test_websocket_ui_event_broadcast(client):
    """Broadcasting a ui_event should reach connected clients."""
    from core.api.routers.websocket import broadcast_event
    
    with client.websocket_connect("/ws") as ws:
        # On connect the server sends an initial burst (status, then events).
        # Drain both so the next frame we read is our broadcast.
        assert ws.receive_json()["type"] == "status"
        assert ws.receive_json()["type"] == "events"
        # Trigger a broadcast from "backend".
        # Python 3.13 removed the implicit loop from asyncio.get_event_loop();
        # drive the coroutine on an explicit loop instead.
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                broadcast_event({"type": "ui_event", "action_type": "widget_open", "params": {"id": "test"}})
            )
        finally:
            loop.close()
        msg = ws.receive_json()
        assert msg["type"] == "ui_event"


def test_voice_intent_parsing():
    """_parse_intent should correctly extract location queries."""
    from core.api.routers.voice_ws import _parse_intent
    
    r1 = _parse_intent("Show me Paris")
    assert r1["action"] == "widget_show_location"
    assert r1["params"]["query"] == "paris"
    
    r2 = _parse_intent("Where is Tokyo?")
    assert r2["params"]["query"] == "tokyo"  # trailing punctuation is stripped for clean geocoding
    
    r3 = _parse_intent("Map of New York City")
    assert r3["params"]["query"] == "new york city"
    
    r4 = _parse_intent("Hello VECTOR")
    assert r4 is None


# NOTE: the dashboard idle-state store lives in vectorStore.ts (TypeScript / Zustand)
# and cannot be imported by pytest. Its behavior is covered by the frontend test
# runner, not this Python suite, so the former test_store_idle_state was removed.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
