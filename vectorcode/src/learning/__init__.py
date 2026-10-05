# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Learning primitive -- router policies, reward functions, learning."""

from __future__ import annotations
from loguru import logger

from vectorcode.src.learning._abc import (
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
    from vectorcode.src.learning.routing.heuristic_policy import (
        ensure_registered as _reg_heuristic,
    )

    _reg_heuristic()

    from vectorcode.src.learning.routing.learned_router import (
        ensure_registered as _reg_learned,
    )

    _reg_learned()

    # Intelligence training (optional deps)
    try:
        import vectorcode.src.learning.intelligence  # noqa: F401
    except ImportError:
        logger.opt(exception=True).debug("[VECTOR] suppressed exception")

    # Orchestrator-specific training (optional deps)
    try:
        import vectorcode.src.learning.intelligence.orchestrator  # noqa: F401
    except ImportError:
        logger.opt(exception=True).debug("[VECTOR] suppressed exception")

    # Agent optimizers (optional deps)
    try:
        import vectorcode.src.learning.agents.dspy_optimizer  # noqa: F401
    except ImportError:
        logger.opt(exception=True).debug("[VECTOR] suppressed exception")
    try:
        import vectorcode.src.learning.agents.gepa_optimizer  # noqa: F401
    except ImportError:
        logger.opt(exception=True).debug("[VECTOR] suppressed exception")

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
