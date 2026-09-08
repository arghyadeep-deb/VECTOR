"""Trust ladder — earned autonomy for YELLOW actions (2026-07-02).

Unit tests exercise the TrustLadder state machine on an in-memory DB.
Integration tests run the REAL PermissionGateway (never mocked, testing.md)
with VECTOR_TRUST_TEST=1 so trust recording is active in pytest.
"""

import sys
import asyncio
import sqlite3
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loop.trust_ladder import TrustLadder
from core.loop.permission_gateway import PermissionGateway, Action


THRESHOLD = 20  # config default trust_promotion_streak


@pytest.fixture
def ladder():
    return TrustLadder(conn=sqlite3.connect(":memory:"))


# ── unit: state machine ──────────────────────────────────────────────────────

def test_streak_below_threshold_not_promoted(ladder):
    for _ in range(THRESHOLD - 1):
        assert ladder.record_approval("commit_code") is False
    assert ladder.is_promoted("commit_code") is False


def test_threshold_promotes(ladder):
    for _ in range(THRESHOLD - 1):
        ladder.record_approval("commit_code")
    assert ladder.record_approval("commit_code") is True
    assert ladder.is_promoted("commit_code") is True


def test_rejection_resets_streak_and_demotes(ladder):
    for _ in range(THRESHOLD):
        ladder.record_approval("commit_code")
    assert ladder.is_promoted("commit_code")
    ladder.record_rejection("commit_code")
    assert ladder.is_promoted("commit_code") is False
    row = ladder.status()[0]
    assert row["streak"] == 0
    assert row["demote_reason"] == "owner rejected"


def test_bad_outcome_demotes(ladder):
    for _ in range(THRESHOLD):
        ladder.record_approval("commit_code")
    ladder.record_bad_outcome("commit_code")
    assert ladder.is_promoted("commit_code") is False
    assert ladder.status()[0]["bad_outcomes"] == 1


def test_bad_outcome_blocks_future_promotion(ladder):
    # An action with a failure on record must not promote on streak alone.
    ladder.record_bad_outcome("commit_code")
    for _ in range(THRESHOLD + 5):
        assert ladder.record_approval("commit_code") is False
    assert ladder.is_promoted("commit_code") is False


def test_manual_promote_and_demote(ladder):
    ladder.promote("send_message_routine")
    assert ladder.is_promoted("send_message_routine")
    ladder.demote("send_message_routine", "owner via API")
    assert not ladder.is_promoted("send_message_routine")


def test_streaks_are_per_action_type(ladder):
    for _ in range(THRESHOLD):
        ladder.record_approval("commit_code")
    assert ladder.is_promoted("commit_code")
    assert ladder.is_promoted("download_file") is False


def test_recent_changes_digest(ladder):
    for _ in range(THRESHOLD):
        ladder.record_approval("commit_code")
    ladder.promote("set_reminder")
    ladder.demote("set_reminder", "manual")
    changes = ladder.recent_changes(days=7)
    assert {p["action_type"] for p in changes["promoted"]} == {"commit_code"}
    assert {d["action_type"] for d in changes["demoted"]} == {"set_reminder"}


def test_unknown_db_fails_closed():
    class _Boom:
        def execute(self, *a, **kw):
            raise RuntimeError("db down")

        def commit(self):
            raise RuntimeError("db down")

    t = TrustLadder(conn=_Boom())
    assert t.is_promoted("anything") is False  # no DB → no auto-execution


# ── integration: REAL gateway ────────────────────────────────────────────────

@pytest.fixture
def gateway_with_ladder(monkeypatch):
    """Real PermissionGateway wired to an in-memory trust ladder."""
    monkeypatch.setenv("VECTOR_TRUST_TEST", "1")
    # VECTOR_YELLOW_AUTO_CONFIRM=1 is set in this machine's real .env (an
    # owner convenience choice) and permission_gateway.py reads it live from
    # os.environ, not a cached config value — left set, a pytest-mode YELLOW
    # timeout (0.01s) is treated as auto-confirmed instead of rejected,
    # which legitimately flips test_unpromoted_yellow_still_gated's result.
    # Same guard tests/unit/test_permission_gateway_extra.py already uses.
    monkeypatch.delenv("VECTOR_YELLOW_AUTO_CONFIRM", raising=False)
    ladder = TrustLadder(conn=sqlite3.connect(":memory:"))
    import core.loop.trust_ladder as tl
    monkeypatch.setattr(tl, "_ladder", ladder)
    return PermissionGateway(), ladder


@pytest.mark.asyncio
async def test_promoted_yellow_auto_executes(gateway_with_ladder, monkeypatch):
    monkeypatch.delenv("VECTOR_YELLOW_AUTO_CONFIRM", raising=False)
    gw, ladder = gateway_with_ladder
    ladder.promote("set_reminder")
    result = await gw.execute(Action("set_reminder", {"text": "test"}, "pytest"))
    assert result.approved and result.executed
    assert result.reason == "Auto-executed (trust ladder)"
    assert ladder.status()[0]["auto_execs"] == 1


@pytest.mark.asyncio
async def test_unpromoted_yellow_still_gated(gateway_with_ladder, monkeypatch):
    # 2026-08-12: isolate from .env state — VECTOR_YELLOW_AUTO_CONFIRM=1 in
    # the owner's .env would auto-approve YELLOW actions, bypassing the trust
    # ladder gate this test is verifying. Same fix as
    # tests/unit/test_permission_gateway_extra.py:53-55.
    monkeypatch.delenv("VECTOR_YELLOW_AUTO_CONFIRM", raising=False)
    gw, ladder = gateway_with_ladder
    # No promotion → normal YELLOW flow: pytest timeout (0.01s) → rejected.
    result = await gw.execute(Action("set_reminder", {"text": "test"}, "pytest"))
    assert result.approved is False
    assert result.reason == "Rejected by owner"
    # Timeout is neutral — no rejection recorded, streak untouched.
    rows = ladder.status()
    assert not rows or rows[0]["total_rejections"] == 0


@pytest.mark.asyncio
async def test_red_never_uses_trust(gateway_with_ladder):
    gw, ladder = gateway_with_ladder
    ladder.promote("send_email")  # even if promoted somehow...
    result = await gw.execute(Action("send_email", {"to": "x"}, "pytest"))
    # ...RED still requires owner approval (pytest 1s timeout → rejected).
    assert result.approved is False
    assert "trust" not in result.reason.lower()


@pytest.mark.asyncio
async def test_forbidden_never_uses_trust(gateway_with_ladder):
    gw, ladder = gateway_with_ladder
    ladder.promote("mass_delete")  # in the gateway's FORBIDDEN list
    result = await gw.execute(Action("mass_delete", {}, "pytest"))
    assert result.approved is False
    assert result.level == "FORBIDDEN"


@pytest.mark.asyncio
async def test_disabled_ladder_restores_old_behavior(gateway_with_ladder, monkeypatch):
    gw, ladder = gateway_with_ladder
    ladder.promote("set_reminder")
    from core.config import CONFIG
    monkeypatch.setitem(CONFIG["permission"], "trust_ladder_enabled", False)
    result = await gw.execute(Action("set_reminder", {"text": "t"}, "pytest"))
    # Disabled → promoted or not, YELLOW goes through the owner gate.
    assert result.reason != "Auto-executed (trust ladder)"


async def _when_pending(gw, action_type: str, fn, tries: int = 5000):
    """Poll until the gateway registers the pending event, then act on it.
    (The event only exists once _wait_for_confirmation starts; the notify
    call before it may spend real wall time, so poll on the clock.)

    F-1: pending approvals are keyed by a unique id (action_type#seq), not the
    bare action_type, so poll get_pending() for the action_type rather than the
    raw _pending_events key. confirm_action()/reject() still accept the bare
    action_type and resolve it when a single instance is pending."""
    for _ in range(tries):
        if any(p.get("action_type") == action_type for p in gw.get_pending()):
            return fn()
        await asyncio.sleep(0.001)
    raise AssertionError(f"{action_type} never became pending")


def _silence_notify(gw):
    """Pushover is an external API (mocking allowed) — and removing its wall
    time makes the 10ms pytest YELLOW window deterministic under load."""
    async def _noop(message, priority=0, url="", url_title=""):
        return None
    gw._notify = _noop


@pytest.mark.asyncio
async def test_explicit_approval_feeds_streak(gateway_with_ladder, monkeypatch):
    monkeypatch.delenv("VECTOR_YELLOW_AUTO_CONFIRM", raising=False)
    gw, ladder = gateway_with_ladder
    _silence_notify(gw)
    task = asyncio.create_task(
        _when_pending(gw, "set_reminder", lambda: gw.confirm_action("set_reminder")))
    result = await gw.execute(Action("set_reminder", {"text": "t"}, "pytest"))
    await task
    assert result.approved
    assert ladder.status()[0]["streak"] == 1
    assert ladder.status()[0]["total_approvals"] == 1


@pytest.mark.asyncio
async def test_explicit_rejection_feeds_ladder(gateway_with_ladder, monkeypatch):
    monkeypatch.delenv("VECTOR_YELLOW_AUTO_CONFIRM", raising=False)
    gw, ladder = gateway_with_ladder
    _silence_notify(gw)
    task = asyncio.create_task(
        _when_pending(gw, "set_reminder", lambda: gw.reject("set_reminder")))
    result = await gw.execute(Action("set_reminder", {"text": "t"}, "pytest"))
    await task
    assert result.approved is False
    assert ladder.status()[0]["total_rejections"] == 1
    assert ladder.status()[0]["streak"] == 0


if __name__ == "__main__":
    # real test, no mocks
    t = TrustLadder(conn=sqlite3.connect(":memory:"))
    for _ in range(20):
        t.record_approval("x")
    print("✅ test_trust_ladder OK" if t.is_promoted("x") else "❌ FAILED")
