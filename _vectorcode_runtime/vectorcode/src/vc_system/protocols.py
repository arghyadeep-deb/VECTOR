# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Structural protocols for substituting fakes in place of VectorSystem."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Protocol

if TYPE_CHECKING:
    from vectorcode.src.vc_core.config import VectorConfig
    from vectorcode.src.vc_core.events import EventBus
    from vectorcode.src.vc_engine._abc import InferenceEngine
    from vectorcode.src.vc_security.capabilities import CapabilityPolicy
    from vectorcode.src.vc_sessions.session import SessionStore
    from vectorcode.src.vc_tools._abc import BaseTool
    from vectorcode.src.vc_tools.storage._abc import MemoryBackend
    from vectorcode.src.vc_traces.collector import TraceCollector
    from vectorcode.src.vc_traces.store import TraceStore

class OrchestratorDeps(Protocol):
    """Minimum surface of VectorSystem that QueryOrchestrator depends on.

    Tests can satisfy this with a lightweight class — no need to construct
    the full VectorSystem dataclass or materialize every subsystem.
    """

    config: VectorConfig
    bus: EventBus
    engine: InferenceEngine
    engine_key: str
    model: str
    agent_name: str
    tools: List[BaseTool]
    memory_backend: Optional[MemoryBackend]
    capability_policy: Optional[CapabilityPolicy]
    session_store: Optional[SessionStore]
    trace_store: Optional[TraceStore]
    trace_collector: Optional[TraceCollector]  # written by _run_agent

    # Optional attribute (getattr with default) — declared for type clarity.
    _skill_few_shot_examples: Any
