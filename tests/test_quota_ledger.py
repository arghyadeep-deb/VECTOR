"""Quota ledger — soft free-tier budgets with auto-rotate (2026-07-02).

Offline; injected tmp paths + simulated clock. Uses the real model_catalog
limits (measured Groq/Cerebras/Mistral numbers) as ground truth.
"""

import sys
import json
import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inference.quota_ledger import QuotaLedger, _PROVIDER_KEY


class FakeProv:
    def __init__(self, slug):
        self.slug = slug


@pytest.fixture
def clock():
    return {"now": 100_000.0}


@pytest.fixture
def led(tmp_path, clock):
    return QuotaLedger(path=tmp_path / "q.json", clock=lambda: clock["now"])


def _fill(led, provider, bucket, requests=0, tokens=0):
    day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    led._data.setdefault(day, {}).setdefault(provider, {})[bucket] = {
        "requests": requests, "tokens": tokens}


# ── saturation per unit type (real catalog limits) ───────────────────────────

def test_groq_requests_per_day(led):
    # openai/gpt-oss-20b: 1,000/day (assumed limit in model_catalog.yaml)
    _fill(led, "groq", "openai/gpt-oss-20b", requests=830)
    assert not led.deprioritized("groq", "openai/gpt-oss-20b")   # 83%
    _fill(led, "groq", "openai/gpt-oss-20b", requests=903)
    assert led.deprioritized("groq", "openai/gpt-oss-20b")       # 90.3%


def test_cerebras_tokens_per_day_bind(led):
    # 1M tokens/day is the binding constraint, not the 2,400 req/day
    _fill(led, "cerebras", "gpt-oss-120b", requests=10, tokens=950_000)
    assert led.deprioritized("cerebras", "gpt-oss-120b")


def test_cloudflare_neurons_vs_tokens(led):
    # provider-wide 10K neurons/day compared against the tokens counter
    _fill(led, "cloudflare", _PROVIDER_KEY, requests=5, tokens=9_500)
    assert led.deprioritized("cloudflare")


def test_mistral_per_minute_window(led, clock):
    # ministral-3b: 750 req/min → 700 recorded within the sliding minute
    for _ in range(700):
        led.record("mistral", "ministral-3b-2512")
    assert led.deprioritized("mistral", "ministral-3b-2512")
    clock["now"] += 61          # window slides → resets
    assert not led.deprioritized("mistral", "ministral-3b-2512")


def test_unknown_limits_never_deprioritized(led):
    for _ in range(50):
        led.record("opencode_zen", "big-pickle", tokens=100_000)
    assert led.saturation("opencode_zen", "big-pickle") == 0.0
    assert not led.deprioritized("opencode_zen", "big-pickle")


def test_per_model_isolation(led):
    _fill(led, "groq", "openai/gpt-oss-20b", requests=14_000)
    assert led.deprioritized("groq", "openai/gpt-oss-20b")
    assert not led.deprioritized("groq", "openai/gpt-oss-120b")


# ── per-minute vs daily time-horizon separation (regression) ─────────────────

def test_rpm_burst_does_not_deprioritize_when_daily_budget_unused(led, clock):
    """Cerebras: tokens_per_day=1M, requests_per_min=5, tokens_per_min=30K.
    A burst of 5 requests (hitting 100% RPM) with only ~30K/1M daily tokens
    used must NOT deprioritize — 97% of the daily budget is still unused."""
    # 5 requests using 6K tokens each = 30K tokens (3% of 1M/day)
    for _ in range(5):
        led.record("cerebras", "gpt-oss-120b", tokens=6_000)
    # Per-minute: 5/5 RPM = 100%, 30K/30K TPM = 100%
    # Daily:       5/2400 req = 0.2%, 30K/1M tok = 3%
    # Bug: old max(fractions) returned 1.0 → deprioritized
    # Fix: daily limits govern when they exist → saturation ≈ 3%
    assert not led.deprioritized("cerebras", "gpt-oss-120b")
    assert led.saturation("cerebras", "gpt-oss-120b") < 0.10  # well under 90%


def test_per_minute_only_provider_still_deprioritizes(led, clock):
    """Mistral has only per-minute limits — a burst should still deprioritize."""
    # ministral-3b: 750 req/min, no daily limits
    for _ in range(700):
        led.record("mistral", "ministral-3b-2512")
    assert led.deprioritized("mistral", "ministral-3b-2512")  # 93.3% of RPM


def test_daily_limit_still_deprioritizes_regardless_of_rpm(led):
    """Daily saturation should deprioritize even if per-minute is low."""
    # Groq: requests_per_day=14400, tokens_per_min=6000
    _fill(led, "groq", "openai/gpt-oss-20b", requests=13_500, tokens=100)
    # Daily: 13500/14400 = 93.75% → deprioritized
    assert led.deprioritized("groq", "openai/gpt-oss-20b")


# ── reorder semantics ────────────────────────────────────────────────────────

def test_reorder_stable_partition_ollama_pinned(led):
    _fill(led, "groq", "openai/gpt-oss-20b", requests=14_000)
    pairs = [
        (FakeProv("groq"), "openai/gpt-oss-20b"),      # saturated
        (FakeProv("mistral"), "ministral-3b-2512"),      # fresh
        (FakeProv("cerebras"), "gpt-oss-120b"),          # fresh
        (FakeProv("ollama"), "vector-focus"),            # local terminal
    ]
    out = led.reorder(pairs)
    slugs = [p[0].slug for p in out]
    assert slugs == ["mistral", "cerebras", "groq", "ollama"]
    assert len(out) == 4                                  # nothing dropped


def test_reorder_never_drops_all_saturated(led):
    _fill(led, "groq", _PROVIDER_KEY, requests=10**9)
    _fill(led, "groq", "openai/gpt-oss-20b", requests=10**9)
    pairs = [(FakeProv("groq"), "openai/gpt-oss-20b"),
             (FakeProv("ollama"), "vector-focus")]
    out = led.reorder(pairs)
    assert len(out) == 2
    assert out[-1][0].slug == "ollama"


def test_reorder_empty_and_local_only_noop(led):
    assert led.reorder([]) == []
    pairs = [(FakeProv("ollama"), "vector-focus")]
    assert [p[0].slug for p in led.reorder(pairs)] == ["ollama"]


# ── day rollover + persistence ───────────────────────────────────────────────

def test_utc_midnight_reset(led):
    yesterday = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    led._data[yesterday] = {"groq": {"openai/gpt-oss-20b":
                                     {"requests": 14_000, "tokens": 0}}}
    # Yesterday's counters don't count today.
    assert led.saturation("groq", "openai/gpt-oss-20b") == 0.0


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "q.json"
    a = QuotaLedger(path=p, clock=lambda: 1000.0)
    a.record("groq", "openai/gpt-oss-20b", tokens=500)
    a._last_save = 0.0
    with a._lock:
        a._save()
    b = QuotaLedger(path=p)
    reqs, toks = b._counters("groq", "openai/gpt-oss-20b")
    assert (reqs, toks) == (1, 500)


def test_corrupt_file_tolerated(tmp_path):
    p = tmp_path / "q.json"
    p.write_text("{not json", encoding="utf-8")
    led = QuotaLedger(path=p)
    assert led.saturation("groq") == 0.0    # fresh start, no crash


def test_pytest_default_is_memory_only():
    led = QuotaLedger()                      # no injected path, under pytest
    assert led._path is None
    led.record("groq", "openai/gpt-oss-20b")   # must not write anywhere


if __name__ == "__main__":
    # real test, no mocks
    import tempfile
    led = QuotaLedger(path=Path(tempfile.mkdtemp()) / "q.json")
    led.record("groq", "openai/gpt-oss-20b", tokens=10)
    print("✅ test_quota_ledger OK" if led.snapshot() else "❌ FAILED")
