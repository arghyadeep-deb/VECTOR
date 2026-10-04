"""Regression for two bugs in the skills "github" source:

1. vectorcode/src/skills/sources/github.py's GitHubResolver.sync() passed a
   caller-controlled repo_url (sourced from a CLI --url option, see
   cli/skill_cmd.py and vector_cli/skill_cmd.py) as a bare positional
   argument to `git clone`/`git pull` with no `--` separator. A repo_url
   starting with "-" (e.g. "--upload-pack=...", a known git-clone RCE
   primitive) would be parsed by git as a flag instead of a URL.

2. Both skill_cmd.py's _get_resolver("github", url=...) derived the cache
   directory name by taking the last "/"-separated segment of the URL with
   no validation -- a url ending in ".." (or with no "/" at all) made that
   segment literally "..", so the resulting cache_root escaped the intended
   skill-cache/github/ directory entirely.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import click
import pytest

from skills.sources.github import GitHubResolver


def test_sync_clone_uses_dashdash_separator_before_repo_url():
    src = inspect.getsource(GitHubResolver.sync)
    assert '"clone", "--", self._repo_url' in src, (
        "git clone must pass '--' before repo_url so a URL starting with "
        "'-' can't be parsed as a git flag"
    )


@pytest.mark.parametrize("module_path", ["cli.skill_cmd", "vector_cli.skill_cmd"])
def test_github_resolver_rejects_traversal_cache_name(module_path):
    mod = __import__(module_path, fromlist=["_get_resolver"])
    with pytest.raises(click.BadParameter):
        mod._get_resolver("github", url="https://example.com/a/..")


@pytest.mark.parametrize("module_path", ["cli.skill_cmd", "vector_cli.skill_cmd"])
def test_github_resolver_rejects_dot_only_cache_name(module_path):
    mod = __import__(module_path, fromlist=["_get_resolver"])
    with pytest.raises(click.BadParameter):
        mod._get_resolver("github", url="..")


@pytest.mark.parametrize("module_path", ["cli.skill_cmd", "vector_cli.skill_cmd"])
def test_github_resolver_accepts_normal_url(module_path):
    mod = __import__(module_path, fromlist=["_get_resolver"])
    resolver = mod._get_resolver("github", url="https://github.com/anthropics/skills")
    assert resolver.cache_dir().name == "skills"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
