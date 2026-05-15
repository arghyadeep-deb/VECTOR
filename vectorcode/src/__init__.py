__version__ = "1.0.0"

try:
    from .claims import ClaimService, WorkStealingService, LoadBalancer, mcp_claim_task, mcp_release_task, mcp_steal_task
except ImportError:
    pass

try:
    from .guidance import create_guidance_system, ThreatDetector, CoherenceScheduler, AuthorityGate, ContinueGate
except ImportError:
    pass

try:
    from .neural_training import VECTORTrainer, A2C, DQN, CuriosityModule, DecisionTransformer
except ImportError:
    pass

