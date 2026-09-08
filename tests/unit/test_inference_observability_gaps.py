"""Verifies the completeness-pass gap closures in
core/metering/inference_observability.py and their call-site instrumentation
in core/inference/provider_client.py and core/inference/ollama_safe.py.

Gaps addressed (see VECTOR_TECHNICAL_KNOWLEDGE/50_INFERENCE_OBSERVABILITY.md
section 6 for the full before/after):
  1. Retry count — ProviderClient._call_with_retry() now stamps
     result._retry_attempts (the loop's own `attempt` counter at the
     success point) without changing what is returned or retried.
  2. Tokens/model — InferenceObservability.model_summary() (new).
  3. Autonomous token consumption — InferenceObservability
     .autonomy_token_summary() (new).
  4. User-triggered token consumption — same method, "user" key.
  5. Streaming token exactness — ollama_safe.chat_stream() now reads
     prompt_eval_count/eval_count off the final (done=True) chunk instead
     of always falling back to a char-count estimate; every recorder now
     tags metadata.token_exact so reports can distinguish provider-exact
     from estimated counts (InferenceObservability
     .token_exactness_summary()).
  6. Raw fallback count + failure rate + retry rate — added to
     daily_summary() (fallback_calls/fallback_rate_pct/error_calls/
     failure_rate_pct/retry_calls/retry_rate_pct/retry_coverage_calls).

Real SQLite (temp file), no mocking of InferenceObservability itself —
per .claude/rules/testing.md, VECTOR internals are exercised for real.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.metering.inference_observability import InferenceObservability


@pytest.fixture
def obs():
    """Real InferenceObservability backed by a temp SQLite file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    instance = InferenceObservability(db_path=db_path)
    yield instance
    if instance._conn is not None:
        instance._conn.close()
    db_path.unlink(missing_ok=True)


# ── Gap 2/3/4: model_summary() and autonomy_token_summary() ────────────────


class TestModelSummary:
    def test_tokens_grouped_by_model(self, obs):
        obs.record(caller_id="a", provider="groq", model="llama-3.3-70b",
                   input_tokens=100, output_tokens=50)
        obs.record(caller_id="b", provider="cerebras", model="llama-3.3-70b",
                   input_tokens=200, output_tokens=100)
        obs.record(caller_id="c", provider="gemini", model="gemini-2.5-flash",
                   input_tokens=500, output_tokens=250)
        obs.flush()

        rows = obs.model_summary()
        by_model = {r["model"]: r for r in rows}

        assert by_model["llama-3.3-70b"]["calls"] == 2
        assert by_model["llama-3.3-70b"]["input_tokens"] == 300
        assert by_model["llama-3.3-70b"]["output_tokens"] == 150
        assert by_model["llama-3.3-70b"]["tokens"] == 450

        assert by_model["gemini-2.5-flash"]["calls"] == 1
        assert by_model["gemini-2.5-flash"]["tokens"] == 750

    def test_empty_model_excluded(self, obs):
        obs.record(caller_id="a", provider="ollama", model="",
                   input_tokens=10, output_tokens=5)
        obs.flush()
        rows = obs.model_summary()
        assert all(r["model"] != "" for r in rows)

    def test_no_data_returns_empty_list(self, obs):
        assert obs.model_summary() == []


class TestAutonomyTokenSummary:
    def test_splits_autonomous_and_user_tokens(self, obs):
        obs.record(caller_id="vc_llm_coding", provider="groq", model="m",
                   input_tokens=1000, output_tokens=500, is_autonomous=True)
        obs.record(caller_id="web_ui_chat", provider="ollama", model="m2",
                   input_tokens=100, output_tokens=50, is_autonomous=False)
        obs.record(caller_id="vc_llm_research", provider="gemini", model="m3",
                   input_tokens=2000, output_tokens=1000, is_autonomous=True)
        obs.flush()

        result = obs.autonomy_token_summary()
        assert result["autonomous"]["calls"] == 2
        assert result["autonomous"]["tokens"] == 4500  # 1500 + 3000
        assert result["user"]["calls"] == 1
        assert result["user"]["tokens"] == 150

    def test_no_data_returns_zeroed_structure(self, obs):
        result = obs.autonomy_token_summary()
        assert result["autonomous"] == {"calls": 0, "input_tokens": 0, "output_tokens": 0, "tokens": 0}
        assert result["user"] == {"calls": 0, "input_tokens": 0, "output_tokens": 0, "tokens": 0}


# ── Gap 6: fallback count, failure rate, retry rate in daily_summary() ─────


class TestDailySummaryNewFields:
    def test_fallback_calls_counts_providers_tried_over_one(self, obs):
        obs.record(caller_id="a", provider="groq", model="m", providers_tried=1)
        obs.record(caller_id="b", provider="gemini", model="m", providers_tried=2)
        obs.record(caller_id="c", provider="ollama", model="m", providers_tried=3)
        obs.flush()

        summary = obs.daily_summary()
        assert summary["fallback_calls"] == 2  # providers_tried=2 and 3
        assert summary["fallback_rate_pct"] == pytest.approx(66.7, abs=0.1)

    def test_failure_rate_computed_from_error_calls(self, obs):
        obs.record(caller_id="a", provider="groq", model="m", status="ok")
        obs.record(caller_id="b", provider="groq", model="m", status="ok")
        obs.record(caller_id="c", provider="groq", model="m", status="error")
        obs.flush()

        summary = obs.daily_summary()
        assert summary["error_calls"] == 1
        assert summary["failure_rate_pct"] == pytest.approx(33.3, abs=0.1)

    def test_retry_rate_only_counts_rows_with_retry_metadata(self, obs):
        # Two rows carry retry_attempts (simulating ProviderClient's stamp);
        # one does not (simulating an ollama_safe direct call, which never
        # populates this field).
        obs.record(caller_id="a", provider="groq", model="m", status="ok",
                   metadata={"retry_attempts": 0})
        obs.record(caller_id="b", provider="gemini", model="m", status="ok",
                   metadata={"retry_attempts": 2})
        obs.record(caller_id="c", provider="ollama", model="m", status="ok")
        obs.flush()

        summary = obs.daily_summary()
        # coverage = 2 (only rows a and b carry retry_attempts)
        assert summary["retry_coverage_calls"] == 2
        # retried = 1 (row b, attempts=2 > 0)
        assert summary["retry_calls"] == 1
        assert summary["retry_rate_pct"] == pytest.approx(50.0, abs=0.1)

    def test_retry_rate_zero_coverage_does_not_divide_by_zero(self, obs):
        obs.record(caller_id="a", provider="ollama", model="m", status="ok")
        obs.flush()
        summary = obs.daily_summary()
        assert summary["retry_coverage_calls"] == 0
        assert summary["retry_rate_pct"] == 0

    def test_empty_summary_has_all_new_keys(self, obs):
        summary = obs.daily_summary()  # no data recorded
        for key in ("fallback_calls", "fallback_rate_pct", "failure_rate_pct",
                   "retry_calls", "retry_rate_pct", "retry_coverage_calls"):
            assert key in summary, f"missing key: {key}"


# ── Gap 5: token_exactness_summary() ────────────────────────────────────────


class TestTokenExactnessSummary:
    def test_distinguishes_exact_from_estimated(self, obs):
        obs.record(caller_id="a", provider="groq", model="m",
                   metadata={"token_exact": True})
        obs.record(caller_id="b", provider="gemini", model="m",
                   metadata={"token_exact": True})
        obs.record(caller_id="c", provider="openrouter", model="m",
                   metadata={"token_exact": False})
        obs.record(caller_id="d", provider="ollama", model="m")  # no flag at all
        obs.flush()

        result = obs.token_exactness_summary()
        assert result["exact_calls"] == 2
        assert result["estimated_calls"] == 1
        assert result["unknown_calls"] == 1
        assert result["exact_pct"] == pytest.approx(50.0, abs=0.1)

    def test_no_data_returns_zeroed_structure(self, obs):
        result = obs.token_exactness_summary()
        assert result["exact_calls"] == 0
        assert result["estimated_calls"] == 0
        assert result["exact_pct"] == 0


# ── Report generation includes new sections ─────────────────────────────────


class TestDailyReportIncludesNewSections:
    def test_report_mentions_fallback_and_retry(self, obs):
        obs.record(caller_id="a", provider="groq", model="llama-3.3-70b",
                   input_tokens=100, output_tokens=50, providers_tried=2,
                   metadata={"retry_attempts": 1, "token_exact": True})
        obs.flush()
        report = obs.generate_daily_report()
        assert "Fallback calls:" in report
        assert "Retry rate:" in report
        assert "failure rate" in report
        assert "Model Breakdown" in report
        assert "llama-3.3-70b" in report


# ── Provider-client retry stamping (real _call_with_retry behavior check) ──


class TestProviderClientRetryStamp:
    """Confirms _call_with_retry() stamps attempt count without altering
    the returned CompletionResult's content/model/provider/tokens — i.e.
    the stamp is additive metadata, not a behavior change."""

    def test_completion_result_accepts_retry_attempts_attribute(self):
        from core.inference.provider_client import CompletionResult

        r = CompletionResult(content="hello", model="m", provider="p",
                             input_tokens=10, output_tokens=5)
        # Same dynamic-attribute pattern already used for _tool_calls.
        r._retry_attempts = 0
        assert r.content == "hello"
        assert r.model == "m"
        assert r.provider == "p"
        assert r.input_tokens == 10
        assert r.output_tokens == 5
        assert r._retry_attempts == 0

    @pytest.mark.asyncio
    async def test_call_with_retry_stamps_zero_on_first_try_success(self, monkeypatch):
        """A provider that succeeds on attempt 0 (no retry needed) must be
        stamped _retry_attempts=0 — confirms the counter reflects real
        attempt count, not a placeholder."""
        from core.inference.provider_client import ProviderClient, CompletionResult

        client = ProviderClient()

        class FakeProv:
            slug = "fake"
            api_key_env = "FAKE_KEY"

        async def fake_call(prov, model, messages, temperature, max_tokens, tools, api_key=None):
            return CompletionResult(content="ok", model=model, provider=prov.slug)

        monkeypatch.setattr(client, "_call", fake_call)

        result = await client._call_with_retry(
            FakeProv(), "test-model", [{"role": "user", "content": "hi"}],
            0.7, 100, None,
        )
        assert result.content == "ok"
        assert getattr(result, "_retry_attempts", None) == 0

    @pytest.mark.asyncio
    async def test_call_with_retry_stamps_nonzero_after_retryable_failure(self, monkeypatch):
        """A provider that fails once (non-rate-limit, retryable) then
        succeeds must be stamped _retry_attempts=1 — confirms real retries
        increment the counter, and that this counting does not change
        retry behavior (still succeeds, still returns the same content)."""
        from core.inference.provider_client import ProviderClient, CompletionResult

        client = ProviderClient()

        class FakeProv:
            slug = "fake"
            api_key_env = "FAKE_KEY"

        call_count = {"n": 0}

        async def flaky_call(prov, model, messages, temperature, max_tokens, tools, api_key=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient 500 error")
            return CompletionResult(content="ok-after-retry", model=model, provider=prov.slug)

        monkeypatch.setattr(client, "_call", flaky_call)

        # Patch asyncio.sleep to avoid the real backoff wait in this test.
        async def _no_sleep(*_a, **_kw):
            return None
        monkeypatch.setattr("asyncio.sleep", _no_sleep)

        result = await client._call_with_retry(
            FakeProv(), "test-model", [{"role": "user", "content": "hi"}],
            0.7, 100, None,
        )
        assert result.content == "ok-after-retry"
        assert getattr(result, "_retry_attempts", None) == 1
        assert call_count["n"] == 2


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
