# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Core module — registries, types, configuration, and event bus."""

from __future__ import annotations

from vectorcode.src.vc_core.registry import (
    AgentRegistry,
    EngineRegistry,
    MemoryRegistry,
    ModelRegistry,
    ToolRegistry,
)
from vectorcode.src.vc_core.types import (
    Conversation,
    Message,
    ModelSpec,
    Quantization,
    Role,
    TelemetryRecord,
    ToolCall,
    ToolResult,
)

__all__ = [
    "AgentRegistry",
    "Conversation",
    "EngineRegistry",
    "MemoryRegistry",
    "Message",
    "ModelRegistry",
    "ModelSpec",
    "Quantization",
    "Role",
    "TelemetryRecord",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
]
