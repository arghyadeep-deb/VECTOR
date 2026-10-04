"""Smoke regression for vectorcode/src/bench/{energy,latency,throughput}.py:

all three used stdlib logging.getLogger(__name__) with %-style placeholders
instead of loguru (CLAUDE.md rule 6). Converted to `from loguru import
logger` + `{}`-style placeholders. This module is LIVE (real callers:
core/loop/cron_jobs.py, vectorcode/src/vector_cli/bench_cmd.py), so this
test runs each benchmark end-to-end against a fake engine whose generate()
sometimes raises, to exercise the exact logger.debug(...) call sites that
changed and confirm they don't crash under the new loguru signature.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_core.types import Role
from vectorcode.src.bench.energy import EnergyBenchmark
from vectorcode.src.bench.latency import LatencyBenchmark
from vectorcode.src.bench.throughput import ThroughputBenchmark


class _FlakyEngine:
    engine_id = "fake"
    is_cloud = False

    def __init__(self, fail_every=3):
        self._fail_every = fail_every
        self._calls = 0

    def generate(self, messages, *, model, temperature=0.7, max_tokens=1024, **kwargs):
        self._calls += 1
        if self._calls % self._fail_every == 0:
            raise RuntimeError("simulated backend failure")
        return {"content": "hello world", "usage": {"completion_tokens": 5}}

    async def stream(self, messages, *, model, temperature=0.7, max_tokens=1024, **kwargs):
        yield "hello"


def test_latency_benchmark_runs_with_some_failures():
    result = LatencyBenchmark().run(_FlakyEngine(), "fake-model", num_samples=6, warmup_samples=2)
    assert result.errors >= 1
    assert result.samples == 6


def test_throughput_benchmark_runs_with_some_failures():
    result = ThroughputBenchmark().run(_FlakyEngine(), "fake-model", num_samples=6, warmup_samples=2)
    assert result.errors >= 1
    assert "total_tokens" in result.metrics


def test_energy_benchmark_runs_without_energy_monitor():
    result = EnergyBenchmark().run(_FlakyEngine(), "fake-model", num_samples=6, warmup_samples=2)
    assert result.errors >= 1
    assert result.steady_state_samples == 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
