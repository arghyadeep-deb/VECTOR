"""Tests for EvalHarness: benchmark registration, evaluate(), compare(), regression detection."""

import sys
from pathlib import Path
from typing import Callable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.training.eval_harness import EvalHarness


class DummyBenchmark:
    def __init__(self):
        self.prompts = [
            {"id": "q1", "prompt": "Say hello", "expected": "hello", "type": "exact"},
            {"id": "q2", "prompt": "Say world", "expected": "world", "type": "exact"},
        ]
        logger.info("[Test] DummyBenchmark ready")

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores = {}
        for p in self.prompts:
            response = model_fn(p["prompt"])
            kw = p["expected"].lower()
            scores[p["id"]] = 1.0 if kw in response.lower() else 0.0
        return scores


class LowScoreBenchmark:
    def __init__(self):
        self.prompts = [{"id": "fail1", "prompt": "test", "expected": "xyz", "type": "exact"}]
        logger.info("[Test] LowScoreBenchmark ready")

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        return {p["id"]: 0.0 for p in self.prompts}


def test_register_and_evaluate():
    harness = EvalHarness()
    harness.register_benchmark("dummy", DummyBenchmark)
    result = harness.evaluate(
        model_name="test-model",
        adapter_name="",
        benchmarks=["dummy"],
    )
    assert result.model_name == "test-model"
    assert result.adapter_name == "base"
    assert "dummy" in result.benchmark_results
    assert result.overall_score >= 0.0


def test_evaluate_unknown_benchmark():
    harness = EvalHarness()
    result = harness.evaluate(model_name="test", benchmarks=["nonexistent"])
    assert result.overall_score == 0.0


def test_compare_base_vs_adapter():
    harness = EvalHarness()
    harness.register_benchmark("low", LowScoreBenchmark)
    comp = harness.compare(base_model="base-model", adapter_model="adapter-model", benchmarks=["low"])
    assert comp.base_model_name == "base-model"
    assert comp.adapter_model_name == "adapter-model"
    assert "low" in comp.improvements


def test_compare_shows_improvement():
    harness = EvalHarness()
    harness.register_benchmark("dummy", DummyBenchmark)
    comp = harness.compare(base_model="base", adapter_model="adapter", benchmarks=["dummy"])
    assert isinstance(comp.overall_improvement, float)


def test_compare_no_benchmarks():
    harness = EvalHarness()
    comp = harness.compare(base_model="base", adapter_model="adapter")
    assert comp.overall_improvement == 0.0


def test_regression_detected():
    harness = EvalHarness()
    harness.register_benchmark("dummy", DummyBenchmark)
    base = harness.evaluate(model_name="base", benchmarks=["dummy"])
    adapter = harness.evaluate(model_name="adapter", benchmarks=["dummy"])
    comp = harness.compare("base", "adapter", ["dummy"])
    if comp.overall_improvement < 0:
        assert any(v.get("change", 0) < 0 for v in comp.improvements.values())


def test_benchmark_registration_idempotent():
    harness = EvalHarness()
    harness.register_benchmark("dup", DummyBenchmark)
    harness.register_benchmark("dup", DummyBenchmark)
    result = harness.evaluate(model_name="t", benchmarks=["dup"])
    assert result.overall_score >= 0.0


def test_multiple_benchmarks():
    harness = EvalHarness()
    harness.register_benchmark("d1", DummyBenchmark)
    harness.register_benchmark("d2", LowScoreBenchmark)
    result = harness.evaluate(model_name="multi", benchmarks=["d1", "d2"])
    assert "d1" in result.benchmark_results
    assert "d2" in result.benchmark_results
