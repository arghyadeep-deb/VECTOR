"""
VECTOR Code Conductor — Precision File Editing Tools
Python port of codebuff/sdk/src/tools/change-file.ts

str_replace: the most important tool — find exact string in file, replace surgically.
This is how AI coding agents edit files precisely without rewriting entire files.

Port notes:
  - str_replace requires UNIQUE match (codebuff rule: be more specific if multiple)
  - apply_patch uses Python's difflib to apply unified diffs
  - read_files respects .gitignore patterns via gitpython

Usage:
    result = str_replace("core/config.py", "old_code", "new_code")
    result = write_file("new_module.py", "# content...")
    result = read_files(["core/config.py", "core/city/governor.py"])
"""
from __future__ import annotations

__all__ = [
    "apply_patch",
    "read_files",
    "str_replace",
    "write_file",
]


import difflib
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

_MAX_FILE_SIZE = 500_000  # 500KB — skip binary/large files
_GITIGNORE_CACHE: dict[str, list[str]] = {}


def _read_gitignore(root: str) -> list[str]:
    """Load .gitignore patterns from root directory."""
    if root in _GITIGNORE_CACHE:
        return _GITIGNORE_CACHE[root]
    patterns: list[str] = ["node_modules/", ".git/", "__pycache__/", "*.pyc", "*.pyo"]
    gi = Path(root) / ".gitignore"
    if gi.exists():
        for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    _GITIGNORE_CACHE[root] = patterns
    return patterns


def _is_ignored(file_path: str, root: str) -> bool:
    """Check if a file matches any .gitignore pattern."""
    import fnmatch
    patterns = _read_gitignore(root)
    rel = os.path.relpath(file_path, root)
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(os.path.basename(file_path), pat):
            return True
        # Directory patterns
        if pat.endswith("/") and (f"/{pat.rstrip('/')}" in rel.replace("\\", "/") or rel.replace("\\", "/").startswith(pat.rstrip("/"))):
            return True
    return False


# Files an LLM-produced edit must never touch, even inside the workspace: secrets and repository internals.
_PROTECTED_DIRS = {".git"}


def _contained_path(file_path: str, cwd: str | None) -> tuple[Path | None, str]:
    """Resolve `file_path` (relative to `cwd`) and refuse anything that leaves the workspace.

    2026-09-26 (V1 handoff, coding workflow): these helpers resolved the path but never checked where it ended up, and
    their input comes from an LLM plan -- so `FILE: ../../.env` or an absolute path wrote anywhere on the machine, with
    no permission-gateway check on the write itself. When a workspace (`cwd`) is given, the resolved path must be inside
    it (symlinks and `..` are resolved first) and must not be a secrets file (.env*) or inside `.git`.
    With no `cwd` there is no workspace to enforce, so behaviour is unchanged.
    Returns (path, "") on success or (None, reason).
    """
    path = Path(file_path)
    if cwd and not path.is_absolute():
        path = Path(cwd) / path
    path = path.resolve()
    if cwd:
        root = Path(cwd).resolve()
        try:
            rel = path.relative_to(root)
        except ValueError:
            return None, f"Refusing to edit {file_path}: it resolves outside the workspace ({root})."
        if rel.name.startswith(".env") or any(part in _PROTECTED_DIRS for part in rel.parts):
            return None, f"Refusing to edit {file_path}: protected path (secrets / repository internals)."
    return path, ""


# ── str_replace ───────────────────────────────────────────────────────────────

def str_replace(
    file_path: str,
    old_str: str,
    new_str: str,
    cwd: str | None = None,
) -> dict:
    """
    Replace old_str with new_str in file_path. Surgical, exact-match edit.

    Rules (ported from codebuff):
    - old_str must appear EXACTLY ONCE in the file
    - If multiple matches → error (make old_str more specific)
    - If no match → error (check whitespace/indentation)
    - Returns unified diff of the change

    Returns:
        {status: "ok", file, message, diff}  on success
        {status: "error", message}            on failure
    """
    try:
        path, refusal = _contained_path(file_path, cwd)
        if path is None:
            return {"status": "error", "message": refusal}

        if not path.exists():
            return {"status": "error", "message": f"File not found: {file_path}"}

        original = path.read_text(encoding="utf-8", errors="replace")
        count = original.count(old_str)

        if count == 0:
            # Check for common issues
            stripped_count = original.count(old_str.strip())
            hint = " (found with stripped whitespace — check indentation)" if stripped_count else ""
            return {
                "status": "error",
                "message": f"old_str not found in {file_path}{hint}. Make sure it exactly matches the file content.",
            }

        if count > 1:
            return {
                "status": "error",
                "message": f"old_str found {count} times in {file_path}. Make it more specific by including more surrounding context.",
            }

        new_content = original.replace(old_str, new_str, 1)

        # Generate unified diff
        original_lines = original.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            original_lines, new_lines,
            fromfile=f"a/{file_path}", tofile=f"b/{file_path}",
            n=3,
        ))

        path.write_text(new_content, encoding="utf-8")
        logger.debug("[VECTOR][str_replace] edited {} — {}", file_path, diff[:100])

        return {
            "status": "ok",
            "file": str(path),
            "message": "str_replace applied successfully.",
            "diff": diff,
        }

    except PermissionError:
        return {"status": "error", "message": f"Permission denied writing to {file_path}"}
    except Exception as e:
        return {"status": "error", "message": f"str_replace failed: {e}"}


# ── write_file ────────────────────────────────────────────────────────────────

def write_file(file_path: str, content: str, cwd: str | None = None) -> dict:
    """
    Write a new file or fully overwrite an existing one.

    Returns:
        {status: "ok", file, message}  on success
        {status: "error", message}     on failure
    """
    try:
        path, refusal = _contained_path(file_path, cwd)
        if path is None:
            return {"status": "error", "message": refusal}

        created = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        msg = "Created file successfully." if created else "Overwrote file successfully."
        logger.debug("[VECTOR][str_replace] write {} — {} bytes", file_path, len(content))
        return {"status": "ok", "file": str(path), "message": msg, "created": created}

    except PermissionError:
        return {"status": "error", "message": f"Permission denied writing to {file_path}"}
    except Exception as e:
        return {"status": "error", "message": f"write_file failed: {e}"}


# ── apply_patch ───────────────────────────────────────────────────────────────

def apply_patch(file_path: str, patch: str, cwd: str | None = None) -> dict:
    """
    Apply a unified diff patch to a file.
    Uses Python's difflib patch algorithm.
    """
    _, refusal = _contained_path(file_path, cwd)
    if refusal:
        return {"status": "error", "message": refusal}
    try:
        import patch as patch_lib  # python-patch package
        pset = patch_lib.fromstring(patch.encode())
        success = pset.apply(root=Path(cwd or "."))
        if success:
            return {"status": "ok", "file": file_path, "message": "Patch applied successfully."}
        return {"status": "error", "message": "Patch failed to apply (check context lines match file content)"}
    except ImportError:
        # Fallback: simple line-based patch without python-patch package
        return _apply_patch_simple(file_path, patch, cwd)
    except Exception as e:
        return {"status": "error", "message": f"apply_patch failed: {e}"}


def _apply_patch_simple(file_path: str, patch: str, cwd: str | None) -> dict:
    """Simple unified diff patch application without external deps."""
    path = Path(file_path)
    if cwd and not path.is_absolute():
        path = Path(cwd) / path
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    original = path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    result_lines = list(lines)
    patch_lines = patch.splitlines()

    i = 0
    offset = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            # Parse hunk header: @@ -a,b +c,d @@
            import re
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                orig_start = int(m.group(1)) - 1 + offset
                hunk_lines = []
                i += 1
                while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                    hunk_lines.append(patch_lines[i])
                    i += 1
                # Apply hunk
                removals = [l[1:] for l in hunk_lines if l.startswith("-")]
                additions = [l[1:] for l in hunk_lines if l.startswith("+")]
                # Find and replace
                pos = orig_start
                removed = 0
                for r_line in removals:
                    if pos < len(result_lines) and result_lines[pos] == r_line:
                        result_lines.pop(pos)
                        removed += 1
                    else:
                        pos += 1
                for a_idx, a_line in enumerate(additions):
                    result_lines.insert(pos + a_idx, a_line)
                offset += len(additions) - len(removals)
                continue
        i += 1

    path.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    return {"status": "ok", "file": file_path, "message": "Patch applied (simple mode)."}


# ── read_files ────────────────────────────────────────────────────────────────

def read_files(
    paths: list[str],
    cwd: str | None = None,
    max_chars_per_file: int = 50_000,
    max_total_chars: int = 200_000,
) -> dict:
    """
    Read multiple files. Respects .gitignore. Truncates large files.

    Returns:
        {files: [{path, content, truncated}], total_chars, skipped}
    """
    root = cwd or os.getcwd()
    result: list[dict] = []
    total = 0
    skipped: list[str] = []

    for file_path in paths:
        # 2026-10-02 (Phase 3 audit): unlike str_replace()/write_file(), this
        # never called _contained_path() -- an absolute path (or a relative
        # one escaping via "..") was read with NO confinement at all, even
        # when a cwd workspace was given. Same real-world input source as
        # the 2026-09-26 str_replace()/write_file() fix (an LLM plan), same
        # fix reused for consistency.
        p, refusal = _contained_path(file_path, cwd)
        if p is None:
            skipped.append(f"{file_path} ({refusal})")
            continue

        if not p.exists():
            skipped.append(f"{file_path} (not found)")
            continue

        if _is_ignored(str(p), root):
            skipped.append(f"{file_path} (gitignored)")
            continue

        if p.stat().st_size > _MAX_FILE_SIZE:
            skipped.append(f"{file_path} (too large: {p.stat().st_size // 1024}KB)")
            continue

        if total >= max_total_chars:
            skipped.append(f"{file_path} (total limit reached)")
            continue

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, IsADirectoryError) as e:
            skipped.append(f"{file_path} ({e})")
            continue

        truncated = False
        if len(content) > max_chars_per_file:
            content = content[:max_chars_per_file] + f"\n... [truncated at {max_chars_per_file} chars]"
            truncated = True

        remaining = max_total_chars - total
        if len(content) > remaining:
            content = content[:remaining] + "\n... [total limit reached]"
            truncated = True

        total += len(content)
        result.append({"path": file_path, "content": content, "truncated": truncated})

    return {
        "files": result,
        "total_chars": total,
        "skipped": skipped,
    }


if __name__ == "__main__":
    import sys, tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        # Test write_file
        test_file = os.path.join(tmp, "test.py")
        r = write_file(test_file, "def hello():\n    return 'world'\n")
        assert r["status"] == "ok", r
        assert r["created"] is True

        # Test str_replace
        r = str_replace(test_file, "return 'world'", "return 'VECTOR'")
        assert r["status"] == "ok", r
        assert "diff" in r
        content = Path(test_file).read_text()
        assert "VECTOR" in content

        # Test str_replace — no match
        r = str_replace(test_file, "NONEXISTENT", "x")
        assert r["status"] == "error"
        assert "not found" in r["message"]

        # Test str_replace — multiple matches
        write_file(test_file, "a = 1\na = 1\n")
        r = str_replace(test_file, "a = 1", "a = 2")
        assert r["status"] == "error"
        assert "2 times" in r["message"]

        # Test read_files
        write_file(test_file, "x = 42\n")
        r = read_files([test_file])
        assert r["files"][0]["content"].strip() == "x = 42"

    print("OK str_replace.py — str_replace, write_file, apply_patch, read_files all work")
