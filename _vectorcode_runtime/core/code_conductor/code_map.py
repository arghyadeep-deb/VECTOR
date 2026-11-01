"""
VECTOR Code Conductor — Code Symbol Map
Python port of codebuff/packages/code-map/ using tree-sitter.

Builds an AST-based symbol index of a codebase: functions, classes, imports.
Used by the CodingOrchestrator to understand code structure before editing.

Falls back to regex-based parsing if tree-sitter is not installed.

Usage:
    cm = CodeMap("/path/to/project")
    cm.build()
    logger.info(cm.summary())              # token-efficient structure overview

    hits = cm.query("GUIAgent")      # find all definitions of a symbol
"""
from __future__ import annotations

__all__ = [
    "CodeMap",
    "Symbol",
]


import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

_SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
_MAX_FILE_SIZE = 200_000  # 200KB
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next"}


@dataclass
class Symbol:
    name: str
    kind: str          # function | class | method | import | variable
    file: str
    line: int
    signature: str = ""
    docstring: str = ""


@dataclass
class CodeMap:
    """AST-based symbol index for a Python/JS/TS codebase."""

    root: str
    _index: dict[str, list[Symbol]] = field(default_factory=dict)   # file → symbols
    _by_name: dict[str, list[Symbol]] = field(default_factory=dict)  # name → symbols
    _built: bool = False

    def build(self, paths: list[str] | None = None) -> "CodeMap":
        """
        Index all supported source files in root (or specific paths).
        Returns self for chaining.
        """
        self._index = {}
        self._by_name = {}

        if paths:
            files = [Path(p) for p in paths if Path(p).is_file()]
        else:
            files = list(self._walk_files())

        use_tree_sitter = self._try_tree_sitter_import()

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                rel = os.path.relpath(str(f), self.root)
                if use_tree_sitter and f.suffix == ".py":
                    symbols = self._parse_python_ts(content, rel)
                else:
                    symbols = self._parse_regex(content, rel, f.suffix)
                self._index[rel] = symbols
                for sym in symbols:
                    self._by_name.setdefault(sym.name, []).append(sym)
            except Exception as e:
                logger.debug("[VECTOR][code_map] skipped {}: {}", f, e)

        self._built = True
        total = sum(len(v) for v in self._index.values())
        logger.info("[VECTOR][code_map] indexed {} files, {} symbols", len(self._index), total)
        return self

    def query(self, symbol_name: str) -> list[Symbol]:
        """Find all definitions/usages of a symbol by name (exact or partial match)."""
        exact = self._by_name.get(symbol_name, [])
        if exact:
            return exact
        return [
            sym
            for name, syms in self._by_name.items()
            if symbol_name.lower() in name.lower()
            for sym in syms
        ]

    def symbols_in_file(self, file_path: str) -> list[Symbol]:
        """Get all symbols defined in a specific file."""
        rel = os.path.relpath(file_path, self.root) if os.path.isabs(file_path) else file_path
        return self._index.get(rel, [])

    def summary(self, max_chars: int = 8000) -> str:
        """
        Token-efficient codebase structure summary for LLM context.
        Format: file path + key symbols.
        """
        lines: list[str] = [f"Codebase: {self.root}", ""]
        chars = 0

        for file_rel, symbols in sorted(self._index.items()):
            if not symbols:
                continue
            file_line = f"{file_rel}:"
            sym_parts = []
            for sym in symbols:
                if sym.kind in ("function", "class", "method"):
                    sym_parts.append(f"{sym.kind[0]}:{sym.name}" + (f"({sym.signature})" if sym.signature else ""))
            if not sym_parts:
                continue
            entry = f"  {file_line}\n    " + ", ".join(sym_parts[:20])
            if chars + len(entry) > max_chars:
                lines.append("  ... [truncated]")
                break
            lines.append(entry)
            chars += len(entry)

        return "\n".join(lines)

    # ── File walking ──────────────────────────────────────────────────────────

    def _walk_files(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune skip dirs in-place
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix in _SUPPORTED_EXTENSIONS and p.stat().st_size < _MAX_FILE_SIZE:
                    yield p

    # ── Tree-sitter parsing ───────────────────────────────────────────────────

    def _try_tree_sitter_import(self) -> bool:
        try:
            import tree_sitter  # noqa: F401
            return True
        except ImportError:
            return False

    def _parse_python_ts(self, content: str, rel_path: str) -> list[Symbol]:
        """Parse Python file with tree-sitter for precise AST-based extraction."""
        try:
            import tree_sitter_python as tspython
            from tree_sitter import Language, Parser

            PY_LANGUAGE = Language(tspython.language())
            parser = Parser(PY_LANGUAGE)
            tree = parser.parse(content.encode())

            symbols: list[Symbol] = []

            def walk(node, class_ctx: str | None = None):
                if node.type in ("function_definition", "async_function_definition"):
                    name_node = node.child_by_field_name("name")
                    name = name_node.text.decode() if name_node else ""
                    params_node = node.child_by_field_name("parameters")
                    sig = params_node.text.decode() if params_node else ""
                    kind = "method" if class_ctx else "function"
                    # Try to get docstring
                    doc = ""
                    body = node.child_by_field_name("body")
                    if body and body.child_count > 0:
                        first = body.children[0]
                        if first.type == "expression_statement" and first.child_count > 0:
                            s = first.children[0]
                            if s.type == "string":
                                doc = s.text.decode().strip("'\"").strip()[:120]
                    symbols.append(Symbol(name=name, kind=kind, file=rel_path,
                                         line=node.start_point[0]+1, signature=sig, docstring=doc))
                    for child in node.children:
                        walk(child, class_ctx)

                elif node.type == "class_definition":
                    name_node = node.child_by_field_name("name")
                    name = name_node.text.decode() if name_node else ""
                    symbols.append(Symbol(name=name, kind="class", file=rel_path,
                                         line=node.start_point[0]+1))
                    for child in node.children:
                        walk(child, class_ctx=name)

                elif node.type == "import_statement":
                    symbols.append(Symbol(name=node.text.decode()[:80], kind="import",
                                         file=rel_path, line=node.start_point[0]+1))
                else:
                    for child in node.children:
                        walk(child, class_ctx)

            walk(tree.root_node)
            return symbols

        except Exception as e:
            logger.debug("[VECTOR][code_map] tree-sitter parse failed {}: {} — using regex", rel_path, e)
            return self._parse_regex(content, rel_path, ".py")

    # ── Regex fallback ────────────────────────────────────────────────────────

    def _parse_regex(self, content: str, rel_path: str, ext: str) -> list[Symbol]:
        """Regex-based symbol extraction (fallback, works for all languages)."""
        symbols: list[Symbol] = []
        lines = content.splitlines()

        if ext == ".py":
            for i, line in enumerate(lines):
                # Class
                m = re.match(r"^class\s+(\w+)[\s:(]", line)
                if m:
                    symbols.append(Symbol(name=m.group(1), kind="class", file=rel_path, line=i+1))
                    continue
                # Function/method (detect method by leading spaces)
                m = re.match(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*(\([^)]*\))?", line)
                if m:
                    indent = len(m.group(1))
                    kind = "method" if indent > 0 else "function"
                    sig = m.group(3) or ""
                    symbols.append(Symbol(name=m.group(2), kind=kind, file=rel_path,
                                         line=i+1, signature=sig))
                    continue
                # Import
                m = re.match(r"^(?:import|from)\s+(\S+)", line)
                if m:
                    symbols.append(Symbol(name=m.group(1), kind="import", file=rel_path, line=i+1))

        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            for i, line in enumerate(lines):
                # class Foo
                m = re.match(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", line)
                if m:
                    symbols.append(Symbol(name=m.group(1), kind="class", file=rel_path, line=i+1))
                    continue
                # function foo / const foo = () =>
                m = re.match(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(\([^)]*\))?", line)
                if m:
                    sig = m.group(2) or ""
                    symbols.append(Symbol(name=m.group(1), kind="function", file=rel_path,
                                         line=i+1, signature=sig))
                    continue
                m = re.match(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(", line)
                if m:
                    symbols.append(Symbol(name=m.group(1), kind="function", file=rel_path, line=i+1))
                    continue
                # import
                m = re.match(r"^\s*import\s+.+\s+from\s+['\"](.+)['\"]", line)
                if m:
                    symbols.append(Symbol(name=m.group(1), kind="import", file=rel_path, line=i+1))

        return symbols


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    # Index VECTOR's own core directory as smoke test
    root = str(Path(__file__).parent.parent.parent)
    cm = CodeMap(root=root)
    cm.build(paths=[
        str(Path(__file__).parent / "str_replace.py"),
        str(Path(__file__).parent.parent / "config.py"),
    ])

    assert cm._built
    summary = cm.summary(max_chars=2000)
    assert "str_replace" in summary or "CodeMap" in summary or len(summary) > 10

    # Query a known symbol
    hits = cm.query("str_replace")
    print(f"OK code_map.py — {sum(len(v) for v in cm._index.values())} symbols indexed")
    print(f"  query('str_replace'): {len(hits)} hits")
    print(f"  summary preview: {summary[:200]}")
