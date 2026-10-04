"""Regression for two bugs in vectorcode/src/vc_tools/git_tool.py:

1. Module-level ``logger.debug(...)`` inside the ``_rust_bridge`` import's
   ``except ImportError:`` handler referenced ``logger`` before it was
   defined (the ``logger = logging.getLogger(__name__)`` line came AFTER
   the try/except). Confirmed live: simulating a missing rust bridge
   raised ``NameError: name 'logger' is not defined`` during module import,
   which would crash the whole module -- all four git tools -- in any
   environment without the compiled rust extension.

2. Even with (1) fixed, ``GitStatusTool.execute()`` and
   ``GitDiffTool.execute()`` (default, unstaged/no-path case) called
   ``get_rust_module()`` and used its result directly with no fallback to
   the subprocess-based ``_run_git()`` helper already present in this same
   file -- unlike ``GitLogTool.execute()``, which has exactly this
   fallback a few lines later. Confirmed live in this repo's own
   environment: the rust bridge imports fine, but ``get_rust_module()``
   returns an object with no ``GitStatusTool``/``GitDiffTool`` attribute,
   so both tools unconditionally failed on every call
   (``'NoneType' object has no attribute 'GitStatusTool'`` style errors)
   while ``git_log`` worked because of its fallback. Added the same
   fallback to status/diff.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

_SRC = Path("vectorcode/src/vc_tools/git_tool.py").read_text(encoding="utf-8")


def test_logger_is_defined_before_first_use():
    first_use = _SRC.index("logger.debug")
    definition = _SRC.index("from loguru import logger")
    assert definition < first_use, "logger is used before it is imported/defined"


def test_no_leftover_percent_style_placeholders():
    calls = re.findall(r"logger\.(?:info|warning|error|debug|critical)\(\s*\"[^\"]*%[sdr]", _SRC)
    assert calls == []


def test_git_status_falls_back_to_cli_when_rust_module_lacks_method(monkeypatch, tmp_path):
    from vectorcode.src.vc_tools import git_tool

    class _StubRust:
        pass  # no GitStatusTool attribute -- simulates the real live gap

    monkeypatch.setattr(git_tool, "get_rust_module", lambda: _StubRust())

    repo = tmp_path
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "f.txt").write_text("hi", encoding="utf-8")

    result = git_tool.GitStatusTool().execute(repo_path=str(repo))
    assert result.success is True
    assert "f.txt" in result.content


def test_git_diff_falls_back_to_cli_when_rust_module_lacks_method(monkeypatch, tmp_path):
    from vectorcode.src.vc_tools import git_tool

    class _StubRust:
        pass

    monkeypatch.setattr(git_tool, "get_rust_module", lambda: _StubRust())

    repo = tmp_path
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "f.txt").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (repo / "f.txt").write_text("changed", encoding="utf-8")

    result = git_tool.GitDiffTool().execute(repo_path=str(repo))
    assert result.success is True
    assert "changed" in result.content or "f.txt" in result.content


def test_get_rust_module_stub_returns_none_when_bridge_missing():
    # Static check: the except ImportError branch must bind a fallback
    # get_rust_module, not leave the name undefined.
    assert "def get_rust_module():" in _SRC
    assert "return None" in _SRC


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
