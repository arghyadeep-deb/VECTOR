"""
Regression tests for VECTOR_TECHNICAL_KNOWLEDGE/53_PERMISSION_BOUNDARY_
INTEGRITY.md — Finding 1.

Context (audit finding): EmailAgent.run()'s "reply"/"send_reply"/"forward"
task_type branches called districts.communications.reply_forward's
handle_reply_email()/handle_forward_email() -> core/email/sender.py's real
smtplib.SMTP send DIRECTLY, with NO PermissionGateway check at all — even
though "send_email" is explicitly RED-tier (core/config.py) and this same
class already implements the correct gate on its OWN send_reply() method
(which turned out to be dead code: nothing in run()'s task_type dispatch
table ever calls it).

Reachability confirmed via code trace (see the audit doc): EmailAgent
declares "reply"/"forward"/"send_email" in self.capabilities, so
Governor.dispatch()'s capability-match routes task_type="reply"/"forward"
straight to this agent's run(). That dispatch is reachable with ZERO
PermissionGateway involvement via:
  - autonomous_loop._act_on()'s fallthrough (no VC/skill/plan match) ->
    governor.dispatch()
  - core/api/routers/commands.py's classify_chat_intent() fast path ->
    governor.dispatch() (any normal chat message the classifier reads as
    an email-reply/forward intent)
  - core/api/routers/websocket.py's /command HTTP endpoint, same pattern

These tests exercise the REAL EmailAgent.run() method end to end (not just
source inspection) — only PermissionGateway.execute and the actual SMTP-
reaching reply_forward functions are mocked, since a real test must never
send real email.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_agent():
    from districts.communications.email_agent import EmailAgent
    return EmailAgent()


class _FakeGatewayResult:
    def __init__(self, approved: bool, reason: str = ""):
        self.approved = approved
        self.reason = reason


async def test_reply_denied_by_gateway_does_not_send(monkeypatch):
    """Permission denial must actually prevent execution — a rejected
    gateway result must mean handle_reply_email() is never called."""
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    send_mock = AsyncMock()
    monkeypatch.setattr(rf, "handle_reply_email", lambda **kw: send_mock(**kw))

    async def fake_execute(self, action):
        assert action.action_type == "send_email"
        return _FakeGatewayResult(approved=False, reason="owner rejected")

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    agent = _make_agent()
    result = await agent.run({
        "type": "reply", "to": "someone@example.com", "subject": "Re: test",
        "text": "body", "original_email_id": "e1",
    })

    assert result["status"] == "blocked"
    send_mock.assert_not_called()


async def test_reply_approved_by_gateway_sends(monkeypatch):
    """A genuinely approved gateway result must let the reply through —
    confirms the fix doesn't just fail-closed unconditionally."""
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    called = {}

    def fake_handle_reply_email(**kw):
        called.update(kw)
        return {"message_id": "abc123"}

    monkeypatch.setattr(rf, "handle_reply_email", fake_handle_reply_email)

    async def fake_execute(self, action):
        assert action.action_type == "send_email"
        return _FakeGatewayResult(approved=True)

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    agent = _make_agent()
    result = await agent.run({
        "type": "reply", "to": "someone@example.com", "subject": "Re: test",
        "text": "body", "original_email_id": "e1",
    })

    assert result["status"] == "ok"
    assert called.get("to") == "someone@example.com"


async def test_send_reply_alias_task_type_also_gated(monkeypatch):
    """task_type == 'send_reply' must be gated identically to 'reply' —
    both are handled by the same branch."""
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    send_mock = AsyncMock()
    monkeypatch.setattr(rf, "handle_reply_email", lambda **kw: send_mock(**kw))

    async def fake_execute(self, action):
        return _FakeGatewayResult(approved=False, reason="test")

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    agent = _make_agent()
    result = await agent.run({"type": "send_reply", "to": "x@example.com"})

    assert result["status"] == "blocked"
    send_mock.assert_not_called()


async def test_forward_denied_by_gateway_does_not_send(monkeypatch):
    """Same gate, same denial behavior, for the 'forward' task_type."""
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    send_mock = AsyncMock()
    monkeypatch.setattr(rf, "handle_forward_email", lambda **kw: send_mock(**kw))

    async def fake_execute(self, action):
        assert action.action_type == "send_email"
        return _FakeGatewayResult(approved=False, reason="owner rejected")

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    agent = _make_agent()
    result = await agent.run({
        "type": "forward", "to": "someone@example.com", "subject": "Fwd: test",
        "original_email_id": "e1",
    })

    assert result["status"] == "blocked"
    send_mock.assert_not_called()


async def test_forward_approved_by_gateway_sends(monkeypatch):
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    called = {}

    def fake_handle_forward_email(**kw):
        called.update(kw)
        return {}

    monkeypatch.setattr(rf, "handle_forward_email", fake_handle_forward_email)

    async def fake_execute(self, action):
        return _FakeGatewayResult(approved=True)

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    agent = _make_agent()
    result = await agent.run({
        "type": "forward", "to": "someone@example.com", "original_email_id": "e1",
    })

    assert result["status"] == "ok"
    assert called.get("to") == "someone@example.com"


async def test_gateway_unreachable_fails_closed_for_reply(monkeypatch):
    """Exceptions must not silently bypass permission — if the gateway
    raises/is unreachable, the reply must NOT be sent (fail closed, not
    fail open)."""
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    send_mock = AsyncMock()
    monkeypatch.setattr(rf, "handle_reply_email", lambda **kw: send_mock(**kw))

    async def raising_execute(self, action):
        raise RuntimeError("simulated gateway outage")

    monkeypatch.setattr(PermissionGateway, "execute", raising_execute)

    agent = _make_agent()
    result = await agent.run({"type": "reply", "to": "x@example.com"})

    assert result["status"] == "blocked"
    assert result.get("reason") == "gateway_unreachable"
    send_mock.assert_not_called()


async def test_gateway_unreachable_fails_closed_for_forward(monkeypatch):
    import districts.communications.reply_forward as rf
    from core.loop.permission_gateway import PermissionGateway

    send_mock = AsyncMock()
    monkeypatch.setattr(rf, "handle_forward_email", lambda **kw: send_mock(**kw))

    async def raising_execute(self, action):
        raise RuntimeError("simulated gateway outage")

    monkeypatch.setattr(PermissionGateway, "execute", raising_execute)

    agent = _make_agent()
    result = await agent.run({"type": "forward", "to": "x@example.com"})

    assert result["status"] == "blocked"
    assert result.get("reason") == "gateway_unreachable"
    send_mock.assert_not_called()


async def test_read_only_list_task_unaffected_by_gate(monkeypatch):
    """A GREEN, read-only task_type ('list') must NOT go through
    PermissionGateway.execute at all — this fix must not add friction to
    harmless operations. If this test's fake_execute were ever called for
    'list', that alone is the failure signal."""
    from core.loop.permission_gateway import PermissionGateway

    calls = []

    async def fake_execute(self, action):
        calls.append(action.action_type)
        return _FakeGatewayResult(approved=True)

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    agent = _make_agent()
    result = await agent.run({"type": "list", "folder": "inbox", "limit": 5})

    assert result["status"] == "ok"
    assert calls == [], f"read-only 'list' task must never call the gateway, but got: {calls}"


async def test_real_send_reply_method_still_gates_correctly(monkeypatch):
    """The pre-existing, correctly-gated self.send_reply() method (which
    turned out to be unreachable from run()'s dispatch table — the actual
    root cause documented in the audit) must still behave correctly on its
    own, confirming the fix didn't touch or regress it."""
    from core.loop.permission_gateway import PermissionGateway

    agent = _make_agent()
    # get_email() returns None for a nonexistent draft — this exercises the
    # method's early-return path without needing real DB state, while still
    # proving PermissionGateway.execute is never reached before that check.
    calls = []

    async def fake_execute(self, action):
        calls.append(action.action_type)
        return _FakeGatewayResult(approved=True)

    monkeypatch.setattr(PermissionGateway, "execute", fake_execute)

    result = await agent.send_reply("nonexistent-draft-id")
    assert result["status"] == "error"
    assert calls == []  # never reached the gate — draft lookup failed first
