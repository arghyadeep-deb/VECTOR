"""
Atomic multi-edit tool — apply multiple search/replace operations to one file
sequentially. Each edit is validated before writing; failures are reported per-edit
without aborting the entire batch.

Ported from the high-performance agent harness multiedit.rs.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger


@dataclass
class EditOperation:
    old_string: str
    new_string: str
    replace_all: bool = False


def _generate_diff_summary(old: str, new: str, max_lines: int = 30) -> str:
    """Compact diff: '42- old line' / '42+ new line', max 30 changed lines."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    output: list[str] = []
    lines_shown = 0
    old_idx = new_idx = 0

    import difflib
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            old_idx += i2 - i1
            new_idx += j2 - j1
            continue
        if lines_shown >= max_lines:
            output.append("...")
            break
        if tag in ("replace", "delete"):
            for line in old_lines[i1:i2]:
                stripped = line.strip()
                if stripped:
                    output.append(f"{old_idx + 1}- {stripped}")
                    lines_shown += 1
                old_idx += 1
        if tag in ("replace", "insert"):
            for line in new_lines[j1:j2]:
                stripped = line.strip()
                if stripped:
                    output.append(f"{new_idx + 1}+ {stripped}")
                    lines_shown += 1
                new_idx += 1

    return "\n".join(output)


def multiedit(file_path: str, edits: list[dict]) -> dict:
    """
    Apply multiple edits to one file atomically.

    Args:
        file_path: Path to file to edit.
        edits: List of dicts with keys:
               - old_string (str): text to find
               - new_string (str): replacement
               - replace_all (bool, optional): replace all occurrences (default False)

    Returns:
        {success, applied, failed, diff, file}
    """
    p = Path(file_path)
    if not p.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    ops = [EditOperation(**{k: v for k, v in e.items() if k in ("old_string", "new_string", "replace_all")})
           for e in edits]

    original = p.read_text(encoding="utf-8", errors="replace")
    content = original
    applied: list[str] = []
    failed: list[str] = []

    for i, op in enumerate(ops, 1):
        label = f"Edit {i}"

        if op.old_string == op.new_string:
            failed.append(f"{label}: old_string equals new_string")
            continue

        occurrences = content.count(op.old_string)
        if occurrences == 0:
            failed.append(f"{label}: old_string not found")
            continue

        if occurrences > 1 and not op.replace_all:
            failed.append(
                f"{label}: found {occurrences} occurrences — use replace_all=true or be more specific"
            )
            continue

        if op.replace_all:
            content = content.replace(op.old_string, op.new_string)
            applied.append(f"{label}: replaced {occurrences} occurrence(s)")
        else:
            content = content.replace(op.old_string, op.new_string, 1)
            applied.append(f"{label}: replaced 1 occurrence")

    if applied:
        p.write_text(content, encoding="utf-8")
        logger.info("[VECTOR][multiedit] wrote {} ({} edits applied)", file_path, len(applied))

    diff = _generate_diff_summary(original, content) if applied else ""

    return {
        "success": len(failed) == 0,
        "file": file_path,
        "applied": applied,
        "failed": failed,
        "total_applied": len(applied),
        "total_failed": len(failed),
        "diff": diff,
    }


if __name__ == "__main__":
    import tempfile, os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1\ny = 2\nz = 3\n")
        tmp = f.name

    result = multiedit(tmp, [
        {"old_string": "x = 1", "new_string": "x = 42"},
        {"old_string": "z = 3", "new_string": "z = 99"},
        {"old_string": "MISSING", "new_string": "nope"},
    ])
    assert result["total_applied"] == 2, result
    assert result["total_failed"] == 1, result
    assert "Edit 3: old_string not found" in result["failed"]
    content = Path(tmp).read_text()
    assert "x = 42" in content and "z = 99" in content
    os.unlink(tmp)
    print("OK multiedit.py")
