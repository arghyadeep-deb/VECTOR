"""
Module: agents/learning/note_organizer.py
District: learning | Focus: Organize, summarize, and link notes
"""

import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, re, os
from typing import Optional


class NoteOrganizer(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="NoteOrganizer",
            district="learning",
            generation=1
        )
        self.capabilities = ["learning", "link", "link_notes", "notes", "organis", "organize", "organize_notes", "summarize_notes"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.notes_index = {}
        self.links = {}
        logger.info("[VECTOR][learning] NoteOrganizer ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        if os.getenv("VECTOR_LEARNING_LLM") != "1":
            return "Offline learning summary available; set VECTOR_LEARNING_LLM=1 for live model analysis."
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

    def organize_notes(self, source_dir: str) -> dict:
        logger.info(f"[VECTOR][learning] Organizing notes from: {source_dir}")
        self.add_lesson({"action": "organize_notes", "source": source_dir})

        # Path("") == Path(".") exists: an empty source_dir would otherwise
        # organize (and write next to) the process CWD.
        if not (source_dir or "").strip():
            return {"error": "source_dir is required", "path": source_dir}
        source = Path(source_dir)
        if not source.is_dir():
            logger.error(f"[VECTOR][learning] Source directory not found: {source_dir}")
            return {"error": "Source directory not found", "path": source_dir}

        topics = {}
        for md_file in source.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                heading_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                title = heading_match.group(1) if heading_match else md_file.stem

                words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', content[:500])
                rel = str(md_file.relative_to(source))
                if title in topics:  # same heading in two files: don't drop one
                    title = f"{title} ({rel})"
                topics[title] = {"file": rel, "file_size": md_file.stat().st_size, "preview": content[:200]}
            except Exception as e:
                logger.warning(f"[VECTOR][learning] Could not read {md_file}: {e}")

        categories = {
            "tech": [],
            "science": [],
            "business": [],
            "personal": [],
            "general": [],
        }

        for title, info in topics.items():
            prompt = f"Categorize this note title into one of: tech, science, business, personal, general.\nTitle: {title}\nPreview: {info['preview'][:100]}\nReturn only the category word."
            category = self._call_ollama(prompt).strip().lower()
            if category in categories:
                categories[category].append(title)
            else:
                categories["general"].append(title)

        organized_dir = Path(source_dir).parent / "organized"
        organized_dir.mkdir(parents=True, exist_ok=True)

        for cat, notes in categories.items():
            cat_dir = organized_dir / cat
            cat_dir.mkdir(exist_ok=True)
            index_content = f"# {cat.upper()} Notes\n\n"
            for note_title in notes:
                index_content += f"- [[{note_title}]]\n"
                self.notes_index[note_title] = {"category": cat, "topics": topics[note_title]}
            (cat_dir / "_index.md").write_text(index_content, encoding="utf-8")

        result = {
            "source": source_dir,
            "organized_to": str(organized_dir),
            "total_notes": len(topics),
            "categories": {k: len(v) for k, v in categories.items()},
        }

        self.memory.store(
            event_type="notes_organized",
            content=f"Organized {len(topics)} notes into {len(categories)} categories",
            tags=["learning", "notes", "organization"],
            context=result,
            source="NoteOrganizer"
        )

        logger.info(f"[VECTOR][learning] Organized {len(topics)} notes into categories")
        return result

    def summarize_notes(self, topic: str) -> dict:
        logger.info(f"[VECTOR][learning] Summarizing notes on: {topic}")
        self.add_lesson({"action": "summarize_notes", "topic": topic})

        matching_notes = []
        for title, info in self.notes_index.items():
            if topic.lower() in title.lower() or topic.lower() in info.get("topics", {}).get("preview", "").lower():
                matching_notes.append({"title": title, "category": info["category"]})

        if not matching_notes:
            # Don't ask the LLM to "summarize" a placeholder title.
            logger.info("[VECTOR][learning] No indexed notes match '{}'", topic)
            return {
                "topic": topic,
                "matching_notes": 0,
                "summary": "",
                "note_titles": [],
                "note": "No matching notes found; run organize_notes first",
            }

        prompt = f"Create a comprehensive summary of notes on '{topic}'. Found {len(matching_notes)} related notes. Format as structured markdown with key points, definitions, and takeaways.\nNotes: {json.dumps([n['title'] for n in matching_notes])}"
        summary = self._call_ollama(prompt)

        result = {
            "topic": topic,
            "matching_notes": len(matching_notes),
            "summary": summary,
            "note_titles": [n["title"] for n in matching_notes],
        }

        self.memory.store(
            event_type="notes_summarized",
            content=f"Summarized {len(matching_notes)} notes on topic '{topic}'",
            tags=["learning", "notes", "summary", topic],
            context=result,
            source="NoteOrganizer"
        )

        return result

    def link_notes(self, concept_a: str, concept_b: str) -> dict:
        logger.info(f"[VECTOR][learning] Linking notes: {concept_a} <-> {concept_b}")
        self.add_lesson({"action": "link_notes", "concept_a": concept_a, "concept_b": concept_b})

        link_id = f"{concept_a}___{concept_b}"
        self.links[link_id] = {
            "concept_a": concept_a,
            "concept_b": concept_b,
            "created_at": self.last_active,
            "bidirectional": True,
        }

        reverse_link = f"{concept_b}___{concept_a}"
        if reverse_link not in self.links:
            self.links[reverse_link] = {"concept_a": concept_b, "concept_b": concept_a, "created_at": self.last_active, "bidirectional": False, "reverse_of": link_id}

        prompt = f"Explain the relationship between '{concept_a}' and '{concept_b}'. How are they connected or related? Give 3-5 key connection points."
        relationship = self._call_ollama(prompt)

        result = {
            "concept_a": concept_a,
            "concept_b": concept_b,
            "relationship": relationship,
            "bidirectional": True,
            "total_links": len(self.links),
        }

        self.memory.store(
            event_type="notes_linked",
            content=f"Linked '{concept_a}' with '{concept_b}'",
            tags=["learning", "notes", "links"],
            context=result,
            source="NoteOrganizer"
        )

        return result


    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["organize_notes", "summarize_notes", "link_notes"]

        if task_type == "organize_notes":
            result = self.organize_notes(p.get("source_dir", ""))
            return {"status": "error" if result.get("error") else "ok", **result}
        if task_type == "summarize_notes":
            result = self.summarize_notes(p.get("topic", ""))
            return {"status": "ok", **result}
        if task_type == "link_notes":
            result = self.link_notes(p.get("concept_a", ""), p.get("concept_b", ""))
            return {"status": "ok", **result}

        # 2026-08-04: real chat dispatch arrives as an LLM-invented task_type
        # with the user's question in params["query"] — "summarize my notes on
        # config" previously returned a bare "unhandled type" error. Route a
        # real question to a real capability instead.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            a, b = p.get("concept_a", ""), p.get("concept_b", "")
            if a and b and any(w in q for w in ("link", "connect", "relate", "between")):
                result = self.link_notes(a, b)
                return {"status": "ok", **result}
            if p.get("source_dir") and any(w in q for w in ("organis", "organiz", "tidy", "sort")):
                result = self.organize_notes(p["source_dir"])
                return {"status": "error" if result.get("error") else "ok", **result}
            # Summarising is the read-only, no-required-arg default; topic
            # falls back to the question itself so the summary is scoped to
            # what was actually asked.
            result = self.summarize_notes(p.get("topic", "") or query)
            return {"status": "ok", **result}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = NoteOrganizer()
    assert agent.district == "learning"

    result = agent.organize_notes("C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/V.E.C.T.O.R. Codebase/core")
    assert "organized_to" in result

    summary = agent.summarize_notes("config")
    assert "summary" in summary

    link = agent.link_notes("machine learning", "neural networks")
    assert "relationship" in link
    assert link["bidirectional"] is True

    print("✅ note_organizer.py OK")
