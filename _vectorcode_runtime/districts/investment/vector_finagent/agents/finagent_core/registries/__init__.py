"""
Registries - Central registries for all Agno components

Provides lazy loading and unified access to:
- Tools (100+ available)
- Models (40+ providers)
- VectorDBs (20+ options)
- Embedders (15+ options)
"""

from .tools_registry import ToolsRegistry
from .models_registry import ModelsRegistry
from .vectordb_registry import VectorDBRegistry
from .embedder_registry import EmbedderRegistry

__all__ = [
    "ToolsRegistry",
    "ModelsRegistry",
    "VectorDBRegistry",
    "EmbedderRegistry"
]
