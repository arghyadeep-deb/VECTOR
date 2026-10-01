"""Regression: vectorcode/src/tools/git_tools.py's git_push()/git_create_branch()
passed caller-controlled strings as bare positional git arguments with no
allowlist or "--" separator -- a string starting with "-" is interpreted as a
git option (--upload-pack=<cmd> is a known git RCE vector). Same bug class
already fixed in core/mcp_tools/expansion_modules/git.py (commits
d41e9a1f2/46e4b2fda); same allowlist fix applied here.
"""
import sys
import tempfile
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.tools.git_tools import GitTools


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
    return GitTools(repo_root=tmp_path)


def test_git_push_rejects_option_like_remote(repo):
    out = repo.git_push(remote="--upload-pack=touch${IFS}pwned", branch="main")
    assert "invalid remote" in out
    assert "push failed" in out


def test_git_push_rejects_option_like_branch(repo):
    out = repo.git_push(remote="origin", branch="--upload-pack=touch${IFS}pwned")
    assert "invalid" in out


def test_git_create_branch_rejects_option_like_name(repo):
    out = repo.git_create_branch("--upload-pack=touch${IFS}pwned")
    assert "invalid" in out
    assert "Branch creation failed" in out


def test_git_create_branch_rejects_option_like_name_no_checkout(repo):
    out = repo.git_create_branch("--force", checkout=False)
    assert "invalid" in out


def test_git_create_branch_still_works_for_legitimate_names(repo):
    out = repo.git_create_branch("feature/real-branch-123", checkout=False)
    assert "created" in out
    assert "feature/real-branch-123" in repo._run(["branch"])["stdout"]


def test_git_push_rejects_ref_with_dotdot(repo):
    out = repo.git_push(remote="origin", branch="main..evil")
    assert "invalid" in out
