"""Regression for vectorcode/src/server/webhook_routes.py: three webhook
secret checks used plain ==/!= instead of secrets.compare_digest() --
timing side-channels on real credentials:

- /webhooks/bluebubbles: Authorization header vs bluebubbles_password
- /webhooks/whatsapp (GET verify): hub.verify_token vs whatsapp_verify_token
- /webhooks/sendblue: x-sendblue-secret header vs sb.webhook_secret

Fixed all three with secrets.compare_digest(). The WhatsApp POST handler's
HMAC check already correctly used hmac.compare_digest() -- not touched.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.webhook_routes import create_webhook_router


def test_source_uses_constant_time_compares_not_bare_eq():
    src = inspect.getsource(create_webhook_router)
    assert src.count("secrets.compare_digest") >= 3
    assert "auth != bluebubbles_password" not in src
    assert "token == whatsapp_verify_token" not in src
    assert "header_secret != sb.webhook_secret" not in src


def _client(**kwargs) -> TestClient:
    app = FastAPI()
    app.include_router(create_webhook_router(bridge=None, **kwargs))
    return TestClient(app)


def test_bluebubbles_rejects_wrong_password():
    client = _client(bluebubbles_password="correct-pw")
    resp = client.post(
        "/webhooks/bluebubbles",
        json={"type": "new-message", "data": {}},
        headers={"Authorization": "wrong-pw"},
    )
    assert resp.status_code == 403


def test_bluebubbles_accepts_correct_password():
    client = _client(bluebubbles_password="correct-pw")
    resp = client.post(
        "/webhooks/bluebubbles",
        json={"type": "ping"},
        headers={"Authorization": "correct-pw"},
    )
    assert resp.status_code == 200


def test_whatsapp_verify_rejects_wrong_token():
    client = _client(whatsapp_verify_token="real-token")
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert resp.status_code == 403


def test_whatsapp_verify_accepts_correct_token():
    client = _client(whatsapp_verify_token="real-token")
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "real-token", "hub.challenge": "echo-me"},
    )
    assert resp.status_code == 200
    assert resp.text == "echo-me"


class _FakeSendBlueChannel:
    def __init__(self, webhook_secret: str):
        self.webhook_secret = webhook_secret

    def send(self, *_a, **_k):
        pass


def test_sendblue_rejects_wrong_secret():
    channel = _FakeSendBlueChannel("real-secret")
    client = _client(sendblue_channel=channel)
    resp = client.post(
        "/webhooks/sendblue",
        json={"from_number": "+1555", "content": "hi"},
        headers={"x-sendblue-secret": "wrong-secret"},
    )
    assert resp.status_code == 403


def test_whatsapp_verify_rejects_when_token_not_configured():
    """An empty whatsapp_verify_token must never satisfy the compare --
    secrets.compare_digest("", "") is True, so an unconfigured token
    previously let an empty hub.verify_token "verify" successfully."""
    client = _client(whatsapp_verify_token="")
    resp = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "x"},
    )
    assert resp.status_code == 403


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
