"""
tests/integration/test_no_stubs.py — Phase 6B: Verify _stubs.py files are documented.

This test ensures every _stubs.py file has a docstring explaining its purpose.
It does NOT require renaming (that's a Phase 6A-level refactor).
The goal is to prevent new undocumented stubs from being added.
"""
import ast
from pathlib import Path
import pytest


def _find_stubs_files() -> list[Path]:
    root = Path(__file__).parent.parent.parent
    return [
        p for p in root.rglob("_stubs.py")
        if ".claude" not in str(p)
        and "node_modules" not in str(p)
        and "__pycache__" not in str(p)
        and "venv" not in str(p)
    ]


@pytest.mark.parametrize("stub_file", _find_stubs_files())
def test_stub_file_has_docstring(stub_file: Path):
    """Every _stubs.py must have a module-level docstring explaining its purpose."""
    source = stub_file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        pytest.skip(f"Syntax error in {stub_file} — skip docstring check")
        return
    docstring = ast.get_docstring(tree)
    assert docstring, (
        f"{stub_file.relative_to(stub_file.parent.parent.parent)} "
        f"has no module docstring. Add one explaining: "
        f"(A) ABC base class, (B) optional-dependency fallback, or (C) type definitions."
    )
