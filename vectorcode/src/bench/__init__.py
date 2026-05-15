# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/bench/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Benchmarking framework for VectorCode inference engines."""

from __future__ import annotations

from vectorcode.src.bench._stubs import BaseBenchmark, BenchmarkResult, BenchmarkSuite
from vectorcode.src.oj_core.registry import BenchmarkRegistry


def ensure_registered() -> None:
    """Ensure all benchmark implementations are registered."""
    from vector.bench.energy import ensure_registered as _reg_energy
    from vector.bench.latency import ensure_registered as _reg_latency
    from vector.bench.throughput import ensure_registered as _reg_throughput

    _reg_latency()
    _reg_throughput()
    _reg_energy()


# Trigger registration on import
ensure_registered()

__all__ = [
    "BaseBenchmark",
    "BenchmarkRegistry",
    "BenchmarkResult",
    "BenchmarkSuite",
    "ensure_registered",
]
