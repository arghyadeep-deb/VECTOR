"""Audit phase 3: core/trading/graph + core/trading/llm_clients regressions.

No network, no real LLM: fakes + tmp_path only.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, TypedDict
from unittest.mock import MagicMock

import pytest
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger

import core.trading.graph.trading_graph as tg
from core.trading.agents.utils.memory import TradingMemoryLog
from core.trading.graph.checkpointer import (
    clear_all_checkpoints,
    clear_checkpoint,
    get_checkpointer,
)
from core.trading.graph.propagation import Propagator
from core.trading.graph.signal_processing import SignalProcessor
from core.trading.graph.trading_graph import VectorTradingGraph


@pytest.fixture
def log_sink():
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(str(m)), level="DEBUG", format="{message}")
    yield messages
    logger.remove(sink_id)


# --------------------------------------------------------------- signal processing


def test_negated_label_does_not_become_buy():
    # old: "Rating: Not Buy\nHold" -> "Buy" (fail-open on a negated rating)
    assert SignalProcessor().process_signal("Rating: Not Buy\nHold") == "Hold"


def test_negated_bare_word_does_not_become_buy():
    # old: -> "Buy"
    assert SignalProcessor().process_signal("Do not Buy this stock.") == "Hold"


def test_none_decision_defaults_to_hold_instead_of_crashing():
    # old: AttributeError ('NoneType' has no attribute 'splitlines')
    assert SignalProcessor().process_signal(None) == "Hold"


def test_explicit_label_still_wins_over_prose_negation():
    text = "Do not hesitate, the thesis is strong.\n**Rating**: Overweight"
    assert SignalProcessor().process_signal(text) == "Overweight"


# --------------------------------------------------------------- resume / state


class _S(TypedDict):
    messages: Annotated[list, add_messages]
    company_of_interest: str
    trade_date: str
    past_context: str
    investment_debate_state: dict
    risk_debate_state: dict
    market_report: str
    fundamentals_report: str
    sentiment_report: str
    news_report: str
    investment_plan: str
    trader_investment_plan: str
    final_trade_decision: str


def _make_graph(tmp_path, calls, crash):
    def analyst(state):
        calls.append("analyst")
        return {"market_report": "R"}

    def manager(state):
        calls.append("manager")
        if crash[0]:
            raise RuntimeError("simulated crash")
        return {
            "final_trade_decision": "Rating: Hold",
            "investment_plan": "p",
            "trader_investment_plan": "t",
        }

    wf = StateGraph(_S)
    wf.add_node("analyst", analyst)
    wf.add_node("manager", manager)
    wf.set_entry_point("analyst")
    wf.add_edge("analyst", "manager")
    wf.add_edge("manager", END)

    g = object.__new__(VectorTradingGraph)
    g.config = {
        "checkpoint_enabled": True,
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
    }
    g.debug = False
    g.callbacks = []
    g.workflow = wf
    g.graph = wf.compile()
    g._checkpointer_ctx = None
    g.propagator = Propagator()
    g.signal_processor = SignalProcessor()
    g.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "mem.md")})
    g.log_states_dict = {}
    g.curr_state = None
    g.ticker = None
    return g


def test_checkpoint_resume_does_not_rerun_completed_nodes(tmp_path):
    calls: list[str] = []
    crash = [True]
    g = _make_graph(tmp_path, calls, crash)

    with pytest.raises(RuntimeError):
        g.propagate("NVDA", "2026-01-10")
    assert calls == ["analyst", "manager"]

    crash[0] = False
    state, rating = g.propagate("NVDA", "2026-01-10")

    # old: analyst ran again -> ["analyst","manager","analyst","manager"]
    assert calls == ["analyst", "manager", "manager"]
    # old: the human message was appended a second time (2 messages)
    assert len(state["messages"]) == 1
    assert rating == "Hold"


# --------------------------------------------------------------- input validation


@pytest.mark.parametrize(
    "ticker,date",
    [("../../etc/x", "2026-01-10"), ("NVDA", "../../x"), ("NVDA", "2026-13-45"), ("NVDA", "10/01/2026")],
)
def test_propagate_rejects_bad_ticker_or_date_before_any_work(tmp_path, ticker, date):
    g = _make_graph(tmp_path, [], [False])
    g._resolve_pending_entries = MagicMock()
    g._run_graph = MagicMock()
    with pytest.raises(ValueError):
        g.propagate(ticker, date)
    # old: pending-entry resolution (yfinance + LLM) and the whole graph run happened first
    g._resolve_pending_entries.assert_not_called()
    g._run_graph.assert_not_called()


# --------------------------------------------------------------- reflection / outcomes


def _graph_with_pending(tmp_path, reflector):
    g = object.__new__(VectorTradingGraph)
    g.config = {}
    g.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "mem.md")})
    g.memory_log.store_decision("NVDA", "2026-01-10", "Rating: Buy\nbuy it")
    g.reflector = reflector
    g._fetch_returns = lambda *a, **k: (0.05, 0.02, 5)
    return g


def test_reflection_llm_failure_keeps_entry_pending_and_does_not_abort(tmp_path):
    reflector = MagicMock()
    reflector.reflect_on_final_decision.side_effect = RuntimeError("llm down")
    g = _graph_with_pending(tmp_path, reflector)
    g._resolve_pending_entries("NVDA")  # old: RuntimeError aborted the whole analysis run
    assert len(g.memory_log.get_pending_entries()) == 1


def test_blank_reflection_is_not_recorded_as_resolved(tmp_path):
    reflector = MagicMock()
    reflector.reflect_on_final_decision.return_value = "   "
    g = _graph_with_pending(tmp_path, reflector)
    g._resolve_pending_entries("NVDA")
    # old: entry resolved with an empty reflection and never retried
    assert len(g.memory_log.get_pending_entries()) == 1


def test_good_reflection_resolves_entry(tmp_path):
    reflector = MagicMock()
    reflector.reflect_on_final_decision.return_value = "Call was right."
    g = _graph_with_pending(tmp_path, reflector)
    g._resolve_pending_entries("NVDA")
    assert g.memory_log.get_pending_entries() == []


def test_nan_close_is_not_a_resolved_outcome(monkeypatch):
    import pandas as pd

    class _FakeTicker:
        def __init__(self, sym):
            self.sym = sym

        def history(self, start, end):
            close = [float("nan"), 10.0, 11.0] if self.sym == "NVDA" else [100.0, 101.0, 102.0]
            return pd.DataFrame({"Close": close})

    monkeypatch.setattr(tg.yf, "Ticker", _FakeTicker)
    g = object.__new__(VectorTradingGraph)
    # old: (nan, nan, 2) -> logged as "+nan%" outcome and reflected on
    assert g._fetch_returns("NVDA", "2026-01-10", benchmark="SPY") == (None, None, None)


def test_fetch_returns_failure_logs_with_loguru_formatting(log_sink):
    g = object.__new__(VectorTradingGraph)
    assert g._fetch_returns("NVDA", "2026-99-99") == (None, None, None)
    joined = "\n".join(log_sink)
    # old: stdlib logging with %s placeholders, never reached the loguru sink
    assert "NVDA" in joined and "2026-99-99" in joined and "%s" not in joined


# --------------------------------------------------------------- checkpointer


def test_clear_all_checkpoints_removes_wal_and_shm_sidecars(tmp_path):
    with get_checkpointer(tmp_path, "AAPL"):
        pass
    cp_dir = tmp_path / "checkpoints"
    (cp_dir / "AAPL.db-wal").write_bytes(b"stale")
    (cp_dir / "AAPL.db-shm").write_bytes(b"stale")
    assert clear_all_checkpoints(tmp_path) == 1
    # old: sidecars survived and could be replayed into the next AAPL.db
    assert list(cp_dir.iterdir()) == []


def test_clear_checkpoint_failure_logs_context_not_placeholder(tmp_path, log_sink):
    cp_dir = tmp_path / "checkpoints"
    cp_dir.mkdir()
    sqlite3.connect(cp_dir / "MSFT.db").close()  # DB without writes/checkpoints tables
    clear_checkpoint(tmp_path, "MSFT", "2026-01-10")
    joined = "\n".join(log_sink)
    # old: literal "[VECTOR] suppressed exception (degraded mode)"
    assert "suppressed exception" not in joined
    assert "MSFT" in joined and "2026-01-10" in joined and "no such table" in joined


# --------------------------------------------------------------- llm clients


def test_azure_client_honours_explicit_base_url(monkeypatch):
    from core.trading.llm_clients.azure_client import AzureOpenAIClient

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://env-endpoint.openai.azure.com/")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-03-01-preview")
    llm = AzureOpenAIClient("gpt-5", base_url="https://explicit.openai.azure.com/").get_llm()
    # old: explicit base_url silently ignored in favour of the env endpoint
    assert llm.azure_endpoint == "https://explicit.openai.azure.com/"
