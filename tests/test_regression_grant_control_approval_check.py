"""Regression test for a real bug an independent review found, fixed
across two rounds:

Round 1: `PermissionGateway.grant_control()` used to mint a real
capability token for ANY action_type with zero approval-state check at
all -- any in-process caller could self-mint a RED-tier
`run_shell_command` token and walk straight past `_verify_control_token()`'s
own gate, and a caller could mint for an action_type never even
classified in core/config.py's GREEN/YELLOW/RED lists at all (UNKNOWN).

Round 1's fix added an `approved: bool` kwarg the caller simply asserted
-- a SECOND independent review correctly pointed out that remains
forgeable (any caller can pass `approved=True` with zero real proof).

Round 2 (this test file, current): replaced with an internal,
gateway-owned, one-shot receipt ledger (`_issue_approval_receipt()`/
`_consume_approval_receipt()`). Only this file's own `execute()`
(inside `_execute_action()`, reached only after a real approval decision)
or `request_approval()` (after a real owner confirmation) can issue a
receipt. `grant_control()` has no way to be told "trust me" anymore --
it can only consume a receipt that was genuinely, recently issued for
that exact action_type.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real `grant_control()`/`_classify()`/
`_issue_approval_receipt()`/`_consume_approval_receipt()` implementation
directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.loop.permission_gateway import PermissionGateway


def test_red_tier_action_refused_without_a_receipt():
    gw = PermissionGateway()
    assert gw._classify("run_shell_command") == "RED"
    token = gw.grant_control("run_shell_command", uses=1, ttl=60)
    assert token is None, (
        "a RED-tier action must never mint a real capability token "
        "without a real, gateway-issued approval receipt -- this is the "
        "exact self-mint bypass an independent review found live"
    )


def test_grant_control_no_longer_accepts_a_caller_asserted_boolean():
    """Round-1's fix (approved: bool) was itself the bug round 2 fixes --
    lock in that the parameter is genuinely gone, not just defaulted."""
    gw = PermissionGateway()
    import inspect
    sig = inspect.signature(gw.grant_control)
    assert "approved" not in sig.parameters, (
        "grant_control() must not accept any caller-asserted boolean "
        "approval claim again -- approval must be proven via a real, "
        "gateway-issued receipt only"
    )


def test_red_tier_action_mints_with_a_real_receipt():
    gw = PermissionGateway()
    gw._issue_approval_receipt("run_shell_command")
    token = gw.grant_control("run_shell_command", uses=1, ttl=60)
    assert token is not None
    assert gw.verify_control(token, "run_shell_command") is True


def test_receipt_is_one_shot_not_reusable():
    gw = PermissionGateway()
    gw._issue_approval_receipt("run_shell_command")
    first = gw.grant_control("run_shell_command", uses=1, ttl=60)
    assert first is not None
    second = gw.grant_control("run_shell_command", uses=1, ttl=60)
    assert second is None, (
        "a single approval receipt must be consumed exactly once -- "
        "minting a second token off the SAME receipt would let one real "
        "approval be silently stretched into unlimited grants"
    )


def test_receipt_is_bound_to_its_exact_action_type():
    gw = PermissionGateway()
    gw._issue_approval_receipt("launch_app")
    # A receipt for launch_app must not authorize run_shell_command.
    token = gw.grant_control("run_shell_command", uses=1, ttl=60)
    assert token is None, (
        "an approval receipt for one action_type must never authorize a "
        "different action_type"
    )


def test_green_tier_action_still_mints_without_any_receipt():
    """GREEN actions are auto-approved by tier design (e.g. play_music) --
    the fix must not regress the existing, intentional frictionless path."""
    gw = PermissionGateway()
    assert gw._classify("play_music") == "GREEN"
    token = gw.grant_control("play_music", uses=1, ttl=60)
    assert token is not None
    assert gw.verify_control(token, "play_music") is True


def test_unknown_tier_action_refused_without_a_receipt():
    """instagram_post_via_phone/youtube_upload_via_phone (districts/content/
    phone_poster.py) are UNKNOWN -- never added to config.py's tier lists.
    Before the round-1 fix, calling grant_control() for either minted a
    real token with zero check at all."""
    gw = PermissionGateway()
    assert gw._classify("instagram_post_via_phone") == "UNKNOWN"
    token = gw.grant_control("instagram_post_via_phone", uses=1, ttl=60)
    assert token is None


def test_unknown_tier_action_mints_after_a_real_request_approval_confirmation():
    """The legitimate pattern (phone_poster.py): the caller does its OWN
    real owner-approval dance via request_approval() first (a real
    Pushover notify + wait, fails closed on timeout/rejection). This test
    drives the real request_approval() implementation end to end (with
    _wait_for_confirmation patched to simulate the owner tapping Approve,
    the only piece that would otherwise require a live phone) and proves
    grant_control() succeeds immediately afterward with NO explicit proof
    threaded through by the caller -- confirming the receipt request_approval()
    issues internally is what makes this work, not a parameter."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    gw = PermissionGateway()

    async def _run():
        with patch.object(PermissionGateway, "_wait_for_confirmation", new=AsyncMock(return_value=True)):
            with patch.object(PermissionGateway, "_notify", new=AsyncMock(return_value=None)):
                confirmed = await gw.request_approval(
                    "instagram_post_via_phone", "test summary", timeout=1
                )
        assert confirmed is True
        token = gw.grant_control("instagram_post_via_phone", uses=1, ttl=60)
        assert token is not None
        assert gw.verify_control(token, "instagram_post_via_phone") is True

    asyncio.run(_run())


def test_forbidden_action_never_mints_even_with_a_receipt():
    gw = PermissionGateway()
    assert gw._classify("format_drive") == "FORBIDDEN"
    gw._issue_approval_receipt("format_drive")
    token = gw.grant_control("format_drive", uses=1, ttl=60)
    assert token is None, (
        "FORBIDDEN actions must never mint a capability token, regardless "
        "of any receipt -- there is no legitimate path to owner approval "
        "for a permanently forbidden action"
    )


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
