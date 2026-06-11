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
