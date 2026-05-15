# VECTOR-INGESTED MODULE (absorbed from open-jarvis/OpenJarvis, Apache 2.0)
"""Bundle dataclasses that group cohesive subsystems of VectorSystem."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from vectorcode.src.vc_agents._stubs import BaseAgent
    from vectorcode.src.vc_agents.executor import AgentExecutor
    from vectorcode.src.vc_agents.manager import AgentManager
    from vectorcode.src.vc_agents.scheduler import AgentScheduler
    from vectorcode.src.scheduler.scheduler import TaskScheduler
    from vectorcode.src.scheduler.store import SchedulerStore
    from vectorcode.src.vc_security.audit import AuditLogger
    from vectorcode.src.vc_security.boundary import BoundaryGuard
    from vectorcode.src.vc_security.capabilities import CapabilityPolicy
    from vectorcode.src.telemetry.gpu_monitor import GpuMonitor
    from vectorcode.src.telemetry.store import TelemetryStore
    from vectorcode.src.vc_traces.collector import TraceCollector
    from vectorcode.src.vc_traces.store import TraceStore


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
