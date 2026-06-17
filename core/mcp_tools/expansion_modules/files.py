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


def add_file_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ file_* (10) — wired to districts/coding/coding_tools.py + stdlib â”€â”€â”€â”€â”€â”€â”€
    try:
        from districts.coding.coding_tools import read_code_file, write_code_file, apply_search_replace, grep_code

        @mcp.tool
        def file_read(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
            """Read a file within the repo root."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                content = read_code_file(str(resolved), start_line, end_line)
                return _safe_json({"path": file_path, "content": content})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_write(file_path: str, content: str) -> str:
            """Write content to a file (within repo root)."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                result = write_code_file(str(resolved), content, create_dirs=True)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_edit(file_path: str, search: str, replace: str) -> str:
            """Apply a search-replace edit to a file."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                result = apply_search_replace(str(resolved), search, replace)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_grep(pattern: str, path: str = ".") -> str:
            """Grep for a pattern in files."""
            try:
                results = grep_code(pattern, path or str(ROOT))
                return _safe_json({"pattern": pattern, "results": results[:50]})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_glob(pattern: str) -> str:
            """Glob for files matching a pattern."""
            matches = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern))
            return _safe_json({"pattern": pattern, "matches": matches[:100], "count": len(matches)})

        @mcp.tool
        def file_exists(file_path: str) -> str:
            """Check if a file exists."""
            resolved = (ROOT / file_path).resolve()
            return _safe_json({"path": file_path, "exists": resolved.exists(), "is_file": resolved.is_file(), "is_dir": resolved.is_dir()})

        @mcp.tool
        def file_list_dir(path: str = ".") -> str:
            """List contents of a directory."""
            resolved = (ROOT / path).resolve() if path != "." else ROOT.resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            entries = []
            for p in sorted(resolved.iterdir()):
                entries.append({"name": p.name, "is_dir": p.is_dir(), "is_file": p.is_file()})
            return _safe_json({"path": str(resolved.relative_to(ROOT)), "entries": entries})

        @mcp.tool
        def file_copy(src: str, dst: str) -> str:
            """Copy a file to a new path."""
            src_resolved = (ROOT / src).resolve()
            dst_resolved = (ROOT / dst).resolve()
            if not str(src_resolved).startswith(str(ROOT.resolve())) or not str(dst_resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                _shutil.copy2(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_delete(file_path: str) -> str:
            """Delete a file (RED gate — requires confirmation)."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                resolved.unlink()
                return _safe_json({"ok": True, "deleted": file_path})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_diff(file_path: str) -> str:
            """Show git diff for a file."""
            try:
                result = _subprocess.run(["git", "diff", "--", file_path], capture_output=True, text=True, cwd=str(ROOT), timeout=10)
                return _safe_json({"path": file_path, "diff": result.stdout or "No changes"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] file tools unavailable: {e}")
        for n, d in [("file_read", "Read file"), ("file_write", "Write file"), ("file_edit", "Edit file"), ("file_grep", "Grep files"), ("file_glob", "Glob files"), ("file_exists", "File exists"), ("file_list_dir", "List directory"), ("file_copy", "Copy file"), ("file_delete", "Delete file"), ("file_diff", "File diff")]:
            _reg(mcp, n, d)
