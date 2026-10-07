"""Audit phase 3: core/trading dataflows + crypto_trading. No real network."""
import asyncio
import io
import json
import types
import urllib.error
import urllib.request

import pandas as pd
import pytest
import httpx

from core.trading.dataflows import (
    alpha_vantage_common as avc,
    alpha_vantage_fundamentals as avf,
    reddit,
    stocktwits,
    stockstats_utils as su,
    y_finance,
)
from core.trading import crypto_trading

SECRET = "SUPERSECRETKEY123"


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} Client Error for url: "
                f"https://www.alphavantage.co/query?apikey={SECRET}",
                request=httpx.Request("GET", "https://www.alphavantage.co/query"),
                response=httpx.Response(self.status_code),
            )


@pytest.fixture
def av(monkeypatch):
    monkeypatch.setattr(avc, "get_api_key", lambda: SECRET)

    def install(resp=None, exc=None, seen=None):
        def fake_get(url, params=None, **kw):
            if seen is not None:
                seen.update(kw)
            if exc:
                raise exc
            return resp
        monkeypatch.setattr(avc.httpx, "get", fake_get)
    return install


# ---- Alpha Vantage: API error bodies returned as HTTP 200 -----------------
@pytest.mark.parametrize("body", [
    {"Note": "Thank you for using Alpha Vantage! 5 calls per minute."},
    {"Information": "Our standard API call frequency is 25 requests per day."},
    {"Information": "This is a premium endpoint."},  # old code: only matched 'rate limit'/'api key'
])
def test_av_usage_notice_raises_not_data(av, body):
    av(_Resp(json.dumps(body)))
    with pytest.raises(avc.AlphaVantageRateLimitError):
        avc._make_api_request("TIME_SERIES_DAILY", {"symbol": "IBM"})


def test_av_error_message_raises(av):
    av(_Resp(json.dumps({"Error Message": "Invalid API call."})))
    with pytest.raises(ValueError):
        avc._make_api_request("OVERVIEW", {"symbol": "ZZZZ"})


def test_av_empty_json_raises(av):
    av(_Resp("{}"))
    with pytest.raises(ValueError):
        avc._make_api_request("OVERVIEW", {"symbol": "ZZZZ"})


def test_av_csv_still_returned(av):
    av(_Resp("timestamp,close\n2024-01-02,10\n"))
    assert avc._make_api_request("X", {}).startswith("timestamp")


# ---- Alpha Vantage: apikey leak via exception text ------------------------
def test_av_http_error_does_not_leak_key(av):
    av(_Resp("", status=500))
    with pytest.raises(RuntimeError) as ei:
        avc._make_api_request("RSI", {"symbol": "IBM"})
    assert SECRET not in str(ei.value) and SECRET not in repr(ei.value.__cause__)


def test_av_connection_error_does_not_leak_key_and_has_timeout(av):
    seen = {}
    av(exc=httpx.ConnectError(f"Max retries exceeded with url: /query?apikey={SECRET}"), seen=seen)
    with pytest.raises(RuntimeError) as ei:
        avc._make_api_request("RSI", {"symbol": "IBM"})
    assert SECRET not in str(ei.value)
    av(_Resp("a,b\n1,2\n"), seen=seen)
    avc._make_api_request("RSI", {})
    assert seen.get("timeout")


def test_av_indicator_error_string_has_no_key(av):
    from core.trading.dataflows.alpha_vantage_indicator import get_indicator
    av(_Resp("", status=500))
    out = get_indicator("IBM", "rsi", "2024-01-10", 5)
    assert SECRET not in out


# ---- Alpha Vantage: filter failure must not return unfiltered (future) data
def test_av_csv_filter_failure_does_not_return_unfiltered():
    bad = "timestamp,close\nnot-a-date,1\n2099-01-01,2\n"
    with pytest.raises(ValueError):
        avc._filter_csv_by_date_range(bad, "2024-01-01", "2024-01-10")


def test_av_csv_filter_basic():
    csv = "timestamp,close\n2024-01-02,1\n2024-01-10,2\n2024-01-11,3\n"
    out = avc._filter_csv_by_date_range(csv, "2024-01-01", "2024-01-10")
    assert "2024-01-10" in out and "2024-01-11" not in out


# ---- Alpha Vantage: look-ahead filter was dead for str results ------------
def test_av_balance_sheet_filters_future_reports(av):
    body = {"symbol": "IBM", "annualReports": [
        {"fiscalDateEnding": "2023-12-31"}, {"fiscalDateEnding": "2025-12-31"}],
        "quarterlyReports": [{"fiscalDateEnding": "2024-03-31"}, {"fiscalDateEnding": "2022-03-31"}]}
    av(_Resp(json.dumps(body)))
    out = json.loads(avf.get_balance_sheet("IBM", curr_date="2024-01-10"))
    assert [r["fiscalDateEnding"] for r in out["annualReports"]] == ["2023-12-31"]
    assert [r["fiscalDateEnding"] for r in out["quarterlyReports"]] == ["2022-03-31"]


# ---- yfinance cache: empty download poisoning + non-atomic write ----------
@pytest.fixture
def cache(monkeypatch, tmp_path):
    cfg = {"data_cache_dir": str(tmp_path)}
    monkeypatch.setattr(su, "get_config", lambda: cfg)
    return tmp_path


def test_empty_download_not_cached_and_raises(monkeypatch, cache):
    monkeypatch.setattr(su.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError):
        su.load_ohlcv("AAPL", "2024-01-10")
    assert list(cache.iterdir()) == []


def test_cache_write_is_atomic(monkeypatch, cache):
    df = pd.DataFrame({"Date": pd.to_datetime(["2024-01-02"]), "Close": [1.0],
                       "Open": [1.0], "High": [1.0], "Low": [1.0], "Volume": [1]}).set_index("Date")
    monkeypatch.setattr(su.yf, "download", lambda *a, **k: df)
    real = pd.DataFrame.to_csv

    def partial_then_die(self, path, *a, **k):
        with open(path, "w") as f:
            f.write("Date,Close\n2024-01-02,1.0\n")  # truncated
        raise OSError("disk full")
    monkeypatch.setattr(pd.DataFrame, "to_csv", partial_then_die)
    with pytest.raises(OSError):
        su.load_ohlcv("AAPL", "2024-01-10")
    monkeypatch.setattr(pd.DataFrame, "to_csv", real)
    assert [p for p in cache.iterdir() if p.suffix == ".csv"] == []
    assert list(cache.iterdir()) == []  # temp file cleaned up too


def test_load_ohlcv_traversal_rejected(cache):
    with pytest.raises(ValueError):
        su.load_ohlcv("../../etc/x", "2024-01-10")


# ---- yfinance end date exclusive -> end_date bar dropped ------------------
def test_yfin_online_end_date_inclusive(monkeypatch):
    seen = {}

    class T:
        def __init__(self, s): pass
        def history(self, start=None, end=None):
            seen["end"] = end
            return pd.DataFrame()
    monkeypatch.setattr(y_finance.yf, "Ticker", T)
    y_finance.get_YFin_data_online("AAPL", "2024-01-02", "2024-01-10")
    assert seen["end"] == "2024-01-11"


# ---- indicator failure must not become a blank value ----------------------
def test_stockstats_indicator_failure_not_blank(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(y_finance.StockstatsUtils, "get_stock_stats", staticmethod(boom))
    out = y_finance.get_stockstats_indicator("AAPL", "rsi", "2024-01-10")
    assert out.strip() != "" and out.startswith("Error")


# ---- Reddit / StockTwits --------------------------------------------------
def _boom_urlopen(*a, **k):
    raise urllib.error.URLError("down")


def test_reddit_failure_not_reported_as_no_posts(monkeypatch):
    monkeypatch.setattr(reddit, "urlopen", _boom_urlopen)
    out = reddit.fetch_reddit_posts("AAPL", inter_request_delay=0)
    assert "no Reddit posts found" not in out and "no posts found" not in out
    assert "unavailable" in out.lower()


def test_reddit_genuine_empty_still_says_no_posts(monkeypatch):
    monkeypatch.setattr(reddit, "urlopen",
                        lambda *a, **k: io.BytesIO(json.dumps({"data": {"children": []}}).encode()))
    out = reddit.fetch_reddit_posts("AAPL", inter_request_delay=0)
    assert "no Reddit posts found" in out


def test_reddit_connection_reset_does_not_raise(monkeypatch):
    def reset(*a, **k):
        raise ConnectionResetError("x")
    monkeypatch.setattr(reddit, "urlopen", reset)
    assert "unavailable" in reddit.fetch_reddit_posts("AAPL", inter_request_delay=0).lower()


def test_stocktwits_error_envelope_not_no_messages(monkeypatch):
    body = json.dumps({"response": {"status": 429}, "errors": [{"message": "Rate limit exceeded"}]})
    monkeypatch.setattr(stocktwits, "urlopen", lambda *a, **k: io.BytesIO(body.encode()))
    out = stocktwits.fetch_stocktwits_messages("AAPL")
    assert "unavailable" in out and "no StockTwits messages" not in out


def test_stocktwits_ticker_is_url_quoted(monkeypatch):
    seen = {}

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        return io.BytesIO(b'{"messages": []}')
    monkeypatch.setattr(stocktwits, "urlopen", fake)
    stocktwits.fetch_stocktwits_messages("AAPL/../../x?y=1")
    assert seen["url"].startswith("https://api.stocktwits.com/api/2/streams/symbol/")
    assert seen["url"].endswith(".json") and "/../" not in seen["url"] and "?" not in seen["url"]


# ---- crypto_trading: 0.0 price flowing into analysis ----------------------
def _fake_yf(monkeypatch, fast_info=None, exc=None):
    import sys
    class T:
        def __init__(self, s):
            if exc:
                raise exc
            self.fast_info = fast_info
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=T))


def test_crypto_quote_missing_last_price_is_not_zero(monkeypatch):
    _fake_yf(monkeypatch, fast_info=types.SimpleNamespace())
    q = asyncio.run(crypto_trading.CryptoTradingAgent().get_quote("BTC"))
    assert q["price"] is None and q.get("error")


@pytest.mark.parametrize("bad", [0.0, float("nan"), -1.0, None])
def test_crypto_quote_invalid_price_rejected(monkeypatch, bad):
    _fake_yf(monkeypatch, fast_info=types.SimpleNamespace(last_price=bad))
    q = asyncio.run(crypto_trading.CryptoTradingAgent().get_quote("BTC"))
    assert q["price"] is None and q.get("error")


def test_crypto_quote_failure_price_none(monkeypatch):
    _fake_yf(monkeypatch, exc=RuntimeError("boom"))
    q = asyncio.run(crypto_trading.CryptoTradingAgent().get_quote("BTC"))
    assert q["price"] is None and "boom" in q["error"]


def test_crypto_quote_ok(monkeypatch):
    _fake_yf(monkeypatch, fast_info=types.SimpleNamespace(last_price=65000.5))
    q = asyncio.run(crypto_trading.CryptoTradingAgent().get_quote("BTC"))
    assert q["price"] == 65000.5 and "error" not in q
