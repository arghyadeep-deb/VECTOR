"""
Module: agents/learning/concept_extractor.py
District: learning | Focus: Extract concepts from text, create concept maps, suggest prerequisites
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import os
import uuid, asyncio, json
from typing import Optional


class ConceptExtractor(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ConceptExtractor",
            district="learning",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.concept_graph = {}
        logger.info("[VECTOR][learning] ConceptExtractor ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        if os.getenv("VECTOR_LEARNING_LLM") != "1":
            return '[{"name":"offline_concept","definition":"Offline concept extraction fallback","importance":5,"related_concepts":[]}]'
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def extract_concepts(self, text: str) -> dict:
        logger.info(f"[VECTOR][learning] Extracting concepts from text ({len(text)} chars)")
        self.add_lesson({"action": "extract_concepts", "text_length": len(text)})

        prompt = f"""Extract key concepts from this text. Return a JSON list of concept objects with fields: name, definition, importance (1-10), related_concepts (list of strings).
Text: {text[:2000]}
Format: JSON list only, no explanation."""
        response = self._call_ollama(prompt)

        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                concepts = json.loads(json_match.group(0))
            else:
                concepts = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[VECTOR][learning] Could not parse concepts as JSON")
            concepts = [{"name": "extracted_concepts", "definition": response, "importance": 5, "related_concepts": []}]

        result = {
            "concepts": concepts,
            "count": len(concepts),
            "source_text_length": len(text),
        }

        for c in concepts:
            name = c.get("name", "")
            if name:
                self.concept_graph[name] = {"definition": c.get("definition", ""), "importance": c.get("importance", 5), "related": c.get("related_concepts", [])}

        self.memory.store(
            event_type="concepts_extracted",
            content=f"Extracted {len(concepts)} concepts from text",
            tags=["learning", "concepts", "extraction"],
            context=result,
            source="ConceptExtractor"
        )

        logger.info(f"[VECTOR][learning] Extracted {len(concepts)} concepts")
        return result

    def map_concepts(self, concept_list: list[dict]) -> dict:
        logger.info(f"[VECTOR][learning] Mapping {len(concept_list)} concepts")
        self.add_lesson({"action": "map_concepts", "count": len(concept_list)})

        prompt = f"""Create a concept map showing relationships between these concepts. 
Return JSON with: nodes (each with id, label, importance), edges (each with from, to, type: prerequisite|related|depends-on).
Concepts: {json.dumps(concept_list[:20])}
Format: JSON only."""
        response = self._call_ollama(prompt)

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                concept_map = json.loads(json_match.group(0))
            else:
                concept_map = {"nodes": [], "edges": [], "raw_response": response[:500]}
        except json.JSONDecodeError:
            concept_map = {"nodes": [], "edges": [], "raw_response": response[:500]}

        result = {
            "nodes": concept_map.get("nodes", []),
            "edges": concept_map.get("edges", []),
            "total_concepts": len(concept_list),
        }

        self.memory.store(
            event_type="concept_map_created",
            content=f"Created concept map with {len(result['nodes'])} nodes and {len(result['edges'])} edges",
            tags=["learning", "concepts", "map"],
            context=result,
            source="ConceptExtractor"
        )

        return result

    def suggest_prerequisites(self, concept: str) -> dict:
        logger.info(f"[VECTOR][learning] Suggesting prerequisites for: {concept}")
        self.add_lesson({"action": "suggest_prerequisites", "concept": concept})

        if concept in self.concept_graph:
            related = self.concept_graph[concept].get("related", [])
            if related:
                return {"concept": concept, "prerequisites": related[:5], "source": "local_graph"}

        prompt = f'What are the prerequisites needed to understand \'{concept}\' in a learning path? List 5-8 prerequisite concepts or topics with brief descriptions. Format as JSON: {{"prerequisites": [{{"name": "...", "description": "..."}}]}}'
        response = self._call_ollama(prompt)

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                prereqs = json.loads(json_match.group(0))
            else:
                prereqs = {"prerequisites": []}
        except json.JSONDecodeError:
            prereqs = {"prerequisites": []}

        result = {"concept": concept, "prerequisites": prereqs.get("prerequisites", []), "llm_response": response[:500]}

        self.memory.store(
            event_type="prerequisites_suggested",
            content=f"Suggested prerequisites for '{concept}'",
            tags=["learning", "prerequisites", concept],
            context=result,
            source="ConceptExtractor"
        )

        return result


    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["extract_concepts", "suggest_prerequisites"]

        if task_type == "extract_concepts":
            result = self.extract_concepts(p.get("text", ""))
            return {"status": "ok", **result}
        if task_type == "suggest_prerequisites":
            result = self.suggest_prerequisites(p.get("concept", ""))
            return {"status": "ok", **result}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = ConceptExtractor()
    assert agent.district == "learning"

    text = "Machine learning is a subset of artificial intelligence that enables systems to learn from data. Deep learning uses neural networks with many layers. Transformers revolutionized NLP."
    result = agent.extract_concepts(text)
    assert "concepts" in result
    assert result["count"] >= 1

    if result["concepts"]:
        cmap = agent.map_concepts(result["concepts"])
        assert "nodes" in cmap

    prereqs = agent.suggest_prerequisites("deep learning")
    assert "concept" in prereqs
    assert prereqs["concept"] == "deep learning"

    print("✅ concept_extractor.py OK")
