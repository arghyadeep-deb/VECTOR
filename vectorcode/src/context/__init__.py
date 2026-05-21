"""VectorCode context management — VECTOR.md, 5-stage compaction, session memory, references."""

try:
    from vectorcode.context.references import (
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
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
