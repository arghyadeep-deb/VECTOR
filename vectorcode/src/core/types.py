"""Core types shim — re-exports from vc_core.types."""
from vectorcode.src.vc_core.types import (
    Message, Role, RoutingContext, ModelSpec, Conversation,
    Quantization, FP4, FP8, INT4, INT8, GGUF, GGUF_Q4, GGUF_Q8, NONE,
    SYSTEM, ASSISTANT, GENERATE, RESPOND, RETRIEVE, ROUTE,
)
# Extra shim types not in vc_core
from typing import Any, Dict, List, Optional
class TelemetryRecord:
    """Telemetry record type stub."""
    pass

class ToolResult:
    """Tool result type stub (use vectorcode.src.tools._stubs.ToolResult for full impl)."""
    pass
