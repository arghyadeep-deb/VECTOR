"""Regression for two missing `from pathlib import Path` imports in
vectorcode/src/config/:

- env_detector.py's EnvInfo.adjust_paths() called Path.home() with no
  Path import -- raised NameError on every single call, on every
  platform (confirmed: even the file's own mandated self-test block
  crashed on it).
- theme.py's ThemeEngine._load_custom_themes() (called from
  ThemeEngine.__init__, i.e. on every instantiation, including the
  module singleton get_theme_engine()) and save_theme() both called
  Path.home() with the same missing import -- constructing a
  ThemeEngine crashed unconditionally.

Both dormant today (zero real callers anywhere in the repo, confirmed
via grep), fixed anyway per this cycle's established bar -- both are
part of this module's public API surface (documented in
vectorcode/docs/API_REFERENCE.md) and crashed 100% of the time they were
used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.config.env_detector import detect
from vectorcode.src.config.theme import ThemeEngine, get_theme_engine


def test_env_detector_adjust_paths_does_not_crash():
    info = detect()
    paths = info.adjust_paths()
    assert "home" in paths
    assert "tmp" in paths
    assert "vector_data" in paths


def test_theme_engine_constructs_without_crashing():
    engine = ThemeEngine()
    assert engine.current().name == "vector"


def test_get_theme_engine_singleton_works():
    engine = get_theme_engine()
    assert "vector" in engine.list_themes()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
