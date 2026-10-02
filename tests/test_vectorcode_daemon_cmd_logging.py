"""Regression: vectorcode/src/vector_cli/daemon_cmd.py had 3
"[VECTOR] suppressed exception" placeholders (loguru exc_info=True does
not capture the real exception the way stdlib logging does) -- same
systemic bug fixed 60+ times this cycle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_FILE = Path(__file__).parent.parent / "vectorcode" / "src" / "vector_cli" / "daemon_cmd.py"


def test_no_suppressed_exception_placeholder_remains():
    src = _FILE.read_text(encoding="utf-8")
    assert "suppressed exception" not in src


def test_syntax_valid():
    import ast
    ast.parse(_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
