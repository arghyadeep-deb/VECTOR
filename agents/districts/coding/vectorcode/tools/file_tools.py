import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))
from core.config import CONFIG

import re
import difflib
from loguru import logger

# Lazy import to avoid circular dependency at module level
def _get_gateway():
    from core.loop.permission_gateway import execute_action, Action
    return execute_action, Action


class FileTools:
    """
    Safe file I/O operations scoped to a repo root.
    All paths are validated against repo_root to prevent directory traversal.
    """

    def __init__(self, repo_root: str) -> None:
        self.repo_root: Path = Path(repo_root).resolve()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _safe_path(self, path: str) -> Path:
        """
        Resolve path relative to repo_root.
        Raises PermissionError if the resolved path escapes repo_root.
        """
        resolved = (self.repo_root / path).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError:
            raise PermissionError(
                f"Path traversal blocked: '{path}' resolves outside repo root '{self.repo_root}'"
            )
        return resolved

    # ── Public API ────────────────────────────────────────────────────────────

    def read(self, path: str) -> str:
        """Read and return the text content of a file."""
        safe = self._safe_path(path)
        logger.debug(f"[VECTOR][file_tools] read {safe}")
        return safe.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        """Write content to path, creating parent directories if needed."""
        safe = self._safe_path(path)
        safe.parent.mkdir(parents=True, exist_ok=True)
        safe.write_text(content, encoding="utf-8")
        logger.debug(f"[VECTOR][file_tools] write {safe} ({len(content)} chars)")

    def edit(self, path: str, old: str, new: str) -> None:
        """
        Replace first occurrence of `old` with `new` in file.
        Raises ValueError if `old` is not found.
        """
        safe = self._safe_path(path)
        content = safe.read_text(encoding="utf-8")
        if old not in content:
            raise ValueError(f"String not found in '{path}': {old!r}")
        updated = content.replace(old, new, 1)
        safe.write_text(updated, encoding="utf-8")
        logger.debug(f"[VECTOR][file_tools] edit {safe}")

    def grep(self, pattern: str, glob_pattern: str = "**/*.py") -> list:
        """
        Search for a regex pattern across files matching glob_pattern.
        Returns list of dicts: [{file, line, content}, ...]
        """
        compiled = re.compile(pattern)
        results = []
        for file_path in self.repo_root.glob(glob_pattern):
            if not file_path.is_file():
                continue
            try:
                for line_no, line in enumerate(
                    file_path.read_text(encoding="utf-8", errors="replace").splitlines(),
                    start=1,
                ):
                    if compiled.search(line):
                        results.append({
                            "file": str(file_path.relative_to(self.repo_root)),
                            "line": line_no,
                            "content": line,
                        })
            except OSError as exc:
                logger.warning(f"[VECTOR][file_tools] grep skip {file_path}: {exc}")
        return results

    def glob(self, pattern: str) -> list:
        """Return relative paths of files matching pattern within repo_root."""
        return [
            str(p.relative_to(self.repo_root))
            for p in self.repo_root.glob(pattern)
            if p.is_file()
        ]

    def delete(self, path: str) -> None:
        """
        Delete a file — requires RED-gate approval from permission_gateway.
        Raises PermissionError on traversal; propagates gateway denial.
        """
        safe = self._safe_path(path)
        execute_action, Action = _get_gateway()
        import asyncio
        action = Action(
            action_type="delete_file",
            params={"path": str(safe)},
            proposed_by="FileTools",
            priority="normal",
        )
        result = asyncio.get_event_loop().run_until_complete(execute_action(action))
        if result.approved:
            safe.unlink()
            logger.info(f"[VECTOR][file_tools] deleted {safe}")
        else:
            raise PermissionError(f"Gateway denied delete for '{path}': {result.reason}")

    def list_directory(self, path: str = ".") -> list[str]:
        """
        List files and directories within path (relative to repo_root).
        Returns relative path strings sorted alphabetically.
        """
        safe = self._safe_path(path)
        if not safe.is_dir():
            raise NotADirectoryError(f"Not a directory: '{path}'")
        entries = []
        for entry in sorted(safe.iterdir()):
            rel = str(entry.relative_to(self.repo_root))
            entries.append(rel + ("/" if entry.is_dir() else ""))
        return entries

    def move_file(self, src: str, dst: str) -> None:
        """
        Move/rename a file within repo_root.
        Both src and dst must resolve inside repo_root.
        """
        safe_src = self._safe_path(src)
        safe_dst = self._safe_path(dst)
        if not safe_src.exists():
            raise FileNotFoundError(f"Source not found: '{src}'")
        safe_dst.parent.mkdir(parents=True, exist_ok=True)
        safe_src.rename(safe_dst)
        logger.debug(f"[VECTOR][file_tools] move {safe_src} → {safe_dst}")

    def create_file(self, path: str, content: str = "") -> None:
        """Create a new file at path (fails if already exists)."""
        safe = self._safe_path(path)
        if safe.exists():
            raise FileExistsError(f"File already exists: '{path}'")
        safe.parent.mkdir(parents=True, exist_ok=True)
        safe.write_text(content, encoding="utf-8")
        logger.debug(f"[VECTOR][file_tools] created {safe}")

    def exists(self, path: str) -> bool:
        """Return True if path exists within repo_root."""
        try:
            return self._safe_path(path).exists()
        except PermissionError:
            return False

    def diff(self, path: str, old_content: str, new_content: str) -> str:
        """Return a unified diff string comparing old_content to new_content."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}")
        )


if __name__ == "__main__":
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        ft = FileTools(repo_root=tmp)
        ft.write("hello.py", "print('hello')")
        assert ft.read("hello.py") == "print('hello')"
        ft.write("code.py", "def foo():\n    pass\ndef bar():\n    pass")
        results = ft.grep("def ", "*.py")
        assert len(results) == 2, f"Expected 2 grep results, got {len(results)}"
        ft.write("a.py", "x")
        ft.write("b.py", "y")
        globs = ft.glob("*.py")
        assert len(globs) >= 2
        ft.edit("hello.py", "print('hello')", "print('world')")
        assert ft.read("hello.py") == "print('world')"
        try:
            ft.read("../../etc/passwd")
            assert False, "Should have raised PermissionError"
        except PermissionError:
            pass
    print("file_tools.py OK")
