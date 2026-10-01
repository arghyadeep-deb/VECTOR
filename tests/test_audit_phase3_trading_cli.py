"""Audit phase 3 - core/trading/cli: import path, path-traversal, failure-as-success.

No network / LLM: the trading graph is replaced by a fake; all output goes to tmp_path.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

typer = pytest.importorskip("typer")
pytest.importorskip("questionary")
pytest.importorskip("langgraph")


def test_cli_modules_import_under_core_trading():
    # Old code did `from cli.models import ...` (no top-level `cli` package) -> ModuleNotFoundError.
    import core.trading.cli.announcements  # noqa: F401
    import core.trading.cli.main  # noqa: F401
    import core.trading.cli.utils  # noqa: F401


@pytest.fixture
def cli_main(monkeypatch, tmp_path):
    import core.trading.cli.main as m

    cfg = dict(m.DEFAULT_CONFIG)
    cfg["results_dir"] = str(tmp_path / "results")
    cfg["data_cache_dir"] = str(tmp_path / "cache")
    monkeypatch.setattr(m, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(m, "message_buffer", m.MessageBuffer())
    return m


def _selections(m, ticker="AAPL", date="2025-01-02"):
    return {
        "ticker": ticker,
        "analysis_date": date,
        "analysts": [m.AnalystType.MARKET],
        "research_depth": 1,
        "llm_provider": "openai",
        "backend_url": None,
        "shallow_thinker": "x",
        "deep_thinker": "y",
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "anthropic_effort": None,
        "output_language": "English",
    }


def _fake_graph_cls(chunks):
    class _Propagator:
        def create_initial_state(self, ticker, date):
            return {"company_of_interest": ticker, "trade_date": date}

        def get_graph_args(self, callbacks=None):
            return {}

    class _Inner:
        def stream(self, state, **kwargs):
            yield from chunks

    class _Graph:
        def __init__(self, *a, **kw):
            self.propagator = _Propagator()
            self.graph = _Inner()

        def process_signal(self, text):
            return "Hold"

    return _Graph


def _no_prompt(monkeypatch, m, answer="N"):
    calls = []

    def fake_prompt(text, default=None, **kw):
        calls.append(text)
        return answer

    monkeypatch.setattr(m.typer, "prompt", fake_prompt)
    return calls


def test_validate_ticker_input_rejects_dot_traversal(cli_main):
    v = cli_main.validate_ticker_input
    assert v("AAPL") is True
    assert v("0700.HK") is True
    assert v("") is True  # empty -> defaults to SPY
    for bad in ("..", ".", "../x", "a/b", "a\\b"):
        assert v(bad) is not True, bad


def test_run_analysis_refuses_traversal_ticker(cli_main, monkeypatch, tmp_path):
    m = cli_main
    monkeypatch.setattr(m, "get_user_selections", lambda: _selections(m, ticker=".."))
    monkeypatch.setattr(m, "VectorTradingGraph", _fake_graph_cls([]))
    _no_prompt(monkeypatch, m)
    with pytest.raises(typer.Exit) as ei:
        m.run_analysis()
    assert ei.value.exit_code == 1
    # "<results>/../<date>" would have been created next to results/ on the old code
    assert not (tmp_path / "2025-01-02").exists()


def test_run_analysis_refuses_malformed_date(cli_main, monkeypatch, tmp_path):
    m = cli_main
    monkeypatch.setattr(m, "get_user_selections", lambda: _selections(m, date="../../evil"))
    monkeypatch.setattr(m, "VectorTradingGraph", _fake_graph_cls([]))
    _no_prompt(monkeypatch, m)
    with pytest.raises(typer.Exit):
        m.run_analysis()
    assert not (tmp_path / "evil").exists()
    assert not (tmp_path / "results" / "AAPL" / ".." / ".." / "evil").exists()


def test_run_analysis_without_final_decision_is_a_failure(cli_main, monkeypatch):
    m = cli_main
    # Stream ends without ever producing a Portfolio Manager decision.
    chunks = [{"messages": [], "market_report": "partial market text"}]
    monkeypatch.setattr(m, "get_user_selections", lambda: _selections(m))
    monkeypatch.setattr(m, "VectorTradingGraph", _fake_graph_cls(chunks))
    calls = _no_prompt(monkeypatch, m)
    with pytest.raises(typer.Exit) as ei:  # old code: KeyError traceback / blank success
        m.run_analysis()
    assert ei.value.exit_code == 1
    assert calls == []  # never offered to "save" a failed analysis


def test_run_analysis_blank_final_decision_is_a_failure(cli_main, monkeypatch):
    m = cli_main
    chunks = [{"messages": [], "final_trade_decision": "   "}]
    monkeypatch.setattr(m, "get_user_selections", lambda: _selections(m))
    monkeypatch.setattr(m, "VectorTradingGraph", _fake_graph_cls(chunks))
    _no_prompt(monkeypatch, m)
    with pytest.raises(typer.Exit) as ei:
        m.run_analysis()
    assert ei.value.exit_code == 1


def test_run_analysis_happy_path_still_completes(cli_main, monkeypatch, tmp_path):
    m = cli_main
    chunks = [{
        "messages": [],
        "market_report": "m",
        "investment_plan": "i",
        "trader_investment_plan": "t",
        "final_trade_decision": "**Rating**: Buy",
    }]
    monkeypatch.setattr(m, "get_user_selections", lambda: _selections(m))
    monkeypatch.setattr(m, "VectorTradingGraph", _fake_graph_cls(chunks))
    _no_prompt(monkeypatch, m, answer="N")
    m.run_analysis()  # must not raise
    assert (tmp_path / "results" / "AAPL" / "2025-01-02" / "reports" / "market_report.md").exists()


def test_missing_report_sections_only_requires_selected_analysts(cli_main):
    m = cli_main
    state = {
        "market_report": "x",
        "news_report": "",  # not selected -> not required
        "investment_plan": "p",
        "trader_investment_plan": "",  # required, blank
        "final_trade_decision": "d",
    }
    assert m.missing_report_sections(state, ["market"]) == ["trader_investment_plan"]
    assert "news_report" in m.missing_report_sections(state, ["market", "news"])


def test_saved_report_flags_incomplete_analysis(cli_main, tmp_path):
    m = cli_main
    state = {"market_report": "only this"}
    f = m.save_report_to_disk(state, "AAPL", tmp_path / "r1", missing=["final_trade_decision"])
    text = f.read_text(encoding="utf-8")
    assert "INCOMPLETE ANALYSIS" in text and "final_trade_decision" in text
    ok = m.save_report_to_disk(state, "AAPL", tmp_path / "r2")
    assert "INCOMPLETE" not in ok.read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", ["{[]: 1}", "{[]}", "(" * 100000 + ")" * 100000, "[" * 100000])
def test_extract_content_string_survives_hostile_text(cli_main, payload):
    # LLM/tool (web-fetched) text reaches ast.literal_eval; it must never crash the run.
    out = cli_main.extract_content_string(payload)
    assert out == payload.strip()


def test_extract_content_string_still_drops_empty_literals(cli_main):
    assert cli_main.extract_content_string("[]") is None
    assert cli_main.extract_content_string("real text") == "real text"


def test_get_analysis_date_normalises_and_rejects_future(cli_main, monkeypatch):
    m = cli_main
    answers = iter(["2999-01-01", "2024-1-5"])
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: next(answers))
    assert m.get_analysis_date() == "2024-01-05"
