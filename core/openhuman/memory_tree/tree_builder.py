"""
VECTOR Memory Tree — hierarchical summary tree builder.

Builds a 3-level tree from ingested content:
  Level 0: Source (document/channel/integration)
  Level 1: Topic  (auto-clustered from content)
  Level 2: Chunk  (atomic fact/memory unit)

Each level has a rolling summary kept under token budget.
Writes Obsidian-compatible markdown wikis to brain/.

Ported from openhuman's memory/tree/ architecture.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger

_TREE_DB = Path.home() / ".vector_ca" / "memory_tree"
_BRAIN_WIKI = Path("brain") / "VECTOR" / "wiki"


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class TreeChunk:
    """Atomic memory unit — a single fact or observation."""
    id: str
    source_kind: str        # "conversation" | "document" | "integration" | "observation"
    source_id: str
    topic: str
    content: str
    created_at: str
    score: float = 1.0      # relevance/importance score
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "TreeChunk":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TreeNode:
    """Topic-level node containing multiple chunks with a rolling summary."""
    topic: str
    summary: str = ""
    chunks: list[TreeChunk] = field(default_factory=list)
    updated_at: str = ""

    def add_chunk(self, chunk: TreeChunk) -> None:
        self.chunks.append(chunk)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def chunk_count(self) -> int:
        return len(self.chunks)


@dataclass
class MemorySource:
    """Source-level root containing multiple topic nodes."""
    source_kind: str
    source_id: str
    nodes: dict[str, TreeNode] = field(default_factory=dict)
    global_summary: str = ""
    updated_at: str = ""

    def get_or_create_node(self, topic: str) -> TreeNode:
        if topic not in self.nodes:
            self.nodes[topic] = TreeNode(topic=topic)
        return self.nodes[topic]


# ── MemoryTree ─────────────────────────────────────────────────────────────────

class MemoryTree:
    """
    Hierarchical memory tree: Source → Topic → Chunk.

    Usage:
        tree = MemoryTree()
        tree.ingest("conversation", "session_abc", "Python is great for AI", topic="coding")
        wiki = tree.build_wiki("conversation", "session_abc")
        tree.save_wiki(wiki, "session_abc")
    """

    def __init__(self, db_dir: Path | None = None, wiki_dir: Path | None = None) -> None:
        self._db_dir = db_dir or _TREE_DB
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._wiki_dir = wiki_dir or _BRAIN_WIKI
        self._sources: dict[str, MemorySource] = {}
        self._load()

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def ingest(
        self,
        source_kind: str,
        source_id: str,
        content: str,
        topic: str | None = None,
        tags: list[str] | None = None,
        score: float = 1.0,
    ) -> TreeChunk:
        """
        Ingest a piece of content into the memory tree.

        Args:
            source_kind: "conversation" | "document" | "integration" | "observation"
            source_id:   Unique identifier for the source (session ID, file path, etc.)
            content:     Text content to store
            topic:       Topic/category (auto-detected if not provided)
            tags:        Optional tags for retrieval
            score:       Importance score 0.0–1.0

        Returns:
            The created TreeChunk.
        """
        if topic is None:
            topic = self._detect_topic(content)

        chunk = TreeChunk(
            id=self._chunk_id(source_id, content),
            source_kind=source_kind,
            source_id=source_id,
            topic=topic,
            content=content,
            created_at=datetime.now(timezone.utc).isoformat(),
            score=score,
            tags=tags or [],
        )

        key = f"{source_kind}:{source_id}"
        if key not in self._sources:
            self._sources[key] = MemorySource(source_kind=source_kind, source_id=source_id)

        source = self._sources[key]
        node = source.get_or_create_node(topic)
        node.add_chunk(chunk)
        source.updated_at = datetime.now(timezone.utc).isoformat()

        self._save()
        logger.debug("[VECTOR][memory_tree] ingested chunk topic={} source={}", topic, source_id[:16])
        return chunk

    def ingest_document(
        self,
        source_id: str,
        text: str,
        max_chunk_chars: int = 800,
        source_kind: str = "document",
    ) -> list[TreeChunk]:
        """Split a document into chunks and ingest each."""
        chunks = self._split_text(text, max_chunk_chars)
        results = []
        for chunk_text in chunks:
            if chunk_text.strip():
                results.append(self.ingest(source_kind, source_id, chunk_text))
        logger.info("[VECTOR][memory_tree] ingested {} chunks from {}", len(results), source_id[:40])
        return results

    # ── Query ──────────────────────────────────────────────────────────────────

    def query(
        self,
        query: str,
        source_kind: str | None = None,
        topic: str | None = None,
        top_k: int = 10,
    ) -> list[TreeChunk]:
        """Simple keyword search across all chunks."""
        keywords = set(query.lower().split())
        scored: list[tuple[float, TreeChunk]] = []

        for key, source in self._sources.items():
            if source_kind and source.source_kind != source_kind:
                continue
            for t, node in source.nodes.items():
                if topic and t != topic:
                    continue
                for chunk in node.chunks:
                    text_lower = chunk.content.lower()
                    hits = sum(1 for kw in keywords if kw in text_lower)
                    if hits:
                        scored.append((hits * chunk.score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def get_topics(self, source_kind: str | None = None) -> list[str]:
        topics: set[str] = set()
        for key, source in self._sources.items():
            if source_kind and source.source_kind != source_kind:
                continue
            topics.update(source.nodes.keys())
        return sorted(topics)

    def get_chunks(self, source_kind: str, source_id: str, topic: str | None = None) -> list[TreeChunk]:
        key = f"{source_kind}:{source_id}"
        source = self._sources.get(key)
        if not source:
            return []
        if topic:
            return source.nodes.get(topic, TreeNode(topic=topic)).chunks
        return [c for node in source.nodes.values() for c in node.chunks]

    # ── Wiki builder ───────────────────────────────────────────────────────────

    def build_wiki(self, source_kind: str, source_id: str) -> str:
        """Build an Obsidian-compatible markdown wiki for a source."""
        key = f"{source_kind}:{source_id}"
        source = self._sources.get(key)
        if not source:
            return f"# {source_id}\n\nNo memory tree data yet.\n"

        lines = [
            f"# Memory Tree — {source_id}",
            f"*Source: {source_kind} | Updated: {source.updated_at[:10]}*",
            "",
        ]

        for topic, node in sorted(source.nodes.items()):
            lines.append(f"## {topic.replace('_', ' ').title()}")
            if node.summary:
                lines.append(f"> {node.summary}")
                lines.append("")
            for chunk in node.chunks[-10:]:  # last 10 per topic
                lines.append(f"- {chunk.content}")
            lines.append("")

        return "\n".join(lines)

    def save_wiki(self, wiki_content: str, name: str) -> Path:
        """Save wiki to brain/ as Obsidian markdown."""
        safe = re.sub(r"[^\w\-]", "_", name)[:50]
        path = self._wiki_dir / f"{safe}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wiki_content, encoding="utf-8")
        logger.info("[VECTOR][memory_tree] wiki saved: {}", path)
        return path

    def build_and_save_all(self) -> list[Path]:
        """Build + save wikis for all sources."""
        paths = []
        for key, source in self._sources.items():
            wiki = self.build_wiki(source.source_kind, source.source_id)
            paths.append(self.save_wiki(wiki, source.source_id))
        return paths

    # ── Topic detection ────────────────────────────────────────────────────────

    _TOPIC_KEYWORDS = {
        "coding": {"code", "function", "class", "error", "debug", "python", "rust", "api", "git"},
        "research": {"paper", "study", "research", "found", "analysis", "data", "model"},
        "finance": {"money", "budget", "cost", "price", "stock", "crypto", "payment", "invoice"},
        "health": {"sleep", "exercise", "diet", "fatigue", "energy", "health", "mood"},
        "goals": {"goal", "want", "plan", "achieve", "target", "milestone", "progress"},
        "learning": {"learn", "course", "skill", "read", "study", "understand", "practice"},
        "relationships": {"friend", "family", "colleague", "meeting", "conversation", "message"},
        "tasks": {"todo", "task", "deadline", "complete", "finish", "done", "working"},
    }

    def _detect_topic(self, content: str) -> str:
        words = set(content.lower().split())
        best, best_score = "general", 0
        for topic, keywords in self._TOPIC_KEYWORDS.items():
            score = len(words & keywords)
            if score > best_score:
                best, best_score = topic, score
        return best

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_id(source_id: str, content: str) -> str:
        raw = f"{source_id}:{content[:100]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        paragraphs = re.split(r"\n{2,}", text.strip())
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > max_chars and current:
                chunks.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para).strip() if current else para
        if current:
            chunks.append(current.strip())
        return chunks

    # ── Persistence ────────────────────────────────────────────────────────────

    def _db_path(self) -> Path:
        return self._db_dir / "memory_tree.json"

    def _save(self) -> None:
        data = {}
        for key, source in self._sources.items():
            data[key] = {
                "source_kind": source.source_kind,
                "source_id": source.source_id,
                "global_summary": source.global_summary,
                "updated_at": source.updated_at,
                "nodes": {
                    topic: {
                        "summary": node.summary,
                        "updated_at": node.updated_at,
                        "chunks": [c.to_dict() for c in node.chunks],
                    }
                    for topic, node in source.nodes.items()
                },
            }
        self._db_path().write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        p = self._db_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for key, sd in data.items():
                source = MemorySource(
                    source_kind=sd["source_kind"],
                    source_id=sd["source_id"],
                    global_summary=sd.get("global_summary", ""),
                    updated_at=sd.get("updated_at", ""),
                )
                for topic, nd in sd.get("nodes", {}).items():
                    node = TreeNode(
                        topic=topic,
                        summary=nd.get("summary", ""),
                        updated_at=nd.get("updated_at", ""),
                    )
                    for cd in nd.get("chunks", []):
                        try:
                            node.chunks.append(TreeChunk.from_dict(cd))
                        except Exception:
                            pass
                    source.nodes[topic] = node
                self._sources[key] = source
        except Exception as e:
            logger.warning("[VECTOR][memory_tree] load failed: {}", e)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tree = MemoryTree(db_dir=Path(d) / "db", wiki_dir=Path(d) / "wiki")
        tree.ingest("conversation", "sess_001", "Python is great for building AI agents", topic="coding")
        tree.ingest("conversation", "sess_001", "VECTOR uses Ollama for local inference", topic="coding")
        tree.ingest("document", "paper_001", "Transformer architecture uses attention mechanisms", topic="research")
        chunks = tree.query("Python AI", top_k=5)
        assert len(chunks) >= 1
        wiki = tree.build_wiki("conversation", "sess_001")
        assert "coding" in wiki.lower()
        p = tree.save_wiki(wiki, "sess_001")
        assert p.exists()
    print("OK memory_tree/tree_builder.py")
