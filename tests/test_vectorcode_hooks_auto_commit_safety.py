"""Regression for vectorcode/hooks/auto_commit.py:

(1) auto_commit.py commits with --no-verify, bypassing pre_commit_gate.py's
staged-secret check entirely -- it had no filename check of its own, so
editing a .env/credentials file would auto-stage-and-commit the secret
straight into git history with no gate ever seeing it.
(2) `git add <file_path>` reached the filesystem with no "--" separator,
so a file_path starting with "-" could be parsed as a git option.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "vectorcode" / "hooks" / "auto_commit.py"


def _run_hook(file_path: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"file_path": file_path})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)


def test_never_stages_or_commits_a_dangerous_filename(tmp_path):
    _init_repo(tmp_path)
    secret = tmp_path / ".env"
    secret.write_text("API_KEY=super-secret\n", encoding="utf-8")

    result = _run_hook(".env", tmp_path)

    assert result.returncode == 0
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert ".env" not in staged
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert log.strip() == ""


def test_add_uses_separator_for_dash_prefixed_path(tmp_path):
    _init_repo(tmp_path)
    # A real file whose name starts with "-"; without "--" git would try
    # to parse it as an option instead of a pathspec, and `git add` would
    # silently stage nothing (no error, no exception -- the hook's own
    # broad except wouldn't even catch it).
    weird = tmp_path / "-oops.py"
    weird.write_text("x = 1\n", encoding="utf-8")

    result = _run_hook("-oops.py", tmp_path)

    assert result.returncode == 0
    # The hook stages and commits in one pass, so a successful run leaves
    # nothing staged -- check it actually reached a commit instead.
    log = subprocess.run(
        ["git", "log", "--name-only", "--pretty=format:"],
        cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert "-oops.py" in log
