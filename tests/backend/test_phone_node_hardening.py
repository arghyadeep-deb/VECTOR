"""Task 06 — phone node env parsing + upstream auth hardening."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parents[2] / "phone_node" / "ambient_server.py"


def _load():
    spec = importlib.util.spec_from_file_location("vector_phone_node_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def phone():
    return _load()


# ── env parser ────────────────────────────────────────────────────────────────

def test_quoted_values_parse(phone):
    cfg = phone._parse_env('VECTOR_API_KEY="abc123"\nVECTOR_NODE_ID=\'phone-1\'')
    assert cfg["VECTOR_API_KEY"] == "abc123"
    assert cfg["VECTOR_NODE_ID"] == "phone-1"


def test_comments_and_whitespace(phone):
    text = "\n  # leading comment\nVECTOR_BRAIN_URL = https://x.fly.dev   \n\n# tail\n"
    cfg = phone._parse_env(text)
    assert cfg["VECTOR_BRAIN_URL"] == "https://x.fly.dev"
    assert "# leading comment" not in cfg


def test_inline_comment_on_unquoted(phone):
    cfg = phone._parse_env("HEARTBEAT_INTERVAL_SEC=60  # seconds")
    assert cfg["HEARTBEAT_INTERVAL_SEC"] == "60"


def test_hash_inside_quoted_value_preserved(phone):
    cfg = phone._parse_env('VECTOR_API_KEY="a#b#c"')
    assert cfg["VECTOR_API_KEY"] == "a#b#c"


# ── upstream auth guard ───────────────────────────────────────────────────────

def test_missing_key_blocks_upstream(phone, monkeypatch):
    monkeypatch.setattr(phone, "API_KEY", "")
    assert phone._can_send_upstream() is False
    # classify must stay local, never hit the network
    def _boom(*a, **k):
        raise AssertionError("must not call network without API key")
    monkeypatch.setattr(phone.urllib.request, "urlopen", _boom, raising=False) \
        if hasattr(phone, "urllib") else None
    assert phone._classify_remote("hello") == "info"


def test_configured_key_sends_bearer(phone, monkeypatch):
    monkeypatch.setattr(phone, "API_KEY", "k" * 40)
    assert phone._can_send_upstream() is True

    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"label": "task"}'

    import urllib.request as ur

    def _fake_urlopen(req, timeout=0):
        captured["auth"] = req.headers.get("Authorization")
        return _Resp()

    monkeypatch.setattr(ur, "urlopen", _fake_urlopen)
    label = phone._classify_remote("do the thing")
    assert label == "task"
    assert captured["auth"] == "Bearer " + "k" * 40


# â”€â”€ local endpoint auth + wake-on-LAN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.mark.parametrize("key", ["", "short", "changeme", "change-me", "placeholder", "default", "test", "secret"])
def test_local_mutating_auth_fails_closed_for_unusable_key(phone, monkeypatch, key):
    monkeypatch.setattr(phone, "API_KEY", key)
    assert phone._auth_ok(None) is False
    assert phone._auth_ok(f"Bearer {key}") is False


def test_local_mutating_auth_rejects_blank_key(phone, monkeypatch):
    monkeypatch.setattr(phone, "API_KEY", "")
    assert phone._auth_ok(None) is False


def test_local_mutating_auth_requires_matching_bearer(phone, monkeypatch):
    monkeypatch.setattr(phone, "API_KEY", "node-token")
    assert phone._auth_ok(None) is False
    assert phone._auth_ok("Bearer wrong") is False
    assert phone._auth_ok("Bearer node-token") is True


def test_server_warns_once_and_still_starts_with_mutating_routes_locked(phone, monkeypatch):
    messages = []

    class FakeServer:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler

        def serve_forever(self):
            return None

    monkeypatch.setattr(phone, "API_KEY", "changeme")
    monkeypatch.setattr(phone, "HTTPServer", FakeServer)
    monkeypatch.setattr(phone, "_log", messages.append)

    phone._start_server()

    warnings = [message for message in messages if "SECURITY WARNING" in message]
    assert len(warnings) == 1
    assert "mutating endpoints" in warnings[0]


def test_phone_magic_packet_shape(phone):
    packet = phone._magic_packet("14-B5-CD-3C-EC-99")
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("14b5cd3cec99") * 16


def test_phone_wake_legion_reports_missing_config(phone, monkeypatch):
    monkeypatch.setattr(phone, "LEGION_WIFI_MAC", "")
    monkeypatch.setattr(phone, "LEGION_ETHERNET_MAC", "")
    result = phone.wake_legion()
    assert result["ok"] is False
    assert "LEGION_WIFI_MAC" in result["error"]


def test_phone_wake_legion_sends_udp_broadcast(phone, monkeypatch):
    calls = {}

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def setsockopt(self, level, optname, value):
            calls["sockopt"] = (level, optname, value)

        def sendto(self, packet, address):
            calls["packet"] = packet
            calls["address"] = address

    monkeypatch.setattr(phone, "LEGION_WIFI_MAC", "14-B5-CD-3C-EC-99")
    monkeypatch.setattr(phone, "LEGION_ETHERNET_MAC", "")
    monkeypatch.setattr(phone, "LEGION_WAKE_BROADCAST", "10.208.79.255")
    monkeypatch.setattr(phone, "LEGION_WAKE_PORT", 9)
    monkeypatch.setattr(phone.socket, "socket", lambda *args: FakeSocket())

    result = phone.wake_legion()

    assert result["ok"] is True
    assert result["mac"] == "14b5cd3cec99"
    assert calls["address"] == ("10.208.79.255", 9)
    assert calls["packet"] == b"\xff" * 6 + bytes.fromhex("14b5cd3cec99") * 16


def test_execute_cloud_command_wake_legion(phone, monkeypatch):
    monkeypatch.setattr(phone, "wake_legion", lambda prefer="wifi": {"ok": True, "prefer": prefer})

    status, result, error = phone._execute_cloud_command({
        "id": "cmd1",
        "type": "wake_legion",
        "params": {"prefer": "wifi"},
    })

    assert status == "done"
    assert result == {"ok": True, "prefer": "wifi"}
    assert error == ""


def test_command_poll_once_executes_and_posts_result(phone, monkeypatch):
    calls = []

    def fake_cloud_request(path, payload, timeout=10):
        calls.append((path, payload))
        if path.endswith("/poll"):
            return {
                "ok": True,
                "commands": [
                    {"id": "cmd1", "type": "ping", "params": {}, "target_node": "termux-room-node"}
                ],
            }
        return {"ok": True}

    monkeypatch.setattr(phone, "API_KEY", "node-token")
    monkeypatch.setattr(phone, "NODE_ID", "termux-room-node")
    monkeypatch.setattr(phone, "_cloud_request", fake_cloud_request)

    result = phone._command_poll_once()

    assert result == {"ok": True, "commands": 1, "handled": 1}
    assert calls[0][0] == "/nodes/termux-room-node/poll"
    assert calls[1][0] == "/commands/cmd1/result"
    assert calls[1][1]["status"] == "done"
