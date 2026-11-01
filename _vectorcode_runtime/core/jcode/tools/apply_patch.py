"""
Codex-style patch applicator.

Supports the *** Begin Patch / *** End Patch format used by OpenAI Codex and
compatible agents. Operations: Add File, Delete File, Update File (with Move to).

Ported from the high-performance agent harness apply_patch.rs.

Patch format example:
    *** Begin Patch
    *** Add File: src/new_module.py
    +def hello():
    +    pass
    *** Update File: src/existing.py
    @@ some context line
     unchanged context
    -old line
    +new line
    *** Delete File: src/deprecated.py
    *** End Patch
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from loguru import logger


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class _UpdateChunk:
    change_context: str | None
    old_lines: list[str]
    new_lines: list[str]
    is_end_of_file: bool = False


@dataclass
class _AddFile:
    path: str
    contents: str


@dataclass
class _DeleteFile:
    path: str


@dataclass
class _UpdateFile:
    path: str
    move_to: str | None
    chunks: list[_UpdateChunk]


_Hunk = Union[_AddFile, _DeleteFile, _UpdateFile]


# ── Parser ─────────────────────────────────────────────────────────────────────

def _parse_patch(text: str) -> list[_Hunk]:
    lines = text.splitlines()
    start = next(
        (i for i, l in enumerate(lines) if l.strip() == "*** Begin Patch"), None
    )
    if start is None:
        raise ValueError("Patch must contain '*** Begin Patch'")

    hunks: list[_Hunk] = []
    i = start + 1

    while i < len(lines):
        line = lines[i].rstrip()

        if line.strip() == "*** End Patch":
            break

        if line.startswith("*** Add File: "):
            path = line[len("*** Add File: "):].strip()
            i += 1
            contents = ""
            while i < len(lines):
                cl = lines[i]
                if cl.startswith("*** "):
                    break
                if cl.startswith("+"):
                    contents += cl[1:] + "\n"
                i += 1
            hunks.append(_AddFile(path=path, contents=contents))
            continue

        if line.startswith("*** Delete File: "):
            path = line[len("*** Delete File: "):].strip()
            hunks.append(_DeleteFile(path=path))
            i += 1
            continue

        if line.startswith("*** Update File: "):
            path = line[len("*** Update File: "):].strip()
            i += 1

            move_to = None
            if i < len(lines) and lines[i].rstrip().startswith("*** Move to: "):
                move_to = lines[i].rstrip()[len("*** Move to: "):].strip()
                i += 1

            chunks: list[_UpdateChunk] = []
            is_first = True

            while i < len(lines):
                cl = lines[i].rstrip()
                if cl.startswith("*** ") and cl != "*** End of File":
                    break
                if not cl and not cl.startswith((" ", "+", "-")):
                    i += 1
                    continue

                if cl == "@@":
                    ctx = None
                    i += 1
                elif cl.startswith("@@ "):
                    ctx = cl[3:]
                    i += 1
                elif is_first:
                    ctx = None
                else:
                    break

                old_l: list[str] = []
                new_l: list[str] = []
                is_eof = False
                had_lines = False

                while i < len(lines):
                    dl = lines[i]
                    if dl == "*** End of File":
                        is_eof = True
                        i += 1
                        break
                    if dl.startswith("*** ") or dl.startswith("@@"):
                        break
                    if dl.startswith(" "):
                        old_l.append(dl[1:])
                        new_l.append(dl[1:])
                        had_lines = True
                    elif dl.startswith("+"):
                        new_l.append(dl[1:])
                        had_lines = True
                    elif dl.startswith("-"):
                        old_l.append(dl[1:])
                        had_lines = True
                    elif dl == "":
                        old_l.append("")
                        new_l.append("")
                        had_lines = True
                    else:
                        if had_lines:
                            break
                        i += 1
                        continue
                    i += 1

                if had_lines or ctx is not None:
                    chunks.append(_UpdateChunk(
                        change_context=ctx,
                        old_lines=old_l,
                        new_lines=new_l,
                        is_end_of_file=is_eof,
                    ))
                is_first = False

            if not chunks:
                raise ValueError(f"Update hunk for '{path}' has no changes")
            hunks.append(_UpdateFile(path=path, move_to=move_to, chunks=chunks))
            continue

        i += 1

    if not hunks:
        raise ValueError("No valid patch directives found")
    return hunks


# ── Chunk application ──────────────────────────────────────────────────────────

def _seek_sequence(lines: list[str], pattern: list[str], start: int, eof: bool) -> int | None:
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None

    search_start = len(lines) - len(pattern) if (eof and len(lines) >= len(pattern)) else start

    for i in range(search_start, len(lines) - len(pattern) + 1):
        if lines[i:i + len(pattern)] == pattern:
            return i

    for i in range(search_start, len(lines) - len(pattern) + 1):
        if all(lines[i + j].rstrip() == pattern[j].rstrip() for j in range(len(pattern))):
            return i

    for i in range(search_start, len(lines) - len(pattern) + 1):
        if all(lines[i + j].strip() == pattern[j].strip() for j in range(len(pattern))):
            return i

    return None


def _apply_chunks(path: Path, chunks: list[_UpdateChunk]) -> tuple[str, str]:
    original = path.read_text(encoding="utf-8", errors="replace")
    orig_lines = original.split("\n")
    if orig_lines and orig_lines[-1] == "":
        orig_lines.pop()

    replacements: list[tuple[int, int, list[str]]] = []
    line_idx = 0

    for chunk in chunks:
        if chunk.change_context:
            idx = _seek_sequence(orig_lines, [chunk.change_context], line_idx, False)
            if idx is None:
                raise ValueError(f"Context '{chunk.change_context}' not found in {path}")
            line_idx = idx + 1

        if not chunk.old_lines:
            ins = len(orig_lines) - 1 if (orig_lines and orig_lines[-1] == "") else len(orig_lines)
            replacements.append((ins, 0, chunk.new_lines))
            continue

        pattern = chunk.old_lines
        new_slice = chunk.new_lines
        found = _seek_sequence(orig_lines, pattern, line_idx, chunk.is_end_of_file)

        if found is None and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            new_slice = new_slice[:-1] if new_slice and new_slice[-1] == "" else new_slice
            found = _seek_sequence(orig_lines, pattern, line_idx, chunk.is_end_of_file)

        if found is None:
            raise ValueError(f"Lines not found in {path}:\n" + "\n".join(chunk.old_lines))

        replacements.append((found, len(pattern), list(new_slice)))
        line_idx = found + len(pattern)

    replacements.sort(key=lambda x: x[0])
    result = list(orig_lines)
    for start, old_len, new_seg in reversed(replacements):
        result[start:start + old_len] = new_seg

    if not (result and result[-1] == ""):
        result.append("")
    return original, "\n".join(result)


# ── Diff summary ───────────────────────────────────────────────────────────────

def _diff_summary(old: str, new: str, max_lines: int = 30) -> str:
    import difflib
    output: list[str] = []
    lines_shown = 0
    old_no = new_no = 1
    for group in difflib.SequenceMatcher(None, old.splitlines(), new.splitlines()).get_grouped_opcodes(0):
        for tag, i1, i2, j1, j2 in group:
            if lines_shown >= max_lines:
                output.append("... (diff truncated)")
                return "\n".join(output)
            if tag == "equal":
                old_no += i2 - i1
                new_no += j2 - j1
                continue
            if tag in ("replace", "delete"):
                for line in old.splitlines()[i1:i2]:
                    if line.strip():
                        output.append(f"{old_no}- {line.strip()}")
                        lines_shown += 1
                    old_no += 1
            if tag in ("replace", "insert"):
                for line in new.splitlines()[j1:j2]:
                    if line.strip():
                        output.append(f"{new_no}+ {line.strip()}")
                        lines_shown += 1
                    new_no += 1
    return "\n".join(output)


# ── Public API ─────────────────────────────────────────────────────────────────

def _confine(base: Path, rel_path: str) -> Path:
    """Resolve rel_path against base and require it stay inside base.

    hunk.path/move_to are parsed directly out of the patch TEXT (the
    "*** Add File: <path>"/"*** Update File: <path>"/"*** Move to: <path>"
    directives) -- an LLM-generated patch (this tool's whole purpose) that
    names an absolute path or a "../" escape previously reached
    `base / path` with zero confinement. pathlib's own `/` operator
    returns an absolute RHS unmodified, discarding `base` entirely, so an
    absolute path escaped silently; a relative "../../x" escaped via
    resolve(). Same bug class fixed in core/code_conductor/str_replace.py
    (read_files()) and 5+ districts/coding/ files this cycle.
    """
    resolved = (base / rel_path).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"path escapes base_dir: {rel_path!r}")
    return resolved


def apply_patch(patch_text: str, base_dir: str = ".") -> dict:
    """
    Apply a Codex-style *** Begin Patch / *** End Patch block.

    Returns:
        {success, results, touched_files, error}
    """
    base = Path(base_dir).resolve()
    try:
        hunks = _parse_patch(patch_text)
    except ValueError as e:
        return {"success": False, "error": str(e), "results": [], "touched_files": []}

    results: list[str] = []
    touched: list[str] = []
    errors: list[str] = []

    for hunk in hunks:
        try:
            _confine(base, hunk.path)
            if isinstance(hunk, _UpdateFile) and hunk.move_to:
                _confine(base, hunk.move_to)
        except ValueError as e:
            errors.append(f"✗ {hunk.path}: {e}")
            logger.error("[VECTOR][apply_patch] rejected {}: {}", hunk.path, e)
            continue
        if isinstance(hunk, _AddFile):
            dest = base / hunk.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(hunk.contents, encoding="utf-8")
            diff = _diff_summary("", hunk.contents)
            touched.append(hunk.path)
            results.append(f"✓ {hunk.path}: created\n{diff}" if diff else f"✓ {hunk.path}: created")
            logger.info("[VECTOR][apply_patch] created {}", hunk.path)

        elif isinstance(hunk, _DeleteFile):
            target = base / hunk.path
            if target.exists():
                old = target.read_text(encoding="utf-8", errors="replace")
                target.unlink()
                diff = _diff_summary(old, "")
                touched.append(hunk.path)
                results.append(f"✓ {hunk.path}: deleted\n{diff}" if diff else f"✓ {hunk.path}: deleted")
                logger.info("[VECTOR][apply_patch] deleted {}", hunk.path)
            else:
                errors.append(f"✗ {hunk.path}: file not found for deletion")

        elif isinstance(hunk, _UpdateFile):
            src = base / hunk.path
            try:
                old, new = _apply_chunks(src, hunk.chunks)
                diff = _diff_summary(old, new)
                if hunk.move_to:
                    dest = base / hunk.move_to
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(new, encoding="utf-8")
                    src.unlink()
                    touched.extend([hunk.path, hunk.move_to])
                    results.append(
                        f"✓ {hunk.path}: modified ({len(hunk.chunks)} hunks), moved to {hunk.move_to}\n{diff}"
                        if diff else
                        f"✓ {hunk.path}: modified ({len(hunk.chunks)} hunks), moved to {hunk.move_to}"
                    )
                else:
                    src.write_text(new, encoding="utf-8")
                    touched.append(hunk.path)
                    results.append(
                        f"✓ {hunk.path}: modified ({len(hunk.chunks)} hunks)\n{diff}"
                        if diff else
                        f"✓ {hunk.path}: modified ({len(hunk.chunks)} hunks)"
                    )
                logger.info("[VECTOR][apply_patch] updated {}", hunk.path)
            except Exception as e:
                errors.append(f"✗ {hunk.path}: {e}")
                logger.error("[VECTOR][apply_patch] failed on {}: {}", hunk.path, e)

    all_results = results + errors
    return {
        "success": len(errors) == 0,
        "results": all_results,
        "touched_files": touched,
        "applied": len(results),
        "failed": len(errors),
    }


if __name__ == "__main__":
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "hello.py"
        src.write_text("x = 1\ny = 2\n")

        patch = """*** Begin Patch
*** Update File: hello.py
@@ x = 1
-y = 2
+y = 99
*** Add File: new_file.py
+def greet():
+    return "hello"
*** End Patch"""

        result = apply_patch(patch, tmpdir)
        assert result["success"], result
        assert "99" in src.read_text()
        assert (Path(tmpdir) / "new_file.py").exists()
        assert result["applied"] == 2

    print("OK apply_patch.py")
