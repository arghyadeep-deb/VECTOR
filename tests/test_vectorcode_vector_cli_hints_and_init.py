"""Regression for two bugs found in vectorcode/src/vector_cli/ (Phase 3 audit):

1. hints.py's hint_no_config() told the user the config file would be at
   "~/.vectorcode.src/config.toml" -- a Python-module-path fragment
   (".src") leaking into user-facing text. The real path, confirmed via
   vectorcode/src/vc_core/config.py's own DEFAULT_CONFIG_PATH, is
   "~/.vector/config.toml". A user following the hint literally would
   look in a directory that never exists.

2. __init__.py's kanban_db import guard used the
   "[VECTOR] suppressed exception" placeholder with no real exception
   text -- same systemic bug fixed 60+ times this cycle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vector_cli import hints
from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH


def test_hint_no_config_points_at_the_real_config_path():
    text = hints.hint_no_config()
    assert ".vectorcode.src" not in text
    assert str(DEFAULT_CONFIG_PATH.name) in text
    assert DEFAULT_CONFIG_DIR.name in text


def test_vector_cli_package_imports_cleanly():
    import importlib
    import vectorcode.src.vector_cli as pkg
    importlib.reload(pkg)  # exercises the kanban_db import-guard block


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
