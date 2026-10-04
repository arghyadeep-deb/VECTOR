"""Regression for vectorcode/src/cli/auth.py: one suppressed-exception
debug log used a %s placeholder, silently broken under loguru's
{}-style formatter (loguru was already correctly imported, just used
inconsistently at this one site)."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import cli.auth as auth_module


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(auth_module)
    assert "%s" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
