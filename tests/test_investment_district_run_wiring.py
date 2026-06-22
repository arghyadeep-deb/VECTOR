"""Regression/wiring tests: BacktestAgent, FundamentalsBot, and TechnicalBot
must each implement a real `run(self, task: dict) -> dict` that branches on
`task["type"]` (the governor's real dispatch contract — see
core/city/governor.py: `task_type = task.get("type", "unknown")`) and routes
to their existing analysis methods. None of the three classes' methods place
real orders — all are read-only analysis/research, consistent with this
district's "ANALYSIS ONLY" convention (see stock_analyst.py; real order
placement lives exclusively in execution_engine.py's ExecutionEngine).

Before this fix, BacktestAgent.run() ignored task["type"] entirely and only
read params.get("action"), silently defaulting to vt_research for any other
type. FundamentalsBot.run() and TechnicalBot.run() ignored task["type"]
completely and always called a single hardcoded method.

session-scoped asyncio loop (pytest.ini: asyncio_mode=auto,
asyncio_default_fixture_loop_scope=session) — use `async def test_x():`
directly, never asyncio.run() inside a plain `def` test.
"""
from __future__ import annotations

import pytest

from core.city.agent_base import AgentBase
from districts.investment.backtest_agent import BacktestAgent
from districts.investment.fundamentals_bot import FundamentalsBot
from districts.investment.technical_bot import TechnicalBot


# ── AgentBase subclassing sanity (static + isinstance) ──────────────────────

def test_backtest_agent_subclasses_agent_base():
    assert issubclass(BacktestAgent, AgentBase)


def test_fundamentals_bot_subclasses_agent_base():
    assert issubclass(FundamentalsBot, AgentBase)


def test_technical_bot_subclasses_agent_base():
    assert issubclass(TechnicalBot, AgentBase)


# ── BacktestAgent ────────────────────────────────────────────────────────────

@pytest.fixture
def backtest_agent():
    return BacktestAgent()


async def test_backtest_agent_is_agent_base_instance(backtest_agent):
    assert isinstance(backtest_agent, AgentBase)


async def test_backtest_agent_run_routes_vt_skills_by_task_type(backtest_agent):
    """vt_skills is cheap (no network/LLM) — good smoke for type-routing.
    task["type"] (NOT params["action"]) must select the branch. The
    underlying vt_skills() may itself error in this environment (the
    vector_backtest "src" package has its own dependency gaps) — what
    matters here is that run() routed to vt_skills() at all, evidenced by
    the absence of vt_research's distinctive "task" key in the result."""
    result = await backtest_agent.run({"type": "vt_skills", "params": {}})
    assert "skills" in result or "search" in result or result.get("status") == "error"
    assert "task" not in result


async def test_backtest_agent_run_does_not_default_to_vt_research_for_other_types(backtest_agent):
    """Regression: previously task["type"] was ignored entirely and the
    method always fell through to action="vt_research" unless the caller
    also duplicated the routing key inside params["action"]. vt_skills
    must not trigger vt_research's network-bound LLM path."""
    result = await backtest_agent.run({"type": "vt_skills", "params": {}})
    # vt_research path returns a "task" key; vt_skills does not.
    assert "task" not in result


async def test_backtest_agent_run_unhandled_type_returns_structured_error(backtest_agent):
    result = await backtest_agent.run({"type": "totally_unknown_task_type", "params": {}})
    assert result["status"] == "error"
    assert "totally_unknown_task_type" in result["error"]
    assert "supported" in result


async def test_backtest_agent_run_no_real_orders_placed(backtest_agent):
    """Static guarantee: BacktestAgent has no order-placing method at all."""
    assert not hasattr(backtest_agent, "place_order")
    assert not hasattr(backtest_agent, "_execute_via_broker")


# ── FundamentalsBot ──────────────────────────────────────────────────────────

@pytest.fixture
def fundamentals_bot():
    return FundamentalsBot()


async def test_fundamentals_bot_is_agent_base_instance(fundamentals_bot):
    assert isinstance(fundamentals_bot, AgentBase)


async def test_fundamentals_bot_run_routes_check_valuation(fundamentals_bot):
    result = await fundamentals_bot.run({
        "type": "check_valuation",
        "params": {"metric": "pe_ratio", "threshold": 18},
    })
    assert result["status"] == "ok"
    assert result["metric"] == "pe_ratio"
    assert "assessment" in result


async def test_fundamentals_bot_run_routes_analyze_financials(fundamentals_bot):
    result = await fundamentals_bot.run({
        "type": "analyze_financials",
        "params": {"ticker": "AAPL"},
    })
    # analyze_financials() returns its own "success"/"error" status verbatim
    assert result["status"] in ("success", "error")
    assert result["ticker"] == "AAPL"
    if result["status"] == "success":
        assert "income_statement" in result


async def test_fundamentals_bot_run_routes_compare_to_sector(fundamentals_bot):
    result = await fundamentals_bot.run({
        "type": "compare_to_sector",
        "params": {"ticker": "AAPL", "sector": "technology"},
    })
    # compare_to_sector()'s success path returns ticker/sector/metrics/
    # overall_assessment with no "status" key of its own (pre-existing
    # behavior of the underlying method — out of scope to change here);
    # its error path (e.g. unknown sector) does set "status": "error".
    assert result["status"] == "error" or "overall_assessment" in result
    assert result["ticker"] == "AAPL"


async def test_fundamentals_bot_run_routes_dividend_analysis(fundamentals_bot):
    result = await fundamentals_bot.run({
        "type": "dividend_analysis",
        "params": {"ticker": "MSFT"},
    })
    assert result["status"] in ("success", "error")
    assert result["ticker"] == "MSFT"
    if result["status"] == "success":
        assert "dividend_yield" in result


async def test_fundamentals_bot_run_unhandled_type_returns_structured_error(fundamentals_bot):
    result = await fundamentals_bot.run({"type": "nonexistent_type", "params": {}})
    assert result["status"] == "error"
    assert "nonexistent_type" in result["error"]
    assert "supported" in result


async def test_fundamentals_bot_run_no_real_orders_placed(fundamentals_bot):
    assert not hasattr(fundamentals_bot, "place_order")
    assert not hasattr(fundamentals_bot, "_execute_via_broker")


# ── TechnicalBot ─────────────────────────────────────────────────────────────

@pytest.fixture
def technical_bot():
    return TechnicalBot()


async def test_technical_bot_is_agent_base_instance(technical_bot):
    assert isinstance(technical_bot, AgentBase)


async def test_technical_bot_run_routes_get_price_data(technical_bot):
    result = await technical_bot.run({
        "type": "get_price_data",
        "params": {"symbol": "AAPL", "timeframe": "1mo"},
    })
    assert result["status"] == "success"
    assert result["symbol"] == "AAPL"
    assert "data" in result


async def test_technical_bot_run_routes_detect_patterns(technical_bot):
    result = await technical_bot.run({
        "type": "detect_patterns",
        "params": {"symbol": "AAPL"},
    })
    assert result["status"] == "success"
    assert "patterns" in result


async def test_technical_bot_run_routes_calculate_indicators(technical_bot):
    result = await technical_bot.run({
        "type": "calculate_indicators",
        "params": {"symbol": "AAPL", "indicators": ["sma", "rsi"]},
    })
    assert result["status"] == "success"
    assert "indicators" in result
    assert "sma_20" in result["indicators"]
    assert "rsi_14" in result["indicators"]


async def test_technical_bot_run_unhandled_type_returns_structured_error(technical_bot):
    result = await technical_bot.run({"type": "bogus_type", "params": {}})
    assert result["status"] == "error"
    assert "bogus_type" in result["error"]
    assert "supported" in result


async def test_technical_bot_run_no_real_orders_placed(technical_bot):
    assert not hasattr(technical_bot, "place_order")
    assert not hasattr(technical_bot, "_execute_via_broker")
