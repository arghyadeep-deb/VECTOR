"""
ZK Steward — Zettelkasten knowledge management for VECTOR Brain vault.

Reads Obsidian notes, extracts key concepts, finds non-obvious connections,
inserts backlinks, and builds a living Master of Concepts index.
Based on Niklas Luhmann's Zettelkasten method adapted for AI-assisted knowledge.
"""

import asyncio
import datetime
import re
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine

class ZKSteward(AgentBase):
    """
    Zettelkasten knowledge steward for VECTOR Brain vault.
    Links concepts across notes, builds knowledge graph, creates MOC index.
    """

    def __init__(self):
        super().__init__(agent_id="zk_steward_001", name="ZKSteward", district="personal_growth")
        self.capabilities = ["notes", "personal_growth", "zettelkasten"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._vault_path = Path(CONFIG.get("vault_path") or CONFIG.get("obsidian", {}).get("vault_path") or str(Path.home() / "Desktop" / "V.E.C.T.O.R" / "V.E.C.T.O.R. Brain"))
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][zk_steward] initialized — vault={}", self._vault_path)

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self) -> ObsidianSync:
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    # ── Vault scanning ────────────────────────────────────────────────────────

    def scan_vault_notes(self, limit: int = 50) -> list[dict]:
        """Read recent .md files from the Obsidian vault."""
        if not self._vault_path.exists():
            logger.warning("[VECTOR][zk_steward] vault not found: {}", self._vault_path)
            return []

        md_files = sorted(
            self._vault_path.rglob("*.md"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]

        notes = []
        for f in md_files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                if len(content.strip()) < 50:
                    continue
                notes.append({
                    "path": str(f),
                    "name": f.stem,
                    "content": content[:2000],
                    "modified": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
            except Exception as e:
                logger.debug("[VECTOR][zk_steward] skip {}: {}", f.name, e)

        logger.info("[VECTOR][zk_steward] scanned {} notes from vault", len(notes))
        return notes

    def extract_existing_links(self, content: str) -> set[str]:
        """Extract all [[wikilinks]] already in a note."""
        return set(re.findall(r'\[\[([^\]]+)\]\]', content))

    # ── Concept extraction ────────────────────────────────────────────────────

    async def extract_concepts(self, note_name: str, content: str) -> list[str]:
        """Use LLM to extract 3-5 key concepts from a note."""
        prompt = (
            f"Extract exactly 3-5 key concepts from this note titled '{note_name}'.\n"
            f"Rules: single words or short phrases (max 3 words), no duplicates, "
            f"concepts that would connect to other topics.\n"
            f"Reply with just the concepts, one per line, nothing else.\n\n"
            f"Note content:\n{content[:800]}"
        )
        try:
            from core.prompt_library import get_library as _gl
            hydration = ContextEngine().session_hydration_prompt({"task": "extract_concepts"})
            _sys = _gl().get_for_agent("zk_steward") or ""
            _msgs = [{"role": "system", "content": hydration}]
            if _sys:
                _msgs.append({"role": "system", "content": _sys})
            _msgs.append({"role": "user", "content": prompt})
            response = chat(
                model=self._model,
                messages=_msgs,
                timeout=15.0,
            )
            concepts = [c.strip().lower() for c in response.strip().splitlines() if c.strip()]
            return concepts[:5]
        except Exception as e:
            logger.debug("[VECTOR][zk_steward] concept extract failed: {}", e)
            return []

    # ── Connection finding ─────────────────────────────────────────────────────

    async def find_connections(self, note_name: str, concepts: list[str], other_notes: list[dict]) -> list[str]:
        """Find which other notes are conceptually related — return note names."""
        if not concepts or not other_notes:
            return []

        # Build a short index of other notes
        index_lines = []
        for n in other_notes[:20]:
            if n["name"] == note_name:
                continue
            index_lines.append(f"- {n['name']}: {n['content'][:120]}")
        if not index_lines:
            return []

        prompt = (
            f"Note '{note_name}' covers concepts: {', '.join(concepts)}.\n\n"
            f"Which of these notes are non-obviously related (shared themes, "
            f"complementary ideas, or useful contrasts)?\n"
            f"Reply with just the note names, one per line. Max 4. "
            f"Only include genuinely useful connections, not superficial ones.\n\n"
            f"Available notes:\n" + "\n".join(index_lines)
        )
        try:
            hydration = ContextEngine().session_hydration_prompt({"task": "find_connections"})
            response = chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": prompt},
                ],
                timeout=15.0,
            )
            related = [r.strip().strip("-").strip() for r in response.strip().splitlines() if r.strip()]
            return related[:4]
        except Exception as e:
            logger.debug("[VECTOR][zk_steward] connection find failed: {}", e)
            return []

    # ── Backlink insertion ─────────────────────────────────────────────────────

    def insert_backlinks(self, note_path: str, related_notes: list[str]) -> int:
        """Add [[wikilinks]] to the bottom of a note. Returns number added."""
        p = Path(note_path)
        if not p.exists():
            return 0

        content = p.read_text(encoding="utf-8", errors="replace")
        existing_links = self.extract_existing_links(content)
        new_links = [n for n in related_notes if n not in existing_links and n]

        if not new_links:
            return 0

        link_section = "\n\n---\n*ZK connections: " + " ".join(f"[[{l}]]" for l in new_links) + "*\n"

        # Avoid duplicate ZK sections
        if "*ZK connections:" in content:
            # Update existing section
            content = re.sub(
                r'\n\n---\n\*ZK connections:.*?\*\n',
                link_section,
                content,
                flags=re.DOTALL,
            )
        else:
            content += link_section

        try:
            p.write_text(content, encoding="utf-8")
            logger.debug("[VECTOR][zk_steward] added {} links to {}", len(new_links), p.name)
            return len(new_links)
        except Exception as e:
            logger.warning("[VECTOR][zk_steward] write failed for {}: {}", p.name, e)
            return 0

    # ── Knowledge graph summary ────────────────────────────────────────────────

    def build_knowledge_graph_summary(self, notes: list[dict]) -> dict:
        """Count total notes, links, and identify most-linked notes."""
        total_links = 0
        link_counts: dict[str, int] = {}

        for note in notes:
            links = self.extract_existing_links(note["content"])
            total_links += len(links)
            for link in links:
                link_counts[link] = link_counts.get(link, 0) + 1

        top_nodes = sorted(link_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "total_notes": len(notes),
            "total_links": total_links,
            "avg_links_per_note": round(total_links / max(1, len(notes)), 2),
            "top_connected_nodes": [{"note": n, "incoming_links": c} for n, c in top_nodes],
        }

    # ── MOC index ─────────────────────────────────────────────────────────────

    async def generate_index_note(self, graph: dict) -> str:
        """Create/update a Master of Concepts note in Obsidian."""
        top_nodes = graph.get("top_connected_nodes", [])
        top_str = "\n".join(f"- [[{n['note']}]] ({n['incoming_links']} links)" for n in top_nodes[:10])

        content = (
            f"# MOC — Master of Concepts\n"
            f"*Auto-generated by ZKSteward · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
            f"## Knowledge Graph Stats\n"
            f"- Total notes indexed: {graph['total_notes']}\n"
            f"- Total wiki-links: {graph['total_links']}\n"
            f"- Avg links per note: {graph['avg_links_per_note']}\n\n"
            f"## Most Connected Nodes\n{top_str}\n\n"
            f"## How to use this\n"
            f"Follow the most-connected nodes to find the spine of the knowledge base. "
            f"Notes with many incoming links are core concepts worth mastering deeply.\n"
        )

        try:
            moc_path = self._vault_path / "MOC — Master of Concepts.md"
            moc_path.write_text(content, encoding="utf-8")
            logger.info("[VECTOR][zk_steward] MOC index updated: {}", moc_path)
            return str(moc_path)
        except Exception as e:
            logger.warning("[VECTOR][zk_steward] MOC write failed: {}", e)
            return ""

    async def answer_personal_growth_question(self, query: str) -> str:
        """Answer a free-text question instead of blindly running a full
        ZK vault scan that actually edits the owner's real notes (inserting
        backlinks) and rewrites the MOC index on every call, regardless of
        what was actually asked (KNOWN_ISSUES bug pattern: a real,
        unrelated file-mutation side effect from a stray conversational
        message)."""
        try:
            notes = self.scan_vault_notes(limit=30)
            context = f"{len(notes)} note(s) in the Zettelkasten vault currently scannable."
        except Exception:
            context = "Vault note count unavailable right now."
        prompt = (
            "You are VECTOR's ZKSteward in the personal_growth district — "
            "you maintain a Zettelkasten knowledge vault (concept "
            "extraction, backlinks, a Master-of-Concepts index). Answer "
            "the owner's question using this real context; do not invent "
            f"data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            result = self.vchat([{"role": "user", "content": prompt}])
            return (result or "").strip() or context
        except Exception as e:
            logger.warning("[VECTOR][zk_steward] answer_personal_growth_question failed: {}", e)
            return context

    # ── Main run ───────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        Full ZK scan: scan vault → extract concepts → find connections →
        insert backlinks → update MOC → store graph stats.
        """
        query = (
            (task.get("params") or {}).get("query")
            or task.get("query")
            or task.get("text")
            or ""
        ).strip()
        if query:
            answer = await self.answer_personal_growth_question(query)
            if answer:
                self.award_points(10, "personal_growth_question_answered")
                return {"status": "ok", "response": answer}

        try:
            limit = task.get("limit", 30)
            notes = self.scan_vault_notes(limit=limit)
            if not notes:
                return {"status": "ok", "message": "vault empty or not found", "links_added": 0}

            total_links_added = 0
            concepts_by_note: dict[str, list[str]] = {}

            # Phase 1: extract concepts from each note
            for note in notes[:15]:  # process 15 notes per run to stay fast
                concepts = await self.extract_concepts(note["name"], note["content"])
                if concepts:
                    concepts_by_note[note["name"]] = concepts

            # Phase 2: find connections and insert backlinks
            for note in notes[:15]:
                if note["name"] not in concepts_by_note:
                    continue
                related = await self.find_connections(
                    note["name"],
                    concepts_by_note[note["name"]],
                    notes,
                )
                if related:
                    added = self.insert_backlinks(note["path"], related)
                    total_links_added += added

            # Phase 3: build graph summary and update MOC
            graph = self.build_knowledge_graph_summary(notes)
            moc_path = await self.generate_index_note(graph)

            # Store in memory
            mem = self._get_memory()
            mem.store(
                event_type="zk_steward_run",
                content=(
                    f"ZK scan: {graph['total_notes']} notes, "
                    f"{total_links_added} new links added, "
                    f"MOC updated"
                ),
                tags=["personal_growth", "knowledge_management", "zettelkasten"],
                context=graph,
                source="zk_steward",
            )

            if total_links_added > 0:
                self.award_points(40 + total_links_added * 2, "knowledge_connections_found")
                logger.info("[VECTOR][zk_steward] {} new connections added", total_links_added)
            else:
                self.award_points(10, "zk_scan_complete_no_new_links")

            return {
                "status": "ok",
                "notes_scanned": len(notes),
                "links_added": total_links_added,
                "graph": graph,
                "moc_path": moc_path,
            }

        except Exception as e:
            logger.error("[VECTOR][zk_steward] run failed: {}", e)
            self.deduct_points(30, "zk_scan_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ZKSteward()
        notes = agent.scan_vault_notes(limit=5)
        print(f"[OK] scan_vault_notes: {len(notes)} notes")
        graph = agent.build_knowledge_graph_summary(notes)
        print(f"[OK] knowledge_graph_summary: {graph['total_notes']} notes, {graph['total_links']} links")
        if notes:
            concepts = await agent.extract_concepts(notes[0]["name"], notes[0]["content"])
            print(f"[OK] extract_concepts: {concepts}")
        result = await agent.run({"limit": 5})
        print(f"[OK] run: links_added={result.get('links_added')} status={result['status']}")
        print("zk_steward.py OK")

    asyncio.run(_smoke())
