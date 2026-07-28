"""Regression coverage for KNOWN_ISSUES.md #1's stub-output bug in
StockAnalyst.run() — this fix (2026-07-22) was live-verified at the time
but never got an automated test, so a future refactor could silently
reintroduce it with nothing catching it.

Bug shape: run() ignored task["type"] entirely for "risk_analysis" and
always returned a bare quote dict with no key
avatar/avatar_voice.py::_extract_text() recognises as narrative text —
the caller got "Task completed - status: ok." instead of any analysis.
"""
from __future__ import annotations

import asyncio

import pytest

from districts.investment.stock_analyst import StockAnalyst

# The 6 keys avatar_voice.py::_extract_text() checks for narrative text.
_NARRATIVE_KEYS = ("response", "result", "content", "message", "text", "output")


def _fake_quote(symbol: str) -> dict:
    return {
        "status": "success", "symbol": symbol, "price": 150.0,
        "day_high": 152.0, "day_low": 148.0, "52w_high": 200.0, "52w_low": 100.0,
        "source": "test",
    }


def _fake_fundamentals(symbol: str) -> dict:
    return {"status": "success", "symbol": symbol, "beta": 1.8, "debt_to_equity": 160.0, "source": "test"}


class TestRiskAnalysisNotAStub:
    def test_risk_analysis_populates_a_narrative_key(self, monkeypatch):
        analyst = StockAnalyst()
        monkeypatch.setattr(analyst, "get_quote", _fake_quote)
        monkeypatch.setattr(analyst, "get_fundamentals", _fake_fundamentals)

        result = asyncio.run(analyst.run({"type": "risk_analysis", "params": {"symbols": ["TEST"]}}))

        assert any(result.get(k) for k in _NARRATIVE_KEYS), (
            f"run() returned no narrative key from {_NARRATIVE_KEYS} — "
            f"this would render as the generic stub. Got: {result}"
        )
        assert "response" in result
        assert "TEST" in result["response"]
        assert len(result["response"]) > 20

    def test_risk_analysis_reflects_high_risk_signals(self, monkeypatch):
        """A high-beta, high-leverage symbol should be flagged, not glossed over."""
        analyst = StockAnalyst()
        monkeypatch.setattr(analyst, "get_quote", _fake_quote)
        monkeypatch.setattr(analyst, "get_fundamentals", _fake_fundamentals)

        result = asyncio.run(analyst.run({"type": "risk_analysis", "params": {"symbol": "TEST"}}))

        assert result["overall_risk"] in ("high", "moderate")
        assert result["holdings"][0]["risk_factors"] != ["no elevated risk factors detected"]

    def test_risk_analysis_accepts_single_symbol_param(self, monkeypatch):
        """run() accepts symbols=[...] OR the singular symbol= param."""
        analyst = StockAnalyst()
        monkeypatch.setattr(analyst, "get_quote", _fake_quote)
        monkeypatch.setattr(analyst, "get_fundamentals", _fake_fundamentals)

        result = asyncio.run(analyst.run({"type": "risk_analysis", "params": {"symbol": "SOLO"}}))
        assert result["holdings"][0]["symbol"] == "SOLO"

    def test_default_quote_path_unaffected(self, monkeypatch):
        """Every non-risk_analysis task_type keeps the pre-existing plain-quote behavior."""
        analyst = StockAnalyst()
        monkeypatch.setattr(analyst, "get_quote", _fake_quote)

        result = asyncio.run(analyst.run({"type": "some_other_type", "params": {"symbol": "TEST"}}))
        # run() does {"status": "ok", **result} — get_quote()'s own "status"
        # (here "success") wins the key collision. Documenting the real
        # behavior, not asserting the naive expectation.
        assert result["status"] == "success"
        assert result["price"] == 150.0


if __name__ == "__main__":
    import sys

    async def _smoke():
        analyst = StockAnalyst()
        analyst.get_quote = _fake_quote
        analyst.get_fundamentals = _fake_fundamentals
        r = await analyst.run({"type": "risk_analysis", "params": {"symbols": ["TEST"]}})
        assert r.get("response"), "risk_analysis stub regression!"
        print("response preview:", r["response"][:100])

    asyncio.run(_smoke())
    print("test_stock_analyst_regression.py OK")
