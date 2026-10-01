"""Regression: vectorcode/src/tools/worktree.py's WorktreeManager.create()
passed caller-controlled branch_name/base strings as bare positional git
arguments with no allowlist or "--" separator on the base ref -- a string
starting with "-" is interpreted as a git option (--upload-pack=<cmd> is a
known git RCE vector). Same bug class already fixed in this package's
git_tools.py (commit b1523366f) and core/mcp_tools/expansion_modules/git.py;
same allowlist fix applied here. Zero real production callers exist today
(confirmed via repo-wide grep for "WorktreeManager") -- fixed anyway since
the fix is narrow/mechanical and this class could be activated later.
"""
import sys
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.tools.worktree import WorktreeManager


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
    return WorktreeManager(tmp_path)


def test_create_rejects_option_like_base(repo):
    with pytest.raises(ValueError, match="invalid base ref"):
        repo.create(base="--upload-pack=touch${IFS}pwned")


def test_create_rejects_option_like_branch_name(repo):
    with pytest.raises(ValueError, match="invalid branch name"):
        repo.create(branch_name="--upload-pack=touch${IFS}pwned")


def test_create_rejects_dotdot_base(repo):
    with pytest.raises(ValueError, match="invalid base ref"):
        repo.create(base="HEAD..evil")


def test_create_still_works_for_legitimate_args(repo):
    wt_path = repo.create(branch_name="feature/real-branch-123", base="HEAD")
    assert wt_path.exists()
    repo.destroy(wt_path)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
