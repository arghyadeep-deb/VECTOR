"""VectorCode context management — VECTOR.md, 5-stage compaction, session memory, references."""
from vectorcode.src.context.references import (
    ContextReference,
    ContextReferenceResult,
    expand_context_references,
    parse_context_references,
)

__all__ = [
    "ContextReference",
    "ContextReferenceResult",
    "expand_context_references",
    "parse_context_references",
]
