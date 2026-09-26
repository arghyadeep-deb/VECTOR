"""A LightRAG init failure must not be retried (and logged) on every call, and crash damage must be named (found 2026-09-27).

The live vault index has had 7 of its 11 files zero-filled since 2026-07-15 (a crash during write), so every memory query
re-attempted initialisation and logged the same opaque XML error -- 113 times in one backend session.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from loguru import logger

from core.memory import obsidian_sync as osync


def test_zero_filled_files_are_named_and_healthy_ones_are_not(tmp_path):
    (tmp_path / "graph.graphml").write_bytes(b"\x00" * 500)
    (tmp_path / "vdb.json").write_bytes(b"\x00" * 100)
    (tmp_path / "ok.json").write_text('{"a": 1}')
    (tmp_path / "empty.json").write_bytes(b"")
    assert osync._zero_filled_index_files(str(tmp_path)) == ["graph.graphml", "vdb.json"]
    assert osync._zero_filled_index_files(str(tmp_path / "missing")) == []


def test_a_failed_init_is_retried_at_most_once_per_window(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "lightrag", None)            # `from lightrag import ...` -> ImportError
    (tmp_path / "graph.graphml").write_bytes(b"\x00" * 64)
    sync = osync.ObsidianSync(vault_path=tmp_path)
    sync._cfg = {**sync._cfg, "lightrag_working_dir": str(tmp_path)}
    seen: list[str] = []
    sink = logger.add(lambda m: seen.append(str(m)), level="WARNING")
    try:
        for _ in range(5):
            asyncio.run(sync._init_rag())
    finally:
        logger.remove(sink)
    failures = [m for m in seen if "LightRAG init failed" in m]
    assert len(failures) == 1, failures
    assert "zero-filled" in failures[0] and "graph.graphml" in failures[0]

    monkeypatch.setattr(osync, "_RAG_RETRY_AFTER_S", 0.0)            # window elapsed -> it tries again
    seen.clear()
    sink = logger.add(lambda m: seen.append(str(m)), level="WARNING")
    try:
        asyncio.run(sync._init_rag())
    finally:
        logger.remove(sink)
    assert any("LightRAG init failed" in m for m in seen)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
