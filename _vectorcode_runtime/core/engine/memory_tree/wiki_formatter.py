"""VECTOR Wiki Formatter — converts Memory Tree to Obsidian-compatible markdown."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.engine.memory_tree.tree_builder import MemoryTree


def _safe_page_name(key: str, max_length: int) -> str:
    """Return a portable single-component filename for an untrusted tree key."""
    safe = re.sub(r"[^\w.-]", "_", key, flags=re.UNICODE).strip(" .")
    safe = safe[:max_length].rstrip(" .") or "memory"
    # Windows device names remain special even with an extension.
    if safe.upper().split(".", 1)[0] in {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
        "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
        "LPT6", "LPT7", "LPT8", "LPT9",
    }:
        safe = f"_{safe}"
    return safe


def _atomic_write_text(path: Path, content: str) -> None:
    """Durably replace *path* without exposing a partially written page."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


class WikiFormatter:
    """
    Formats the full VECTOR memory tree as an Obsidian wiki vault.

    Outputs:
      - One file per source
      - MOC (Map of Contents) index
      - Wikilinks between related pages
    """

    def __init__(self, tree: MemoryTree) -> None:
        self._tree = tree

    def format_source(self, source_kind: str, source_id: str) -> str:
        return self._tree.build_wiki(source_kind, source_id)

    def format_moc(self) -> str:
        """Map of Contents — index of all memory tree sources."""
        lines = [
            "# VECTOR Memory — Map of Contents",
            f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
            "",
            "## Sources",
            "",
        ]
        for key, source in self._tree._sources.items():
            chunk_count = sum(n.chunk_count() for n in source.nodes.values())
            safe = _safe_page_name(key, 40)
            lines.append(f"- [[{safe}]] — {source.source_kind} · {chunk_count} chunks")

        lines += ["", "## Topics", ""]
        for topic in self._tree.get_topics():
            lines.append(f"- #{topic}")

        return "\n".join(lines)

    def save_all(self, output_dir: Path | None = None) -> list[Path]:
        out = output_dir or self._tree._wiki_dir
        out.mkdir(parents=True, exist_ok=True)
        paths = []

        # MOC
        moc_path = out / "MOC.md"
        _atomic_write_text(moc_path, self.format_moc())
        paths.append(moc_path)

        # One file per source
        for key, source in self._tree._sources.items():
            wiki = self.format_source(source.source_kind, source.source_id)
            safe = _safe_page_name(key, 50)
            p = out / f"{safe}.md"
            _atomic_write_text(p, wiki)
            paths.append(p)

        return paths


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tree = MemoryTree(db_dir=Path(d) / "db", wiki_dir=Path(d) / "wiki")
        tree.ingest("conversation", "sess_1", "VECTOR uses Python 3.11", topic="coding")
        tree.ingest("conversation", "sess_1", "Arghyadeep is building VECTOR", topic="goals")
        fmt = WikiFormatter(tree)
        moc = fmt.format_moc()
        assert "sess_1" in moc.lower() or "conversation" in moc.lower()
        paths = fmt.save_all(Path(d) / "wiki")
        assert any("MOC" in str(p) for p in paths)
    print("OK wiki_formatter.py")
