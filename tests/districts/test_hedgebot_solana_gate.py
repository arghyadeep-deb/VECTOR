"""Real-money gate: hedgebot solana_execute must not sign without owner approval.

Security fix 2026-06-21 (audit + owner rule): signing a Solana swap moves real
on-chain funds. It was gated only by a config boolean — no PermissionGateway.
Now it routes RED through the gateway (notify owner with price + reasoning, sign
only on approval) and FAILS CLOSED if the gateway is unreachable.
"""
import asyncio

import core.loop.permission_gateway as pg
from districts.investment.hedgebot_agent import HedgeBotAgent


class _Result:
    def __init__(self, approved):
        self.approved = approved
        self.reason = "test"


class _FakeGateway:
    def __init__(self, approved=False, raise_it=False):
        self._approved = approved
        self._raise = raise_it

    async def execute(self, action):
        if self._raise:
            raise RuntimeError("gateway down")
        return _Result(self._approved)


def test_denied_swap_is_not_signed(monkeypatch):
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _FakeGateway(approved=False))
    agent = HedgeBotAgent()
    res = asyncio.run(agent.solana_execute("unsigned_tx", "req-abc-123",
                                           expected_price="$1.50", reasoning="oversold dip"))
    assert res["status"] == "denied"  # never reached the signer


def test_gateway_unreachable_fails_closed(monkeypatch):
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _FakeGateway(raise_it=True))
    agent = HedgeBotAgent()
    res = asyncio.run(agent.solana_execute("unsigned_tx", "req-abc-123"))
    assert res["status"] == "blocked"  # gateway down → refuse to sign, NOT fail open


def test_approved_passes_the_gate(monkeypatch):
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _FakeGateway(approved=True))
    agent = HedgeBotAgent()
    res = asyncio.run(agent.solana_execute("unsigned_tx", "req-abc-123"))
    # Gate opened → reaches the executor's config check ('disabled' with no live
    # keys in the test env). The point: it is NOT denied/blocked by the gate.
    assert res["status"] not in ("denied", "blocked")
