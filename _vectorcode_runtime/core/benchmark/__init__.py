"""VECTOR Cognitive Benchmark — measures actual cognitive capabilities.

Not unit tests. Not synthetic benchmarks. Measures whether VECTOR is becoming
more capable over time across 14 cognitive dimensions.

Run: python scripts/cognitive_benchmark.py
"""
from core.benchmark.benchmark_task import BenchmarkTask, TaskResult
from core.benchmark.isolation import IsolatedState
from core.benchmark.benchmark_runner import BenchmarkRunner
from core.benchmark.report import BenchmarkReport

__all__ = [
    "BenchmarkTask",
    "TaskResult",
    "IsolatedState",
    "BenchmarkRunner",
    "BenchmarkReport",
]
