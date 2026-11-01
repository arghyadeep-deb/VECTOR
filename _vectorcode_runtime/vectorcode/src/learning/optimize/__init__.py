# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Optimization framework for VectorCode configuration tuning."""

from vectorcode.src.learning.optimize.config import (
    load_benchmark_specs,
    load_objectives,
    load_optimize_config,
)
from vectorcode.src.learning.optimize.llm_optimizer import LLMOptimizer
from vectorcode.src.learning.optimize.optimizer import (
    OptimizationEngine,
    compute_pareto_frontier,
)
from vectorcode.src.learning.optimize.search_space import (
    DEFAULT_SEARCH_SPACE,
    build_search_space,
)
from vectorcode.src.learning.optimize.store import OptimizationStore
from vectorcode.src.learning.optimize.trial_runner import (
    BenchmarkSpec,
    MultiBenchTrialRunner,
    TrialRunner,
)
from vectorcode.src.learning.optimize.types import (
    ALL_OBJECTIVES,
    DEFAULT_OBJECTIVES,
    BenchmarkScore,
    ObjectiveSpec,
    OptimizationRun,
    SampleScore,
    SearchDimension,
    SearchSpace,
    TrialConfig,
    TrialFeedback,
    TrialResult,
)

__all__ = [
    "ALL_OBJECTIVES",
    "BenchmarkScore",
    "BenchmarkSpec",
    "DEFAULT_OBJECTIVES",
    "DEFAULT_SEARCH_SPACE",
    "LLMOptimizer",
    "MultiBenchTrialRunner",
    "ObjectiveSpec",
    "OptimizationEngine",
    "OptimizationRun",
    "OptimizationStore",
    "SampleScore",
    "SearchDimension",
    "SearchSpace",
    "TrialConfig",
    "TrialFeedback",
    "TrialResult",
    "TrialRunner",
    "build_search_space",
    "compute_pareto_frontier",
    "load_benchmark_specs",
    "load_objectives",
    "load_optimize_config",
]
