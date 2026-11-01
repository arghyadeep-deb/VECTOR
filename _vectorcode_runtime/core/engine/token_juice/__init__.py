"""VECTOR TokenJuice — aggressive token compression targeting 80% reduction."""
from core.engine.token_juice.compressor import TokenJuice, reduce_messages, reduce_text
__all__ = ["TokenJuice", "reduce_messages", "reduce_text"]
