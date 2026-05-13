# Ported from GitHub/NousResearch_hermes-agent/repo/tools/file_tools.py
"""File manipulation tools: read_file, write_file, patch, search_files."""
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from .binary_extensions import has_binary_extension
from .file_safety import is_write_denied, is_safe_to_read, _BLOCKED_DEVICE_PATHS
from .path_security import has_traversal_component
from .registry import registry

_DEFAULT_MAX_READ_CHARS = 100_000

_SENSITIVE_PATH_PREFIXES = ("/etc/", "/boot/", "/usr/lib/systemd/", "/private/etc/", "/private/var/")
_SENSITIVE_EXACT_PATHS = {"/var/run/docker.sock", "/run/docker.sock"}


def _resolve(filepath: str) -> Path:
    p = Path(filepath).expanduser()
    if not p.is_absolute():
        p = Path(os.environ.get("TERMINAL_CWD", os.getcwd())) / p
    return p.resolve()


def _is_blocked_device(filepath: str) -> bool:
    normalized = os.path.expanduser(filepath)
    return normalized in _BLOCKED_DEVICE_PATHS


# ── read_file ─────────────────────────────────────────────────────────────────

def read_file(
    path: str,
    offset: int = 0,
    limit: Optional[int] = None,
    encoding: str = "utf-8",
) -> str:
    """Read a file and return its contents."""
    if _is_blocked_device(path):
        return json.dumps({"error": f"Blocked device path: {path}"})

    if not is_safe_to_read(path):
        return json.dumps({"error": f"Access denied: {path} is an internal cache file."})

    if has_binary_extension(path):
        return json.dumps({"error": f"Binary file: {path}. Use a specialized tool."})

    try:
        resolved = _resolve(path)
    except Exception as e:
        return json.dumps({"error": f"Invalid path: {e}"})

    if not resolved.exists():
        return json.dumps({"error": f"File not found: {path}"})

    if not resolved.is_file():
        return json.dumps({"error": f"Not a file: {path}"})

    try:
        content = resolved.read_text(encoding=encoding, errors="replace")
    except Exception as e:
        return json.dumps({"error": f"Read error: {e}"})

    lines = content.splitlines(keepends=True)
    if offset:
        lines = lines[offset:]
    if limit is not None:
        lines = lines[:limit]

    result = "".join(lines)
    if len(result) > _DEFAULT_MAX_READ_CHARS:
        result = result[:_DEFAULT_MAX_READ_CHARS] + f"\n[...truncated at {_DEFAULT_MAX_READ_CHARS} chars]"

    return result


# ── write_file ────────────────────────────────────────────────────────────────

def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
    """Write content to a file, creating parent directories as needed."""
    if is_write_denied(path):
        return json.dumps({"error": f"Write denied: {path} is a protected path."})

    for prefix in _SENSITIVE_PATH_PREFIXES:
        if path.startswith(prefix):
            return json.dumps({"error": f"Refusing to write to sensitive system path: {path}"})

    try:
        resolved = _resolve(path)
    except Exception as e:
        return json.dumps({"error": f"Invalid path: {e}"})

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding=encoding)
        return json.dumps({"success": True, "path": str(resolved), "bytes": len(content.encode(encoding))})
    except PermissionError as e:
        return json.dumps({"error": f"Permission denied: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Write error: {e}"})


# ── patch ─────────────────────────────────────────────────────────────────────

def patch(path: str, old_str: str, new_str: str, encoding: str = "utf-8") -> str:
    """Replace old_str with new_str in a file (exact string match)."""
    if is_write_denied(path):
        return json.dumps({"error": f"Write denied: {path}"})

    try:
        resolved = _resolve(path)
    except Exception as e:
        return json.dumps({"error": f"Invalid path: {e}"})

    if not resolved.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        content = resolved.read_text(encoding=encoding, errors="replace")
    except Exception as e:
        return json.dumps({"error": f"Read error: {e}"})

    if old_str not in content:
        # Show context around where it might be
        return json.dumps({"error": f"String not found in {path}. The file may have changed."})

    count = content.count(old_str)
    if count > 1:
        return json.dumps({"error": f"Found {count} occurrences of the string. Provide more context to make it unique."})

    new_content = content.replace(old_str, new_str, 1)
    try:
        resolved.write_text(new_content, encoding=encoding)
        return json.dumps({"success": True, "path": str(resolved)})
    except Exception as e:
        return json.dumps({"error": f"Write error: {e}"})


# ── search_files ──────────────────────────────────────────────────────────────

def search_files(
    path: str = ".",
    pattern: str = "",
    file_pattern: str = "*",
    max_results: int = 50,
) -> str:
    """Search for files matching a pattern, or search file contents with regex."""
    try:
        root = _resolve(path)
    except Exception as e:
        return json.dumps({"error": f"Invalid path: {e}"})

    if not root.exists():
        return json.dumps({"error": f"Path not found: {path}"})

    results = []

    if not pattern:
        # File name search
        for p in root.rglob(file_pattern):
            if p.is_file() and not has_binary_extension(str(p)):
                results.append(str(p.relative_to(root)))
                if len(results) >= max_results:
                    break
        return json.dumps({"files": results, "count": len(results)})

    # Content search
    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as e:
        return json.dumps({"error": f"Invalid regex: {e}"})

    matches = []
    for p in root.rglob(file_pattern):
        if not p.is_file() or has_binary_extension(str(p)):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    matches.append({
                        "file": str(p.relative_to(root)),
                        "line": i,
                        "content": line.rstrip(),
                    })
                    if len(matches) >= max_results:
                        break
        except Exception:
            continue
        if len(matches) >= max_results:
            break

    return json.dumps({"matches": matches, "count": len(matches)})


# ── Register tools ────────────────────────────────────────────────────────────

registry.register(
    name="read_file",
    handler=read_file,
    schema={
        "description": "Read a file and return its contents. Use offset/limit for large files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "offset": {"type": "integer", "description": "Line offset to start reading from"},
                "limit": {"type": "integer", "description": "Max lines to read"},
            },
            "required": ["path"],
        },
    },
    toolset="coding",
    risk_level="safe",
    emoji="📖",
)

registry.register(
    name="write_file",
    handler=write_file,
    schema={
        "description": "Write content to a file, creating parent directories as needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    toolset="coding",
    risk_level="low",
    emoji="✏️",
)

registry.register(
    name="patch",
    handler=patch,
    schema={
        "description": "Replace old_str with new_str in a file (exact string match, must be unique).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to patch"},
                "old_str": {"type": "string", "description": "Exact string to replace"},
                "new_str": {"type": "string", "description": "Replacement string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    toolset="coding",
    risk_level="medium",
    emoji="🔧",
)

registry.register(
    name="search_files",
    handler=search_files,
    schema={
        "description": "Search for files by name or search file contents with regex.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Regex pattern to search in file contents (empty = filename search)"},
                "file_pattern": {"type": "string", "description": "Glob pattern for filenames (e.g. '*.py')"},
                "max_results": {"type": "integer", "description": "Max results to return"},
            },
        },
    },
    toolset="coding",
    risk_level="safe",
    emoji="🔍",
)
