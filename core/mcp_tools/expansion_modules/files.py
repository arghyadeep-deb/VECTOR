from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.expansion_modules import is_protected_write_path, is_secret_path, resolve_in_root
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir


def add_file_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ file_* (10) — wired to districts/coding/coding_tools.py + stdlib â”€â”€â”€â”€â”€â”€â”€
    try:
        from districts.coding.coding_tools import read_code_file, write_code_file, apply_search_replace, grep_code

        def _confine(file_path: str, *, write: bool = False, read: bool = False):
            """Return (Path, None) or (None, error_json). CWE-22 safe: is_relative_to, not startswith."""
            resolved = resolve_in_root(ROOT, file_path)
            if resolved is None:
                return None, _safe_json({"error": "Path traversal denied"})
            if write and is_protected_write_path(ROOT, resolved):
                return None, _safe_json({"error": "Protected path denied"})
            if read and is_secret_path(ROOT, resolved):
                return None, _safe_json({"error": "Secret file read denied"})
            return resolved, None

        def _need_grant(name: str):
            # Same gate file_write/file_edit already get from coding_tools: only inside a
            # gateway-approved code_* execution. Copy/delete are writes too.
            try:
                from core.loop.permission_gateway import is_coding_grant_active
                ok = is_coding_grant_active()
            except Exception as exc:
                logger.warning("[VECTOR][mcp] coding-grant check unavailable for {}: {}", name, exc)
                ok = False
            if not ok:
                return _safe_json({"ok": False, "error": "coding grant not active - requires gateway-approved code_* execution"})
            return None

        @mcp.tool
        def file_read(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
            """Read a file within the repo root."""
            resolved, err = _confine(file_path, read=True)
            if err:
                return err
            try:
                content = read_code_file(str(resolved), start_line, end_line)
                if isinstance(content, dict) and "error" in content:
                    return _safe_json({"ok": False, "path": file_path, "error": content["error"]})
                return _safe_json({"path": file_path, "content": content})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_write(file_path: str, content: str) -> str:
            """Write content to a file (within repo root)."""
            resolved, err = _confine(file_path, write=True)
            if err:
                return err
            try:
                result = write_code_file(str(resolved), content, create_dirs=True)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_edit(file_path: str, search: str, replace: str) -> str:
            """Apply a search-replace edit to a file."""
            resolved, err = _confine(file_path, write=True)
            if err:
                return err
            try:
                result = apply_search_replace(str(resolved), search, replace)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_grep(pattern: str, path: str = ".") -> str:
            """Grep for a pattern in files."""
            # grep_code passes the pattern to `rg` without "--": a leading "-" would be an
            # rg option (e.g. --pre=<cmd> executes a command per file).
            if pattern.startswith("-"):
                return _safe_json({"error": "pattern must not start with '-'"})
            resolved, err = _confine(path or ".")
            if err:
                return err
            try:
                found = grep_code(pattern, str(resolved))
                matches = found.get("matches", []) if isinstance(found, dict) else list(found)
                matches = [m for m in matches if not (isinstance(m, dict) and is_secret_path(ROOT, _Path(m.get("file", ".env"))))]
                return _safe_json({"pattern": pattern, "results": matches[:50]})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_glob(pattern: str) -> str:
            """Glob for files matching a pattern."""
            # On Windows, Path("/etc/*").is_absolute() is False (no drive letter),
            # so a POSIX-rooted pattern slipped past this guard and hit pathlib's
            # glob() instead, which raises "Non-relative patterns are unsupported"
            # -- a confusing error, not a denial. Check for a leading separator too.
            if _Path(pattern).is_absolute() or pattern.startswith(("/", "\\")) or ".." in _Path(pattern).parts:
                return _safe_json({"error": "Path traversal denied"})
            base = ROOT.resolve()
            try:
                found = [p for p in base.glob(pattern) if p.resolve().is_relative_to(base) and not is_secret_path(ROOT, p)]
            except (NotImplementedError, ValueError) as e:
                return _safe_json({"error": f"invalid glob pattern: {e}"})
            matches = sorted(str(p.relative_to(base)) for p in found)
            return _safe_json({"pattern": pattern, "matches": matches[:100], "count": len(matches)})

        @mcp.tool
        def file_exists(file_path: str) -> str:
            """Check if a file exists."""
            resolved, err = _confine(file_path)
            if err:
                return err
            return _safe_json({"path": file_path, "exists": resolved.exists(), "is_file": resolved.is_file(), "is_dir": resolved.is_dir()})

        @mcp.tool
        def file_list_dir(path: str = ".") -> str:
            """List contents of a directory."""
            resolved, err = _confine(path)
            if err:
                return err
            try:
                entries = [{"name": p.name, "is_dir": p.is_dir(), "is_file": p.is_file()} for p in sorted(resolved.iterdir())]
            except OSError as e:
                return _safe_json({"error": str(e)})
            return _safe_json({"path": str(resolved.relative_to(ROOT.resolve())), "entries": entries})

        @mcp.tool
        def file_copy(src: str, dst: str) -> str:
            """Copy a file to a new path."""
            denied = _need_grant("file_copy")
            if denied:
                return denied
            src_resolved, err = _confine(src, read=True)
            if err:
                return err
            dst_resolved, err = _confine(dst, write=True)
            if err:
                return err
            try:
                _shutil.copy2(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_delete(file_path: str) -> str:
            """Delete a file (RED gate — requires confirmation)."""
            denied = _need_grant("file_delete")
            if denied:
                return denied
            resolved, err = _confine(file_path, write=True)
            if err:
                return err
            try:
                resolved.unlink()
                return _safe_json({"ok": True, "deleted": file_path})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_diff(file_path: str) -> str:
            """Show git diff for a file."""
            resolved, err = _confine(file_path, read=True)
            if err:
                return err
            try:
                result = _subprocess.run(["git", "diff", "--", file_path], capture_output=True, text=True, cwd=str(ROOT), timeout=10)
                if result.returncode != 0:
                    return _safe_json({"ok": False, "path": file_path, "error": result.stderr.strip()})
                return _safe_json({"path": file_path, "diff": result.stdout or "No changes"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] file tools unavailable: {e}")
        for n, d in [("file_read", "Read file"), ("file_write", "Write file"), ("file_edit", "Edit file"), ("file_grep", "Grep files"), ("file_glob", "Glob files"), ("file_exists", "File exists"), ("file_list_dir", "List directory"), ("file_copy", "Copy file"), ("file_delete", "Delete file"), ("file_diff", "File diff")]:
            _reg(mcp, n, d)
