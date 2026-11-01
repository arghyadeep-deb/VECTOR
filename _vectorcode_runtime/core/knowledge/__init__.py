"""
VECTOR Knowledge Layer — codebase + wiki understanding utilities.

Absorbed from Understand-Anything-main (MIT) — Python algorithm reimplementation.

Provides:
  DomainExtractor   — multi-language entry point + signature scanner
  WikiParser        — Karpathy-format markdown wiki → knowledge graph
  WikiMerger        — merges scan-manifest with LLM analysis batches
  GraphMerger       — normalizes + merges LLM batch graph outputs
  SubgraphMerger    — merges multiple knowledge-graph JSON files
"""
from core.knowledge.domain_extractor import DomainExtractor, DomainContext
from core.knowledge.wiki_parser import WikiParser
from core.knowledge.wiki_merger import WikiMerger
from core.knowledge.graph_merger import GraphMerger, SubgraphMerger

__all__ = [
    "DomainExtractor", "DomainContext",
    "WikiParser",
    "WikiMerger",
    "GraphMerger", "SubgraphMerger",
]
