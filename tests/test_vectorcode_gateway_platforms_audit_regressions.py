"""Regression coverage for the 2026-10-05 platform-adapter audit slice."""

from __future__ import annotations

import ast
import asyncio
from email.mime.text import MIMEText
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ROOT / "vectorcode" / "src" / "gateway" / "platforms"
sys.path.insert(0, str(ROOT / "vectorcode" / "src"))
AUDITED = (
    "signal_rate_limit.py",
    "sms.py",
    "feishu_comment_rules.py",
    "qqbot/keyboards.py",
    "yuanbao_sticker.py",
    "qqbot/chunked_upload.py",
    "email.py",
    "yuanbao_media.py",
    "mattermost.py",
    "bluebubbles.py",
    "signal.py",
    "whatsapp.py",
)


def test_audited_platforms_use_loguru_without_printf_placeholders() -> None:
    for relative in AUDITED:
        path = PLATFORMS / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "logging" for alias in node.names):
                pytest.fail(f"{relative}:{node.lineno} imports stdlib logging")
            if isinstance(node, ast.ImportFrom) and node.module == "logging":
                pytest.fail(f"{relative}:{node.lineno} imports stdlib logging")
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "logger":
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                assert not any(token in node.args[0].value for token in ("%s", "%d", "%r", "%i", "%f")), (
                    f"{relative}:{node.lineno} still uses a printf-style logger placeholder"
                )


def test_production_adapters_do_not_print() -> None:
    for relative in ("email.py", "whatsapp.py"):
        tree = ast.parse((PLATFORMS / relative).read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        ]
        assert not calls, f"{relative} contains production print() calls"


def test_disconnect_cleanup_does_not_reraise_its_own_cancellation() -> None:
    targets = {
        "email.py": "EmailAdapter",
        "mattermost.py": "MattermostAdapter",
        "signal.py": "SignalAdapter",
        "whatsapp.py": "WhatsAppAdapter",
    }
    for relative, class_name in targets.items():
        tree = ast.parse((PLATFORMS / relative).read_text(encoding="utf-8"))
        klass = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        disconnect = next(
            node for node in klass.body
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "disconnect"
        )
        for handler in (
            node for node in ast.walk(disconnect) if isinstance(node, ast.ExceptHandler)
        ):
            rendered_type = ast.unparse(handler.type) if handler.type else ""
            if "CancelledError" in rendered_type:
                assert not any(isinstance(node, ast.Raise) for node in ast.walk(handler)), (
                    f"{relative} re-raises cancellation from a task disconnect() cancelled itself"
                )


def test_pairing_cache_refuses_to_replace_corrupt_persistent_data(tmp_path: Path) -> None:
    from gateway.platforms.feishu_comment_rules import _MtimeCache

    pairing = tmp_path / "pairing.json"
    original = "{this is not valid json"
    pairing.write_text(original, encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to treat unreadable persistent data as empty"):
        _MtimeCache(pairing, fail_closed=True).load()

    assert pairing.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_bluebubbles_webhook_uses_constant_time_secret_comparison(monkeypatch) -> None:
    from gateway.platforms import bluebubbles

    calls = []

    def compare(left: str, right: str) -> bool:
        calls.append((left, right))
        return False

    monkeypatch.setattr(bluebubbles.secrets, "compare_digest", compare)
    adapter = bluebubbles.BlueBubblesAdapter.__new__(bluebubbles.BlueBubblesAdapter)
    adapter.password = "correct-secret"

    class Request:
        query = {"password": "wrong-secret"}
        headers = {}

    response = await adapter._handle_webhook(Request())
    assert response.status == 401
    assert calls == [("wrong-secret", "correct-secret")]


@pytest.mark.asyncio
async def test_bluebubbles_keeps_read_receipt_task_alive() -> None:
    from gateway.platforms.bluebubbles import BlueBubblesAdapter

    blocker = asyncio.Event()
    adapter = BlueBubblesAdapter.__new__(BlueBubblesAdapter)
    adapter.password = "secret"
    adapter.send_read_receipts = True
    adapter._background_tasks = set()
    adapter._download_attachment = lambda *_args: None
    adapter.build_source = lambda **kwargs: kwargs

    async def handle_message(_event):
        return None

    async def mark_read(_chat_id):
        await blocker.wait()

    adapter.handle_message = handle_message
    adapter.mark_read = mark_read

    class Request:
        query = {"password": "secret"}
        headers = {}

        async def read(self):
            return json.dumps({
                "type": "new-message",
                "data": {
                    "text": "hello",
                    "guid": "message-guid",
                    "chatGuid": "iMessage;-;person@example.com",
                    "sender": "person@example.com",
                },
            }).encode()

    response = await adapter._handle_webhook(Request())
    assert response.status == 200
    assert any(not task.done() for task in adapter._background_tasks)
    blocker.set()
    await asyncio.gather(*tuple(adapter._background_tasks))


@pytest.mark.asyncio
async def test_email_disconnect_consumes_its_own_task_cancellation() -> None:
    from gateway.platforms.email import EmailAdapter

    adapter = EmailAdapter.__new__(EmailAdapter)
    adapter._running = True
    adapter._poll_task = asyncio.create_task(asyncio.sleep(60))
    await adapter.disconnect()
    assert adapter._poll_task is None


def test_email_failed_fetch_does_not_poison_seen_uid(monkeypatch) -> None:
    from gateway.platforms import email as email_platform

    message = MIMEText("hello")
    message["From"] = "person@example.com"
    message["Subject"] = "Hi"

    class Imap:
        fetch_attempts = 0

        def __init__(self, *_args, **_kwargs):
            pass

        def login(self, *_args):
            pass

        def select(self, *_args):
            pass

        def uid(self, command, *_args):
            if command == "search":
                return "OK", [b"42"]
            type(self).fetch_attempts += 1
            if type(self).fetch_attempts == 1:
                return "NO", []
            return "OK", [(b"42 (RFC822)", message.as_bytes())]

        def logout(self):
            pass

    monkeypatch.setattr(email_platform.imaplib, "IMAP4_SSL", Imap)
    adapter = email_platform.EmailAdapter.__new__(email_platform.EmailAdapter)
    adapter._imap_host = "imap.example.com"
    adapter._imap_port = 993
    adapter._address = "bot@example.com"
    adapter._password = "secret"
    adapter._seen_uids = set()
    adapter._seen_uids_max = 2000
    adapter._skip_attachments = True

    assert adapter._fetch_new_messages() == []
    assert b"42" not in adapter._seen_uids
    assert len(adapter._fetch_new_messages()) == 1
    assert b"42" in adapter._seen_uids


def test_whatsapp_device_jid_normalization_preserves_one_at_sign() -> None:
    from gateway.platforms.whatsapp import WhatsAppAdapter

    assert (
        WhatsAppAdapter._normalize_whatsapp_id("15551234567:2@s.whatsapp.net")
        == "15551234567@s.whatsapp.net"
    )


def test_chunked_upload_rejects_prepare_response_without_valid_parts() -> None:
    from gateway.platforms.qqbot.chunked_upload import _parse_prepare_response

    with pytest.raises(ValueError, match="no valid parts"):
        _parse_prepare_response({"upload_id": "upload-1", "parts": [None, "bad"]})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
