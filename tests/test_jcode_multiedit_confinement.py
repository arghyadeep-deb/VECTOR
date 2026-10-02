"""Regression: core/jcode/tools/multiedit.py's multiedit() read/wrote a
caller-supplied file_path with zero confinement. Real caller:
districts/coding/coding_tools.py's multiedit_file() (gated behind an active
coding grant, but that grant authorizes editing the repo, not an arbitrary
path a malformed/injected call could name) -- same bug class and same real
caller pattern as this cycle's apply_patch.py fix (sibling tool, same file).
Found during the Phase 3 whole-repo audit (2026-10-02).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.jcode.tools.multiedit import multiedit, _ROOT


def test_path_outside_repo_rejected(tmp_path):
    outside = tmp_path / "evil.py"
    outside.write_text("x = 1\n")
    result = multiedit(str(outside), [{"old_string": "x = 1", "new_string": "x = 2"}])
    assert result["success"] is False
    assert "outside repo" in result["error"]
    assert outside.read_text() == "x = 1\n"  # untouched


def test_legitimate_in_repo_path_still_works():
    tmpdir = _ROOT / "test_tmp" / "multiedit_confinement_test"
    tmpdir.mkdir(parents=True, exist_ok=True)
    f = tmpdir / "sample.py"
    f.write_text("a = 1\n")
    try:
        result = multiedit(str(f), [{"old_string": "a = 1", "new_string": "a = 2"}])
        assert result["success"] is True
        assert f.read_text() == "a = 2\n"
    finally:
        f.unlink()
        tmpdir.rmdir()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
