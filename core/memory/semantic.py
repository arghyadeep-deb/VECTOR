"""V.E.C.T.O.R. SemanticMemory — persistent SQLite-backed concept store."""
import sys
import json

from loguru import logger
from datetime import datetime


class SemanticMemory:
    """Persistent concept knowledge store backed by the shared SQLite semantic_memory table."""

    def __init__(self):
        from core.memory.episodic import get_db_connection
        self._get_conn = get_db_connection
        logger.info("[VECTOR][semantic] SemanticMemory initialized (SQLite)")

    # ── Write ─────────────────────────────────────────────────────────────────

    async def add_concept(self, concept: str, definition: str,
                          tags: list[str] | None = None,
                          category: str = "concept",
                          confidence: float = 0.8) -> dict:
        """Store a concept. Upserts by key."""
        value = json.dumps({
            "definition": definition,
            "tags": tags or [],
        })
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO semantic_memory (key, value, category, confidence, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value, category=excluded.category,
                       confidence=excluded.confidence, updated_at=excluded.updated_at""",
                (concept, value, category, confidence, now),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[VECTOR][semantic] add_concept failed: {e}")
        logger.info(f"[VECTOR][semantic] stored: {concept}")
        return {"concept": concept, "definition": definition, "tags": tags or []}

    def store(self, key: str, value: str, category: str = "fact",
              confidence: float = 0.8) -> None:
        """Low-level key-value store into semantic_memory."""
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO semantic_memory (key, value, category, confidence, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value, confidence=excluded.confidence,
                       updated_at=excluded.updated_at""",
                (key, value, category, confidence, now),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[VECTOR][semantic] store failed: {e}")

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_concept(self, concept: str) -> dict | None:
        """Retrieve a concept by name."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT key, value, category, confidence FROM semantic_memory WHERE key = ?",
                (concept,),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row[1]) if row[1].startswith("{") else {"definition": row[1]}
            return {"concept": row[0], **payload, "category": row[2], "confidence": row[3]}
        except Exception as e:
            logger.error(f"[VECTOR][semantic] get_concept failed: {e}")
            return None

    def get(self, key: str) -> str | None:
        """Low-level get by key."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT value FROM semantic_memory WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"[VECTOR][semantic] get failed: {e}")
            return None

    def search_concepts(self, query: str, limit: int = 10) -> list[dict]:
        """Keyword search across all stored concepts."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                """SELECT key, value, category, confidence FROM semantic_memory
                   WHERE key LIKE ? OR value LIKE ?
                   ORDER BY confidence DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            results = []
            for row in rows:
                payload = json.loads(row[1]) if row[1].startswith("{") else {"definition": row[1]}
                results.append({"concept": row[0], **payload, "category": row[2], "confidence": row[3]})
            return results
        except Exception as e:
            logger.error(f"[VECTOR][semantic] search_concepts failed: {e}")
            return []

    def link_concepts(self, concept_a: str, concept_b: str, relation: str) -> dict:
        """Store a relation link between two concepts."""
        link_key = f"link:{concept_a}:{relation}:{concept_b}"
        self.store(link_key, json.dumps({"from": concept_a, "to": concept_b, "relation": relation}),
                   category="link", confidence=1.0)
        logger.info(f"[VECTOR][semantic] Linked {concept_a} --[{relation}]--> {concept_b}")
        return {"from": concept_a, "to": concept_b, "relation": relation}

    def get_related(self, concept: str) -> list[dict]:
        """Get all concepts linked to this one."""
        return self.search_concepts(f"link:{concept}:")


if __name__ == "__main__":
    import asyncio, sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        sm = SemanticMemory()
        await sm.add_concept("VECTOR", "Virtual Entity for Cognitive Tasks and Operational Reasoning", ["AI", "agent"])
        result = sm.get_concept("VECTOR")
        assert result is not None, "get_concept failed"
        results = sm.search_concepts("VECTOR")
        assert len(results) > 0, "search_concepts failed"
        print(f"OK semantic.py — concept stored and retrieved: {result['concept']}")

    asyncio.run(_smoke())
