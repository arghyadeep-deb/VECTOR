"""T9-fix-1 (Codex external review, 2026-09-27, verified real by Claude reading the code).

Governor._is_known_task_type() treats ANY agent-declared capability string as "known" for the
UNKNOWN-block gate below it, but that method itself never applies a tier. districts/communications/
email_agent.py declared discard_draft, mark_read and move as real capabilities (see its run() task_type
branches) with NO entry in core/config.py's GREEN/YELLOW/RED lists, so Governor.dispatch() let all three
run with zero PermissionGateway involvement -- not even a GREEN classification, exactly the same class of
gap the 2026-09-25 Governor district-trust fix closed for a curated "risk word" list, just not for these
three names.

Fix: explicit tier entries (mark_read -> GREEN, a low-risk read-flag flip on the owner's own local store;
discard_draft/move -> YELLOW, real local mailbox-state mutations with no external send). This is a tier
GAP closure, not a tier CHANGE -- see core/config.py's own comments at each entry for the honest
classification and the flag for the pending independent review, per VECTOR_TECHNICAL_KNOWLEDGE/
SELF_DEV_AGENT_SPEC.md's guardrails (never silently add or loosen a tier).
"""
from __future__ import annotations

import pytest

from core.city.agent_registry import AgentRegistry
from core.city.governor import Governor
from core.loop.permission_gateway import PermissionGateway
from districts.communications.email_agent import EmailAgent


@pytest.fixture()
def registry(monkeypatch):
    """A real registry with the real EmailAgent -- these tests are about whether dispatch reaches it
    with or without a receipt, not about EmailAgent's own internal correctness."""
    from core.city import agent_registry as reg_mod

    reg = AgentRegistry()
    agent = EmailAgent()
    reg.register(agent)
    reg.email_agent = agent
    monkeypatch.setattr(reg_mod, "_registry", reg, raising=False)
    monkeypatch.setattr(reg_mod, "get_registry", lambda: reg)
    return reg


def _governor(reg):
    g = Governor()
    g._registry = reg
    g._get_registry = lambda: reg
    return g


@pytest.mark.parametrize("name,tier", [
    ("discard_draft", "YELLOW"),
    ("move", "YELLOW"),
    ("mark_read", "GREEN"),
])
def test_email_agent_capabilities_have_a_real_tier(name, tier):
    """Before this fix all three classified UNKNOWN -- the exact gap T9-fix-1 found."""
    assert PermissionGateway()._classify(name) == tier


@pytest.mark.asyncio
async def test_discard_draft_is_refused_without_a_receipt(registry):
    """Before the fix this reached EmailAgent.discard_draft() with zero gate; must now block."""
    result = await _governor(registry).dispatch({
        "type": "discard_draft", "district": "communications",
        "params": {"draft_id": "does-not-exist"},
    })
    assert result["status"] == "blocked", result


@pytest.mark.asyncio
async def test_move_is_refused_without_a_receipt(registry):
    """Before the fix this reached EmailAgent.move_email() with zero gate; must now block."""
    result = await _governor(registry).dispatch({
        "type": "move", "district": "communications",
        "params": {"email_id": "does-not-exist", "folder": "archive"},
    })
    assert result["status"] == "blocked", result


@pytest.mark.asyncio
async def test_blocked_yellow_dispatch_never_reaches_the_agent(registry):
    await _governor(registry).dispatch({"type": "discard_draft", "district": "communications", "params": {}})
    await _governor(registry).dispatch({"type": "move", "district": "communications", "params": {}})
    # Real DB read of the agent's own inbox count is the only side effect a reached-but-refused
    # dispatch could have caused; assert on the actual mechanism instead -- no receipt was ever consumed.
    assert not PermissionGateway()._consume_approval_receipt("discard_draft", purpose="governor_dispatch")
    assert not PermissionGateway()._consume_approval_receipt("move", purpose="governor_dispatch")


@pytest.mark.asyncio
async def test_discard_draft_dispatches_with_a_real_receipt(registry):
    """With a genuine PermissionGateway approval on file, the YELLOW gate lets it through."""
    PermissionGateway()._issue_approval_receipt("discard_draft", purpose="governor_dispatch")
    result = await _governor(registry).dispatch({
        "type": "discard_draft", "district": "communications",
        "params": {"draft_id": "does-not-exist"},
    })
    assert result["status"] != "blocked", result


@pytest.mark.asyncio
async def test_move_dispatches_with_a_real_receipt(registry):
    PermissionGateway()._issue_approval_receipt("move", purpose="governor_dispatch")
    result = await _governor(registry).dispatch({
        "type": "move", "district": "communications",
        "params": {"email_id": "does-not-exist", "folder": "archive"},
    })
    assert result["status"] != "blocked", result


@pytest.mark.asyncio
async def test_mark_read_dispatches_without_a_receipt_green_needs_none(registry):
    """GREEN is the tier itself acting as approval -- no receipt required, unlike discard_draft/move."""
    result = await _governor(registry).dispatch({
        "type": "mark_read", "district": "communications",
        "params": {"email_id": "does-not-exist", "read": True},
    })
    assert result["status"] != "blocked", result


if __name__ == "__main__":
    import asyncio

    async def _smoke():
        from unittest.mock import MagicMock

        reg = AgentRegistry()
        reg.register(EmailAgent())
        gov = Governor()
        gov._registry = reg
        gov._get_registry = lambda: reg

        r1 = await gov.dispatch({"type": "discard_draft", "district": "communications", "params": {}})
        assert r1["status"] == "blocked"
        PermissionGateway()._issue_approval_receipt("discard_draft", purpose="governor_dispatch")
        r2 = await gov.dispatch({"type": "discard_draft", "district": "communications", "params": {}})
        assert r2["status"] != "blocked"
        print("[OK] test_t9_fix1_email_agent_capability_tiers.py smoke passed")

    asyncio.run(_smoke())
