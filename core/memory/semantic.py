"""
V.E.C.T.O.R. SemanticMemory.
Concept embeddings and knowledge graph via Ollama + ChromaDB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
import uuid
from datetime import datetime

from core.config import CONFIG
from core.memory.episodic import EpisodicMemory


class SemanticMemory:
    """Stores conceptual knowledge with embeddings. Uses Ollama + ChromaDB."""

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._embed_model = CONFIG["models"]["embed"]
        self._episodic = EpisodicMemory()
        self._concepts: dict[str, dict] = {}
        logger.info("[VECTOR][semantic] SemanticMemory initialized")

    async def add_concept(self, concept: str, definition: str, tags: list[str] | None = None) -> dict:
        """Add a concept to the semantic store."""
        entry = {
            "id": str(uuid.uuid4()),
            "concept": concept,
            "definition": definition,
            "tags": tags or [],
            "created_at": datetime.utcnow().isoformat(),
            "access_count": 0,
        }
        self._concepts[concept] = entry
        logger.info(f"[VECTOR][semantic] Added concept: {concept}")
        return entry

    def get_concept(self, concept: str) -> dict | None:
        """Retrieve a concept."""
        if concept in self._concepts:
            self._concepts[concept]["access_count"] += 1
            return self._concepts[concept]
        return None

    def search_concepts(self, query: str, limit: int = 10) -> list[dict]:
        """Simple keyword search across concepts."""
        q = query.lower()
        results = [
            c for c in self._concepts.values()
            if q in c["concept"].lower() or q in c["definition"].lower()
        ]
        return sorted(results, key=lambda x: x["access_count"], reverse=True)[:limit]

    def link_concepts(self, concept_a: str, concept_b: str, relation: str) -> dict:
        """Create a relation between two concepts."""
        if concept_a not in self._concepts or concept_b not in self._concepts:
            return {"status": "error", "detail": "Concept not found"}
        link = {
            "from": concept_a,
            "to": concept_b,
            "relation": relation,
            "created_at": datetime.utcnow().isoformat(),
        }
        if "links" not in self._concepts[concept_a]:
            self._concepts[concept_a]["links"] = []
        self._concepts[concept_a]["links"].append(link)
        logger.info(f"[VECTOR][semantic] Linked {concept_a} --[{relation}]--> {concept_b}")
        return link

    def get_related(self, concept: str) -> list[dict]:
        """Get all concepts related to this one."""
        if concept not in self._concepts:
            return []
        return self._concepts[concept].get("links", [])


if __name__ == "__main__":
    sm = SemanticMemory()
    import asyncio
    async def test():
        await sm.add_concept("V.E.C.T.O.R.", "Virtual Entity for Cognitive Tasks and Operational Reasoning", ["AI", "agent"])
        print(sm.get_concept("V.E.C.T.O.R."))
    asyncio.run(test())