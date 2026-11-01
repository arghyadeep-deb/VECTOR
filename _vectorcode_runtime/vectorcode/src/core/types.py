"""Core types shim — re-exports from vc_core.types."""
from vectorcode.src.vc_core.types import (
    Message, Role, RoutingContext, ModelSpec, Conversation,
    Quantization, TelemetryRecord, ToolResult, ToolCall, Trace, TraceStep,
    StepType,
)

# Quantization enum members as module-level aliases (safe hasattr guards)
FP4     = getattr(Quantization, "FP4",     None)
FP8     = getattr(Quantization, "FP8",     None)
INT4    = getattr(Quantization, "INT4",    None)
INT8    = getattr(Quantization, "INT8",    None)
GGUF    = getattr(Quantization, "GGUF",    None)
GGUF_Q4 = getattr(Quantization, "GGUF_Q4", None)
GGUF_Q8 = getattr(Quantization, "GGUF_Q8", None)
NONE    = getattr(Quantization, "NONE",    None)

SYSTEM    = getattr(Role,      "SYSTEM",    "system")
ASSISTANT = getattr(Role,      "ASSISTANT", "assistant")
GENERATE  = getattr(StepType,  "GENERATE",  "generate")
RESPOND   = getattr(StepType,  "RESPOND",   "respond")
RETRIEVE  = getattr(StepType,  "RETRIEVE",  "retrieve")
ROUTE     = getattr(StepType,  "ROUTE",     "route")
