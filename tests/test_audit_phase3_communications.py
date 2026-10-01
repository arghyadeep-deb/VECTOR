"""Phase 3 audit regression tests for districts/communications."""
from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.email import schema
from districts.communications import reply_forward
from districts.communications.email_agent import EmailAgent
from districts.communications.email_intelligence import EmailIntelligence


@pytest.fixture
def tmpdb(tmp_path, monkeypatch):
    db = tmp_path / "email.db"
    schema.init_schema(db)
    monkeypatch.setattr(reply_forward, "get_connection", partial(schema.get_connection, db))
    conn = schema.get_connection(db)
    with conn:
        conn.execute(
            "INSERT INTO emails(id,folder_id,subject,sender,recipient,date,body,thread_id,message_id)"
            " VALUES('orig','inbox','Hi','a@x.com','me@x.com','2026-01-01','b','orig','m1')"
        )
    conn.close()
    return db


def _folders(db):
    c = schema.get_connection(db)
    rows = [r["folder_id"] for r in c.execute("SELECT folder_id FROM emails WHERE id != 'orig'")]
    c.close()
    return rows


@pytest.mark.parametrize("fn", ["handle_reply_email", "handle_forward_email"])
def test_send_failure_not_reported_as_sent(tmpdb, monkeypatch, fn):
    def boom(params):
        raise OSError("connection refused")

    monkeypatch.setattr(reply_forward, "send_email", boom)
    res = getattr(reply_forward, fn)("me@x.com", "orig", "b@x.com", "me@x.com", "Re: Hi", text="ok")
    assert res.get("status") != "sent"
    assert "error" in res
    assert "sent" not in _folders(tmpdb)


def test_send_success_still_sent(tmpdb, monkeypatch):
    monkeypatch.setattr(reply_forward, "send_email", lambda p: {"message_id": "x"})
    res = reply_forward.handle_reply_email("me@x.com", "orig", "b@x.com", "me@x.com", "Re: Hi", text="ok")
    assert res["status"] == "sent"
    assert "sent" in _folders(tmpdb)


@pytest.mark.asyncio
async def test_run_reply_failure_is_error_not_ok(tmpdb, monkeypatch):
    import core.loop.permission_gateway as pg

    class _R:
        approved = True

    class _GW:
        async def execute(self, action):
            return _R()

    monkeypatch.setattr(pg, "PermissionGateway", _GW)

    def boom(params):
        raise OSError("smtp down")

    monkeypatch.setattr(reply_forward, "send_email", boom)
    agent = EmailAgent()
    res = await agent.run({"type": "reply", "params": {
        "original_email_id": "orig", "to": "b@x.com", "from": "me@x.com",
        "mailbox_id": "me@x.com", "subject": "Re: Hi", "text": "ok"}})
    assert res["status"] == "error"


@pytest.mark.asyncio
async def test_auto_draft_save_failure_not_draft_created(monkeypatch):
    agent = EmailAgent()
    monkeypatch.setattr(agent, "get_email", lambda i: {"body": "hello", "thread_id": "t"})
    monkeypatch.setattr(agent, "get_thread", lambda t: [])
    monkeypatch.setattr("districts.communications.email_agent.is_prompt_injection", lambda b: False)
    monkeypatch.setattr("districts.communications.email_agent.chat", lambda **k: "reply text")
    monkeypatch.setattr(agent, "draft_reply", lambda *a, **k: {"error": "Draft verification failed"})
    res = await agent.handle_new_email("e1", "a@x.com", "Hi", "t")
    assert res["status"] == "error"


@pytest.mark.asyncio
async def test_gmail_fetch_failure_reported_as_error(monkeypatch):
    agent = EmailIntelligence()

    class _Svc:
        def users(self):
            raise RuntimeError("quota exceeded")

    monkeypatch.setattr(agent, "_get_gmail_service", lambda: _Svc())
    res = await agent.run({"type": "brief"})
    assert res["status"] == "error"


@pytest.mark.asyncio
async def test_gmail_not_configured_still_ok(monkeypatch):
    agent = EmailIntelligence()
    monkeypatch.setattr(agent, "_get_gmail_service", lambda: None)
    res = await agent.run({"type": "brief"})
    assert res["status"] == "ok" and res["threads"] == 0
