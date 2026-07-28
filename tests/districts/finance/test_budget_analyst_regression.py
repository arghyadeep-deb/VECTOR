"""Regression coverage for KNOWN_ISSUES.md #1's stub-output bug in
BudgetAnalyst.run() — analyse() always built a full markdown report but
run() used to discard it and return a bare {"status": "ok"}, which
avatar/avatar_voice.py::_extract_text() renders as a generic stub. Fixed
2026-07-22 (live-verified at the time) but never got an automated test.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from districts.finance.budget_analyst import BudgetAnalyst

_NARRATIVE_KEYS = ("response", "result", "content", "message", "text", "output")


def _make_agent(tmp_vault: Path) -> BudgetAnalyst:
    agent = BudgetAnalyst()
    (tmp_vault / "Finance").mkdir(parents=True, exist_ok=True)
    agent._obsidian._vault = tmp_vault
    # Avoid a real LLM round-trip and a real episodic-memory DB query in
    # this unit test; testing.md allows mocking external APIs, and the LLM
    # recommendation text isn't what this regression is guarding.
    agent._fetch_category_spend = lambda days=30: {"food": 5000.0}
    agent._get_recommendations = lambda over_budget, hydration: "Cook at home."
    agent._context.session_hydration_prompt = lambda: ""
    return agent


class TestBudgetReportNotAStub:
    def test_run_populates_a_narrative_key(self):
        with tempfile.TemporaryDirectory() as d:
            agent = _make_agent(Path(d))
            result = asyncio.run(agent.run({"type": "analyze_spending", "params": {}}))

        assert any(result.get(k) for k in _NARRATIVE_KEYS), (
            f"run() returned no narrative key from {_NARRATIVE_KEYS} — "
            f"this would render as the generic stub. Got: {result}"
        )
        assert result["status"] == "ok"
        assert "Budget Analysis" in result["response"]

    def test_over_budget_category_appears_in_report(self):
        """food=5000 vs the 3000 default budget should trigger an over-budget alert."""
        with tempfile.TemporaryDirectory() as d:
            agent = _make_agent(Path(d))
            result = asyncio.run(agent.run({"type": "analyze_spending", "params": {}}))

        assert "OVER BUDGET" in result["response"] or "Over-Budget" in result["response"]
        assert "Food" in result["response"]

    def test_write_failure_returns_error_status_not_a_crash(self):
        """If Obsidian write fails, run() should degrade to a clean error dict."""
        with tempfile.TemporaryDirectory() as d:
            agent = _make_agent(Path(d))
            agent._obsidian.write_note = lambda **kw: (_ for _ in ()).throw(OSError("disk full"))
            result = asyncio.run(agent.run({"type": "analyze_spending", "params": {}}))

        assert result["status"] == "error"


if __name__ == "__main__":
    async def _smoke():
        with tempfile.TemporaryDirectory() as d:
            agent = _make_agent(Path(d))
            r = await agent.run({"type": "analyze_spending", "params": {}})
            assert r.get("response"), "budget report stub regression!"
            print("response preview:", r["response"][:100])

    asyncio.run(_smoke())
    print("test_budget_analyst_regression.py OK")
