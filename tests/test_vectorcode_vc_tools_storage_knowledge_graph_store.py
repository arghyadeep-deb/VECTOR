"""Regression test: KnowledgeGraphMemory.store() must not let caller-supplied
metadata override the real content.

store()'s properties dict was built as
``{"content": content, **(meta.get("properties", {}))}`` -- later keys in a
dict literal win, so a metadata dict containing its own "properties.content"
key silently replaced the actual content argument. This is reachable from
server/api_routes.py's HTTP endpoint, which passes the request body's
metadata straight through: ``backend.store(req.content, metadata=req.metadata or {})``.
"""

from __future__ import annotations

from pathlib import Path

from vectorcode.src.vc_tools.storage.knowledge_graph import KnowledgeGraphMemory


def test_store_content_wins_over_metadata_properties_content(tmp_path: Path) -> None:
    kg = KnowledgeGraphMemory(db_path=tmp_path / "kg.db")
    try:
        kg.store(
            "doc-1",
            "the real content",
            metadata={"properties": {"content": "attacker-controlled override"}},
        )
        stored = kg.retrieve("doc-1")
        assert stored == "the real content"
    finally:
        kg.close()


def test_store_preserves_other_metadata_properties(tmp_path: Path) -> None:
    kg = KnowledgeGraphMemory(db_path=tmp_path / "kg2.db")
    try:
        kg.store(
            "doc-2",
            "hello",
            metadata={"properties": {"author": "alice"}},
        )
        entity = kg.get_entity("doc-2")
        assert entity is not None
        assert entity.properties["content"] == "hello"
        assert entity.properties["author"] == "alice"
    finally:
        kg.close()
