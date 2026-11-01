"""
CodeGraph — AST-based code intelligence for VECTOR's coding district.

Parses Python files using the stdlib `ast` module, builds an incremental
SQLite index of symbols (functions, classes, methods) and call-sites, then
exposes blast-radius / dependent queries so the coding agents know what
breaks when a symbol changes.

Schema
------
symbols  : one row per function/class/method in each file
calls    : directed edge caller_symbol → callee_name (intra-file for now)
"""

from core.memory.db_utils import apply_pragmas
import ast
import sqlite3
import threading
from pathlib import Path

from core.config import CONFIG  # noqa: F401 — keeps CONFIG available for future use
from loguru import logger

# ── SQL ────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS symbols (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    kind        TEXT    NOT NULL,  -- function | class | method
    lineno      INTEGER NOT NULL,
    end_lineno  INTEGER NOT NULL,
    UNIQUE(file, name, kind)
);

CREATE TABLE IF NOT EXISTS calls (
    caller_file  TEXT NOT NULL,
    caller_name  TEXT NOT NULL,
    callee_name  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file);
"""


# ── AST visitors ──────────────────────────────────────────────────────────────

class _SymbolVisitor(ast.NodeVisitor):
    """Collect all top-level and class-method function/class defs."""

    def __init__(self):
        self.symbols: list[dict] = []   # {name, kind, lineno, end_lineno}
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.symbols.append({
            "name": node.name,
            "kind": "class",
            "lineno": node.lineno,
            "end_lineno": node.end_lineno or node.lineno,
        })
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        kind = "method" if self._class_stack else "function"
        self.symbols.append({
            "name": node.name,
            "kind": kind,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno or node.lineno,
        })
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # treat async same as sync


class _CallVisitor(ast.NodeVisitor):
    """Collect call-sites for each top-level / method scope."""

    def __init__(self):
        # {caller_name: [callee_name, ...]}
        self.calls: dict[str, list[str]] = {}
        self._scope_stack: list[str] = []

    def _current_scope(self) -> str | None:
        return self._scope_stack[-1] if self._scope_stack else None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call):
        scope = self._current_scope()
        if scope is None:
            self.generic_visit(node)
            return
        callee = None
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        if callee:
            self.calls.setdefault(scope, []).append(callee)
        self.generic_visit(node)


# ── CodeGraph ─────────────────────────────────────────────────────────────────

class CodeGraph:
    """Incremental AST index with blast-radius analysis."""

    def __init__(self, repo_root: str, db_path: str):
        self.repo_root = Path(repo_root)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        apply_pragmas(self._conn)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"[VECTOR][code_graph] Opened index at {db_path} (root={repo_root})")

    # ── internal ──────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_DDL)
            self._conn.commit()

    def _parse_file(self, abs_path: Path) -> tuple[list[dict], dict[str, list[str]]]:
        """Return (symbols, calls_dict) for a Python source file."""
        try:
            source = abs_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(abs_path))
        except SyntaxError as e:
            logger.warning(f"[VECTOR][code_graph] SyntaxError in {abs_path}: {e}")
            return [], {}

        sv = _SymbolVisitor()
        sv.visit(tree)

        cv = _CallVisitor()
        cv.visit(tree)

        return sv.symbols, cv.calls

    def _upsert_symbols(self, rel_path: str, symbols: list[dict]) -> None:
        """Upsert symbols; remove stale rows for the file first."""
        with self._lock:
            cur = self._conn.cursor()
            # Delete stale symbols for this file so incremental updates are clean
            cur.execute("DELETE FROM symbols WHERE file = ?", (rel_path,))
            # Delete stale call edges too
            cur.execute("DELETE FROM calls WHERE caller_file = ?", (rel_path,))
            for s in symbols:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO symbols (file, name, kind, lineno, end_lineno)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (rel_path, s["name"], s["kind"], s["lineno"], s["end_lineno"]),
                )
            self._conn.commit()

    def _upsert_calls(self, rel_path: str, calls: dict[str, list[str]]) -> None:
        with self._lock:
            cur = self._conn.cursor()
            for caller, callees in calls.items():
                for callee in callees:
                    cur.execute(
                        "INSERT INTO calls (caller_file, caller_name, callee_name) VALUES (?, ?, ?)",
                        (rel_path, caller, callee),
                    )
            self._conn.commit()

    # ── public API ────────────────────────────────────────────────────────────

    def index_file(self, rel_path: str) -> int:
        """Parse one file and upsert into the index. Returns number of symbols found."""
        abs_path = self.repo_root / rel_path
        if not abs_path.exists():
            logger.warning(f"[VECTOR][code_graph] File not found: {abs_path}")
            return 0
        symbols, calls = self._parse_file(abs_path)
        self._upsert_symbols(rel_path, symbols)
        self._upsert_calls(rel_path, calls)
        logger.debug(f"[VECTOR][code_graph] Indexed {rel_path}: {len(symbols)} symbols")
        return len(symbols)

    def index_repo(self, extensions: list[str] | None = None) -> int:
        """Walk repo_root and index all matching files. Returns total symbols indexed."""
        if extensions is None:
            extensions = [".py"]
        total = 0
        for ext in extensions:
            for path in self.repo_root.rglob(f"*{ext}"):
                try:
                    rel = str(path.relative_to(self.repo_root))
                    total += self.index_file(rel)
                except Exception as e:
                    logger.warning(f"[VECTOR][code_graph] Skipped {path}: {e}")
        logger.info(f"[VECTOR][code_graph] index_repo complete: {total} total symbols")
        return total

    def list_symbols(self, rel_path: str) -> list[str]:
        """Return symbol names (any kind) defined in a specific file."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT name FROM symbols WHERE file = ? ORDER BY lineno", (rel_path,)
            )
            rows = cur.fetchall()
        return [row["name"] for row in rows]

    def list_all_symbols(self) -> list[str]:
        """Return all symbol names across the entire indexed repo."""
        with self._lock:
            cur = self._conn.execute("SELECT DISTINCT name FROM symbols ORDER BY name")
            rows = cur.fetchall()
        return [row["name"] for row in rows]

    def blast_radius(self, symbol_name: str) -> list[str]:
        """
        Return a list of caller symbols that directly call `symbol_name`.
        These are the symbols 'at risk' if `symbol_name` changes.
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT DISTINCT caller_name FROM calls WHERE callee_name = ?",
                (symbol_name,),
            )
            rows = cur.fetchall()
        return [row["caller_name"] for row in rows]

    def dependents(self, rel_path: str) -> list[str]:
        """
        Return files that contain call-edges to symbols defined in `rel_path`.
        i.e. files that depend on (import/call into) this file.
        """
        # Get all symbols in the file
        defined = self.list_symbols(rel_path)
        if not defined:
            return []
        placeholders = ", ".join("?" * len(defined))
        with self._lock:
            cur = self._conn.execute(
                f"""
                SELECT DISTINCT caller_file
                FROM calls
                WHERE callee_name IN ({placeholders})
                  AND caller_file != ?
                """,
                (*defined, rel_path),
            )
            rows = cur.fetchall()
        return [row["caller_file"] for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ── smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, textwrap, os

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "sample.py"
        src.write_text(textwrap.dedent("""
            def foo():
                return bar()
            def bar():
                return 42
            class MyClass:
                def method(self):
                    foo()
        """))

        cg = CodeGraph(repo_root=tmp, db_path=str(Path(tmp) / "test.db"))
        count = cg.index_file("sample.py")
        assert count >= 4, f"Expected >=4 symbols, got {count}"

        syms = cg.list_symbols("sample.py")
        assert "foo" in syms and "bar" in syms, f"Missing symbols: {syms}"

        radius = cg.blast_radius("bar")
        assert "foo" in radius, f"blast_radius('bar') should contain 'foo', got {radius}"

        all_syms = cg.list_all_symbols()
        assert len(all_syms) >= 2

        # Incremental update
        src.write_text("def foo():\n    pass\ndef baz():\n    pass\n")
        cg.index_file("sample.py")
        updated = cg.list_symbols("sample.py")
        assert "baz" in updated, f"baz not found after incremental update: {updated}"

        cg.close()
        print("✅ code_graph OK")


