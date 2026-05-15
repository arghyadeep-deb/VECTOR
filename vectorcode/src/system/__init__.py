# VECTOR-INGESTED MODULE (absorbed from open-jarvis/OpenJarvis, Apache 2.0)
"""Top-level system composition: VectorSystem, SystemBuilder, and helpers."""

from vectorcode.src.system.builder import SystemBuilder
from vectorcode.src.system.bundles import (
    AgentRuntime,
    Observability,
    Scheduling,
    SecurityContext,
)
from vectorcode.src.system.core import VectorSystem
from vectorcode.src.system.orchestrator import QueryOrchestrator
from vectorcode.src.system.protocols import OrchestratorDeps

__all__ = [
    "AgentRuntime",
    "VectorSystem",
    "Observability",
    "OrchestratorDeps",
    "QueryOrchestrator",
    "Scheduling",
    "SecurityContext",
    "SystemBuilder",
]
