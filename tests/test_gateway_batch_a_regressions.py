"""Regression tests for the gateway batch-A security/correctness audit."""

import json
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_pairing_platform_name_cannot_escape_store(tmp_path, monkeypatch):
    from gateway import pairing

    monkeypatch.setattr(pairing, "PAIRING_DIR", tmp_path)
    store = pairing.PairingStore()

    with pytest.raises(ValueError, match="platform"):
        store.generate_code("../outside", "user-1")

    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path.parent / "outside-pending.json").exists()


def test_pairing_code_uses_constant_time_comparisons(tmp_path, monkeypatch):
    from gateway import pairing

    monkeypatch.setattr(pairing, "PAIRING_DIR", tmp_path)
    store = pairing.PairingStore()
    code = store.generate_code("telegram", "user-1")
    calls = []
    real_compare_digest = secrets.compare_digest

    def recording_compare(left, right):
        calls.append((left, right))
        return real_compare_digest(left, right)

    monkeypatch.setattr(pairing.secrets, "compare_digest", recording_compare)
    assert store.approve_code("telegram", code) == {
        "user_id": "user-1",
        "user_name": "",
    }
    assert calls == [(code, code)]


@pytest.mark.parametrize(
    ("function_name", "payload", "default_suffix", "cache_attr"),
    [
        ("cache_image_from_bytes", b"\x89PNG\r\n\x1a\nimage", ".jpg", "IMAGE_CACHE_DIR"),
        ("cache_audio_from_bytes", b"audio", ".ogg", "AUDIO_CACHE_DIR"),
        ("cache_video_from_bytes", b"video", ".mp4", "VIDEO_CACHE_DIR"),
    ],
)
def test_media_cache_rejects_path_like_extensions(
    tmp_path, monkeypatch, function_name, payload, default_suffix, cache_attr
):
    from gateway.platforms import base

    monkeypatch.setattr(base, cache_attr, tmp_path)
    cached = Path(getattr(base, function_name)(payload, "/../../escape.bin"))

    assert cached.parent == tmp_path
    assert cached.suffix == default_suffix


@pytest.mark.asyncio
async def test_bluebubbles_registration_log_redacts_password(monkeypatch):
    from gateway.config import PlatformConfig
    from gateway.platforms import bluebubbles

    adapter = bluebubbles.BlueBubblesAdapter(
        PlatformConfig(extra={"server_url": "http://localhost:1234", "password": "top-secret"})
    )
    adapter.client = object()
    monkeypatch.setattr(adapter, "_find_registered_webhooks", AsyncMock(return_value=[{"id": "1"}]))
    logged = []
    monkeypatch.setattr(bluebubbles.logger, "info", lambda *args, **kwargs: logged.append(args))

    assert await adapter._register_webhook() is True
    assert "top-secret" not in repr(logged)


@pytest.mark.asyncio
async def test_feishu_url_verification_requires_configured_token(monkeypatch):
    from gateway.config import PlatformConfig
    from gateway.platforms.feishu import FeishuAdapter

    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "expected-token")
    adapter = FeishuAdapter(PlatformConfig())
    body = json.dumps(
        {"type": "url_verification", "challenge": "challenge", "token": "wrong-token"}
    ).encode("utf-8")
    request = SimpleNamespace(
        remote="127.0.0.1",
        content_length=len(body),
        headers={"Content-Type": "application/json"},
        read=AsyncMock(return_value=body),
    )

    response = await adapter._handle_webhook_request(request)
    assert response.status == 401


def test_feishu_dedup_save_preserves_old_file_if_replace_fails(tmp_path, monkeypatch):
    from gateway.config import PlatformConfig
    from gateway.platforms import feishu

    adapter = feishu.FeishuAdapter(PlatformConfig())
    adapter._dedup_state_path = tmp_path / "dedup.json"
    original = '{"message_ids":{"old":1}}'
    adapter._dedup_state_path.write_text(original, encoding="utf-8")
    adapter._seen_message_ids = {"new": 2.0}
    adapter._seen_message_order = ["new"]
    monkeypatch.setattr(feishu.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("crash")))

    adapter._persist_seen_message_ids()
    assert adapter._dedup_state_path.read_text(encoding="utf-8") == original


def test_feishu_comment_pairing_save_is_atomic(tmp_path, monkeypatch):
    from gateway.platforms import feishu_comment_rules as rules

    pairing_file = tmp_path / "pairing.json"
    pairing_file.write_text('{"approved":{"old":{}}}', encoding="utf-8")
    monkeypatch.setattr(rules, "PAIRING_FILE", pairing_file)
    monkeypatch.setattr(rules.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("crash")))

    with pytest.raises(OSError, match="crash"):
        rules._save_pairing({"approved": {"new": {}}})
    assert pairing_file.read_text(encoding="utf-8") == '{"approved":{"old":{}}}'
