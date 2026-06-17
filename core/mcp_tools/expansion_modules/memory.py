from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_memory_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ memory_* (12) — wired to core/memory/ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.memory.episodic import EpisodicMemory, get_db_connection, get_temp_cursor
        from core.memory.semantic import SemanticMemory
        from core.memory.reasoning_memory import ReasoningMemory

        _epi = None
        _sem = None
        _rm = None

        # These classes bind the shared singleton connection internally via
        # get_db_connection(); they take no positional connection argument.
        def _get_epi():
            nonlocal _epi
            if _epi is None:
                _epi = EpisodicMemory()
            return _epi

        def _get_sem():
            nonlocal _sem
            if _sem is None:
                _sem = SemanticMemory()
            return _sem

        def _get_rm():
            nonlocal _rm
            if _rm is None:
                _rm = ReasoningMemory()
            return _rm

        @mcp.tool
        def memory_stats() -> str:
            """Get memory index statistics."""
            mem = _get_epi()
            return _safe_json(mem.get_stats() if hasattr(mem, "get_stats") else {"status": "ok"})

        @mcp.tool
        def memory_semantic_search(query: str, limit: int = 5) -> str:
            """Semantic search over stored concepts."""
            mem = _get_sem()
            results = mem.search_concepts(query, limit=limit) if hasattr(mem, "search_concepts") else []
            return _safe_json({"query": query, "results": results})

        @mcp.tool
        def memory_pattern_save(task: str, plan: str, outcome: str, reward: float = 0.0) -> str:
            """Save a task→plan→outcome reasoning pattern."""
            try:
                from core.memory.reasoning_memory import get_reasoning_memory
                rm = get_reasoning_memory()
                rm.store_chain(task, plan, outcome, reward=reward)
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_pattern_recall(task: str, limit: int = 3) -> str:
            """Recall past reasoning patterns similar to a task."""
            try:
                from core.memory.reasoning_memory import get_reasoning_memory
                rm = get_reasoning_memory()
                patterns = rm.inject_past_reasoning(task, limit=limit) if hasattr(rm, "inject_past_reasoning") else []
                return _safe_json({"task": task, "patterns": patterns})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_recent(limit: int = 10) -> str:
            """Get most recently added memory entries."""
            mem = _get_epi()
            try:
                cur = mem.get_temp_cursor() if hasattr(mem, "get_temp_cursor") else None
                if cur:
                    cur.execute("SELECT * FROM episodic_memory ORDER BY timestamp DESC LIMIT ?", (limit,))
                    rows = cur.fetchall()
                    return _safe_json({"count": len(rows), "entries": rows})
                return _safe_json({"status": "no cursor available"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_categories() -> str:
            """List all insight categories in semantic memory."""
            mem = _get_sem()
            try:
                cur = mem.get_temp_cursor() if hasattr(mem, "get_temp_cursor") else None
                if cur:
                    cur.execute("SELECT DISTINCT category FROM semantic_memory")
                    rows = [r[0] for r in cur.fetchall()]
                    return _safe_json({"categories": rows})
                return _safe_json({"categories": []})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_clear(confirm: str = "") -> str:
            """Delete ALL entries from episodic memory. Destructive and
            irreversible — requires confirm="CONFIRM_CLEAR_MEMORY"."""
            if confirm != _MEMORY_CLEAR_CONFIRM:
                return _safe_json({
                    "error": "confirmation required",
                    "message": f'memory_clear deletes all episodic memory; call again with confirm="{_MEMORY_CLEAR_CONFIRM}"',
                    "cleared": False,
                })
            mem = _get_epi()
            try:
                from core.memory.episodic import get_temp_cursor
                with get_temp_cursor() as cur:
                    cur.execute("DELETE FROM episodic_memory")
                return _safe_json({"ok": True, "cleared": True, "message": "Episodic memory cleared"})
            except Exception as e:
                return _safe_json({"error": str(e), "cleared": False})

        @mcp.tool
        def memory_export(path: str = "") -> str:
            """Export episodic memory to JSON. Path is confined to the approved
            memory_exports directory under the runtime data root."""
            out_path, err = _resolve_memory_path(path, default_name="memory_export.json")
            if err:
                return _safe_json({"error": err})
            try:
                from core.memory.episodic import get_temp_cursor
                with get_temp_cursor() as cur:
                    cur.execute("SELECT * FROM episodic_memory ORDER BY timestamp DESC")
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                with open(out_path, "w", encoding="utf-8") as f:
                    _json.dump(rows, f, default=str)
                return _safe_json({"ok": True, "path": str(out_path), "count": len(rows)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_import(path: str) -> str:
            """Import memory entries from a JSON file inside the approved
            memory_exports directory under the runtime data root."""
            in_path, err = _resolve_memory_path(path, default_name="memory_export.json")
            if err:
                return _safe_json({"error": err})
            if not in_path.is_file():
                return _safe_json({"error": f"file not found in approved directory: {in_path}"})
            mem = _get_epi()
            try:
                with open(in_path, encoding="utf-8") as f:
                    data = _json.load(f)
                count = 0
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    content = entry.get("content")
                    if content is None:
                        continue
                    tags = entry.get("tags")
                    if isinstance(tags, str):
                        try:
                            tags = _json.loads(tags)
                        except Exception:
                            tags = [tags] if tags else None
                    mem.store(
                        event_type=entry.get("event_type", "imported"),
                        content=content,
                        tags=tags,
                        source=entry.get("source", "memory_import"),
                    )
                    count += 1
                return _safe_json({"ok": True, "imported": count})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_bridge_sync() -> str:
            """Trigger Obsidian vault sync."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                return _safe_json({"status": "sync_triggered", "vault": str(sync.vault_path) if hasattr(sync, "vault_path") else "unknown"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_faiss_add(text: str) -> str:
            """FAISS not available — VECTOR uses SQLite-based semantic memory. Use memory_semantic_search instead."""
            return _safe_json({"status": "not_available", "alternative": "memory_semantic_search"})

        @mcp.tool
        def memory_faiss_search(query: str) -> str:
            """FAISS not available — VECTOR uses SQLite-based semantic memory. Use memory_semantic_search instead."""
            return _safe_json({"status": "not_available", "alternative": "memory_semantic_search"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] memory tools unavailable: {e}")
        for n, d in [("memory_stats", "Memory stats"), ("memory_semantic_search", "Semantic search"), ("memory_pattern_save", "Save pattern"), ("memory_pattern_recall", "Recall pattern"), ("memory_recent", "Recent entries"), ("memory_categories", "List categories"), ("memory_clear", "Clear memory"), ("memory_export", "Export memory"), ("memory_import", "Import memory"), ("memory_bridge_sync", "Bridge sync"), ("memory_faiss_add", "FAISS add (unavailable)"), ("memory_faiss_search", "FAISS search (unavailable)")]:
            _reg(mcp, n, d)
