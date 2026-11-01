"""
VECTOR Knowledge Graph — SQLite-backed entity-relation triple store.

Complements episodic memory and LightRAG with structured graph queries:
  add_entity("Python", "programming_language", {"typed": "static/dynamic"})
  add_relation("Python", "used_for", "AI development")
  query_graph("Python")  → entities and relations involving Python

Ported from the agent OS memory/knowledge.rs KnowledgeStore.
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas
__all__ = [
    "Entity",
    "get_knowledge_graph",
    "GraphQueryResult",
    "KnowledgeGraph",
    "Relation",
]


import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

_KG_DB = Path.home() / ".vector_ca" / "knowledge_graph.db"


@dataclass
class Entity:
    name: str
    entity_type: str
    properties: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.entity_type,
                "properties": self.properties, "created_at": self.created_at}


@dataclass
class Relation:
    subject: str
    predicate: str
    obj: str
    confidence: float = 1.0
    source: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"subject": self.subject, "predicate": self.predicate,
                "object": self.obj, "confidence": self.confidence,
                "source": self.source, "created_at": self.created_at}


@dataclass
class GraphQueryResult:
    entities: list[Entity]
    relations: list[Relation]
    query: str

    @property
    def total(self) -> int:
        return len(self.entities) + len(self.relations)

    def to_markdown(self) -> str:
        lines = [f"## Knowledge Graph: {self.query}", ""]
        if self.entities:
            lines.append("### Entities")
            for e in self.entities:
                props = ", ".join(f"{k}={v}" for k, v in e.properties.items())
                lines.append(f"- **{e.name}** ({e.entity_type})" + (f" — {props}" if props else ""))
        if self.relations:
            lines.append("\n### Relations")
            for r in self.relations:
                lines.append(f"- {r.subject} **{r.predicate}** {r.obj} (conf={r.confidence:.2f})")
        return "\n".join(lines)


class KnowledgeGraph:
    """
    SQLite-backed entity-relation triple store.

    Usage:
        kg = KnowledgeGraph()
        kg.add_entity("VECTOR", "ai_system", {"phase": "1", "owner": "arghyadeep"})
        kg.add_relation("VECTOR", "built_with", "Python")
        kg.add_relation("VECTOR", "runs_on", "Ollama")
        result = kg.query("VECTOR")
        logger.info(result.to_markdown())

    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _KG_DB
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        apply_pragmas(conn)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS entities (
                    name        TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT 'concept',
                    properties  TEXT NOT NULL DEFAULT '{}',
                    created_at  REAL NOT NULL,
                    PRIMARY KEY (name)
                );
                CREATE TABLE IF NOT EXISTS relations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject     TEXT NOT NULL,
                    predicate   TEXT NOT NULL,
                    object      TEXT NOT NULL,
                    confidence  REAL NOT NULL DEFAULT 1.0,
                    source      TEXT NOT NULL DEFAULT '',
                    created_at  REAL NOT NULL,
                    UNIQUE(subject, predicate, object)
                );
                CREATE INDEX IF NOT EXISTS idx_rel_subject  ON relations(subject);
                CREATE INDEX IF NOT EXISTS idx_rel_object   ON relations(object);
                CREATE INDEX IF NOT EXISTS idx_rel_pred     ON relations(predicate);
                CREATE INDEX IF NOT EXISTS idx_ent_type     ON entities(entity_type);
            """)

    # ── Write ──────────────────────────────────────────────────────────────────

    def add_entity(
        self,
        name: str,
        entity_type: str = "concept",
        properties: dict | None = None,
    ) -> Entity:
        """Add or update an entity."""
        entity = Entity(name=name, entity_type=entity_type,
                        properties=properties or {})
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO entities (name, entity_type, properties, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     entity_type=excluded.entity_type,
                     properties=excluded.properties""",
                (name, entity_type, json.dumps(properties or {}), entity.created_at),
            )
        logger.debug("[VECTOR][kg] entity: {} ({})", name, entity_type)
        return entity

    def add_relation(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source: str = "",
    ) -> Relation:
        """Add a subject-predicate-object triple."""
        relation = Relation(subject=subject, predicate=predicate,
                            obj=obj, confidence=confidence, source=source)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO relations (subject, predicate, object, confidence, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(subject, predicate, object) DO UPDATE SET
                     confidence=excluded.confidence,
                     source=excluded.source""",
                (subject, predicate, obj, confidence, source, relation.created_at),
            )
        logger.debug("[VECTOR][kg] relation: {} {} {}", subject, predicate, obj)
        return relation

    def add_from_text(self, text: str, source: str = "") -> list[Relation]:
        """
        Extract and add relations from free text using simple heuristics.
        Pattern: 'X is/uses/has/builds/runs Y'
        """
        import re
        pattern = re.compile(
            r'([A-Z]\w+(?:\s[A-Z]\w+)?)\s+'
            r'(is|uses|has|builds|runs|supports|integrates|connects|enables|provides)\s+'
            r'([A-Z]\w+(?:\s[A-Z]\w+)?)',
            re.IGNORECASE,
        )
        relations = []
        for m in pattern.finditer(text):
            subj = m.group(1).strip()
            pred = m.group(2).strip().lower()
            obj = m.group(3).strip()
            if len(subj) > 1 and len(obj) > 1:
                relations.append(self.add_relation(subj, pred, obj, confidence=0.7, source=source))
        return relations

    # ── Query ──────────────────────────────────────────────────────────────────

    def query(self, term: str, max_results: int = 50) -> GraphQueryResult:
        """
        Query entities and relations involving a search term.

        Finds:
          - Entities whose name contains the term
          - Relations where subject OR object matches the term
        """
        term_like = f"%{term}%"
        entities: list[Entity] = []
        relations: list[Relation] = []

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM entities WHERE name LIKE ? ORDER BY created_at DESC LIMIT ?",
                (term_like, max_results),
            ).fetchall()
            for row in rows:
                entities.append(Entity(
                    name=row["name"],
                    entity_type=row["entity_type"],
                    properties=json.loads(row["properties"]),
                    created_at=row["created_at"],
                ))

            rows = conn.execute(
                """SELECT * FROM relations
                   WHERE subject LIKE ? OR object LIKE ?
                   ORDER BY confidence DESC, created_at DESC
                   LIMIT ?""",
                (term_like, term_like, max_results),
            ).fetchall()
            for row in rows:
                relations.append(Relation(
                    subject=row["subject"],
                    predicate=row["predicate"],
                    obj=row["object"],
                    confidence=row["confidence"],
                    source=row["source"],
                    created_at=row["created_at"],
                ))

        return GraphQueryResult(entities=entities, relations=relations, query=term)

    def get_neighbors(self, entity: str) -> list[Relation]:
        """Return all relations where entity is subject or object."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM relations WHERE subject=? OR object=? ORDER BY confidence DESC",
                (entity, entity),
            ).fetchall()
        return [Relation(subject=r["subject"], predicate=r["predicate"],
                         obj=r["object"], confidence=r["confidence"],
                         source=r["source"], created_at=r["created_at"]) for r in rows]

    def find_path(self, start: str, end: str, max_depth: int = 3) -> list[str]:
        """BFS shortest path between two entities via relations."""
        from collections import deque
        visited: set[str] = {start}
        queue: deque[list[str]] = deque([[start]])
        while queue:
            path = queue.popleft()
            if len(path) > max_depth + 1:
                break
            node = path[-1]
            for rel in self.get_neighbors(node):
                neighbor = rel.obj if rel.subject == node else rel.subject
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return []

    def entity_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]

    def relation_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

    def all_entities(self, entity_type: str | None = None) -> list[Entity]:
        with self._conn() as conn:
            if entity_type:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE entity_type=? ORDER BY name", (entity_type,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM entities ORDER BY name").fetchall()
        return [Entity(name=r["name"], entity_type=r["entity_type"],
                       properties=json.loads(r["properties"]), created_at=r["created_at"])
                for r in rows]


_kg: KnowledgeGraph | None = None


def get_knowledge_graph(db_path: Path | None = None) -> KnowledgeGraph:
    global _kg
    if _kg is None:
        _kg = KnowledgeGraph(db_path)
    return _kg


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        kg = KnowledgeGraph(db_path=Path(d) / "kg.db")

        # Add entities
        kg.add_entity("VECTOR", "ai_system", {"phase": "1", "owner": "Arghyadeep"})
        kg.add_entity("Python", "programming_language", {"version": "3.11"})
        kg.add_entity("Ollama", "inference_engine")
        kg.add_entity("LightRAG", "rag_system")

        # Add relations
        kg.add_relation("VECTOR", "built_with", "Python", confidence=1.0)
        kg.add_relation("VECTOR", "uses", "Ollama", confidence=1.0)
        kg.add_relation("VECTOR", "uses", "LightRAG", confidence=1.0)
        kg.add_relation("Python", "supports", "async/await", confidence=1.0)

        assert kg.entity_count() == 4
        assert kg.relation_count() == 4

        # Query
        result = kg.query("VECTOR")
        assert result.total >= 3
        assert any(r.predicate == "uses" for r in result.relations)

        # Neighbors
        neighbors = kg.get_neighbors("VECTOR")
        assert len(neighbors) == 3

        # Path finding
        kg.add_relation("Ollama", "enables", "LightRAG")
        path = kg.find_path("VECTOR", "LightRAG")
        assert "VECTOR" in path and "LightRAG" in path

        # Text extraction
        rels = kg.add_from_text("VECTOR uses Ollama and supports Python.")
        assert len(rels) >= 1

        # Markdown output
        md = result.to_markdown()
        assert "VECTOR" in md

    print("OK knowledge_graph.py — entities, relations, query, pathfinding verified")
