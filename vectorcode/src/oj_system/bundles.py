# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/system/bundles.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Bundle dataclasses that group cohesive subsystems of JarvisSystem."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from vector.agents._stubs import BaseAgent
    from vector.agents.executor import AgentExecutor
    from vector.agents.manager import AgentManager
    from vector.agents.scheduler import AgentScheduler
    from vector.scheduler.scheduler import TaskScheduler
    from vector.scheduler.store import SchedulerStore
    from vector.security.audit import AuditLogger
    from vector.security.boundary import BoundaryGuard
    from vector.security.capabilities import CapabilityPolicy
    from vector.telemetry.gpu_monitor import GpuMonitor
    from vector.telemetry.store import TelemetryStore
    from vector.traces.collector import TraceCollector
    from vector.traces.store import TraceStore


@dataclass
class SecurityContext:
    """Security policy, audit, and boundary enforcement."""

    capability_policy: Optional[CapabilityPolicy] = None
    audit_logger: Optional[AuditLogger] = None
    boundary_guard: Optional[BoundaryGuard] = None


@dataclass
class Observability:
    """Telemetry, traces, and hardware monitoring."""

    telemetry_store: Optional[TelemetryStore] = None
    trace_store: Optional[TraceStore] = None
    trace_collector: Optional[TraceCollector] = None
    gpu_monitor: Optional[GpuMonitor] = None


@dataclass
class AgentRuntime:
    """Active agent and agent lifecycle managers."""

    agent: Optional[BaseAgent] = None
    agent_name: str = ""
    manager: Optional[AgentManager] = None
    scheduler: Optional[AgentScheduler] = None
    executor: Optional[AgentExecutor] = None


@dataclass
class Scheduling:
    """Task scheduler and its persistent store."""

    store: Optional[SchedulerStore] = None
    runner: Optional[TaskScheduler] = None
