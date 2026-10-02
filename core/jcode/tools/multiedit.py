"""
Atomic multi-edit tool — apply multiple search/replace operations to one file
sequentially. Each edit is validated before writing; failures are reported per-edit
without aborting the entire batch.

Ported from the high-performance agent harness multiedit.rs.
"""
from __future__ import annotations

__all__ = [
    "EditOperation",
    "multiedit",
]


from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# file_path is caller-supplied and reaches real file I/O directly -- same
# confinement anchor used by this package's sibling apply_patch.py and
# 10+ districts/coding/ files this cycle (resolve + is_relative_to the
# real repo root, not a configurable/CWD-relative base).
_ROOT = Path(__file__).resolve().parents[3]


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

    file_path reaches real file I/O directly with no confinement check --
    the one real caller (districts/coding/coding_tools.py's
    multiedit_file()) only gates the ACTION (an active coding grant), not
    which path a malformed/injected call could name. Confined to the real
    repo root, same pattern as this package's sibling apply_patch.py and
    10+ districts/coding/ files this cycle.
    """
    p = Path(file_path).resolve()
    if not p.is_relative_to(_ROOT):
        return {"success": False, "error": f"path outside repo: {file_path!r}"}
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

    # A system-tempdir path is outside the repo root and correctly rejected
    # by the confinement check above -- use an in-repo tmp dir instead, same
    # fix applied to this cycle's other self-tests that unknowingly relied
    # on an out-of-scope path (e.g. core/code_conductor/str_replace.py).
    tmpdir = _ROOT / "test_tmp" / "multiedit_selftest"
    tmpdir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmpdir / "sample.py"
    tmp_path.write_text("x = 1\ny = 2\nz = 3\n")
    tmp = str(tmp_path)

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
    tmpdir.rmdir()
    print("OK multiedit.py")
