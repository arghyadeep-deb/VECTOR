# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Top-level system composition: VectorSystem, SystemBuilder, and helpers."""

from vectorcode.src.vc_system.builder import SystemBuilder
from vectorcode.src.vc_system.bundles import (
    AgentRuntime,
    Observability,
    Scheduling,
    SecurityContext,
)
from vectorcode.src.vc_system.core import VectorSystem
from vectorcode.src.vc_system.orchestrator import QueryOrchestrator
from vectorcode.src.vc_system.protocols import OrchestratorDeps

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
