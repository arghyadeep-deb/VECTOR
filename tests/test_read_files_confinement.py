"""Regression: core.code_conductor.str_replace.read_files() never called
_contained_path() the way str_replace()/write_file() do -- an absolute path
(or a relative one escaping via "..") was read with zero confinement even
when a real cwd workspace was given. Same real-world input source as the
2026-09-26 str_replace()/write_file() fix (an LLM-produced plan), same fix
reused for consistency.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.code_conductor.str_replace import read_files


def test_read_files_refuses_absolute_path_outside_cwd(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("top secret contents")

    result = read_files(paths=[str(outside)], cwd=str(workspace))
    assert result["files"] == []
    assert any("secret.txt" in s for s in result["skipped"])


def test_read_files_refuses_dotdot_escape(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("top secret contents")

    result = read_files(paths=["../secret.txt"], cwd=str(workspace))
    assert result["files"] == []
    assert len(result["skipped"]) == 1


def test_read_files_still_reads_a_real_in_workspace_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real = workspace / "real.txt"
    real.write_text("hello world")

    result = read_files(paths=["real.txt"], cwd=str(workspace))
    assert len(result["files"]) == 1
    assert result["files"][0]["content"] == "hello world"


def test_read_files_with_no_cwd_is_unchanged_behavior(tmp_path):
    # Documented tradeoff shared with str_replace()/write_file(): with no
    # cwd there is no workspace to enforce, so behavior is unchanged.
    real = tmp_path / "f.txt"
    real.write_text("content")
    result = read_files(paths=[str(real)], cwd=None)
    assert len(result["files"]) == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
