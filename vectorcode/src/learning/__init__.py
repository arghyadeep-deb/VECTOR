# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/learning/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Learning primitive -- router policies, reward functions, learning."""

from __future__ import annotations

from vectorcode.src.learning._stubs import (
    QueryAnalyzer,
    RewardFunction,
    RouterPolicy,
    RoutingContext,
)
from vectorcode.src.learning.agents.agent_evolver import AgentConfigEvolver
from vectorcode.src.learning.learning_orchestrator import LearningOrchestrator
from vectorcode.src.learning.optimize.llm_optimizer import LLMOptimizer
from vectorcode.src.learning.optimize.optimizer import OptimizationEngine
from vectorcode.src.learning.optimize.store import OptimizationStore
from vectorcode.src.learning.routing.complexity import (
    ComplexityQueryAnalyzer,
    score_complexity,
)
from vectorcode.src.learning.routing.heuristic_reward import HeuristicRewardFunction
from vectorcode.src.learning.routing.router import (
    HeuristicRouter,
    build_routing_context,
)
from vectorcode.src.learning.training.data import TrainingDataMiner
from vectorcode.src.learning.training.lora import HAS_TORCH, LoRATrainer, LoRATrainingConfig


def ensure_registered() -> None:
    """Ensure all learning policies are registered in RouterPolicyRegistry."""
    from vector.learning.routing.heuristic_policy import (
        ensure_registered as _reg_heuristic,
    )

    _reg_heuristic()

    from vector.learning.routing.learned_router import (
        ensure_registered as _reg_learned,
    )

    _reg_learned()

    # Intelligence training (optional deps)
    try:
        import vector.learning.intelligence  # noqa: F401
    except ImportError:
        pass

    # Orchestrator-specific training (optional deps)
    try:
        import vector.learning.intelligence.orchestrator  # noqa: F401
    except ImportError:
        pass

    # Agent optimizers (optional deps)
    try:
        import vector.learning.agents.dspy_optimizer  # noqa: F401
    except ImportError:
        pass
    try:
        import vector.learning.agents.gepa_optimizer  # noqa: F401
    except ImportError:
        pass


__all__ = [
    "AgentConfigEvolver",
    "ComplexityQueryAnalyzer",
    "HAS_TORCH",
    "HeuristicRewardFunction",
    "HeuristicRouter",
    "LLMOptimizer",
    "LearningOrchestrator",
    "LoRATrainer",
    "LoRATrainingConfig",
    "OptimizationEngine",
    "OptimizationStore",
    "QueryAnalyzer",
    "RewardFunction",
    "RouterPolicy",
    "RoutingContext",
    "TrainingDataMiner",
    "build_routing_context",
    "ensure_registered",
    "score_complexity",
]
