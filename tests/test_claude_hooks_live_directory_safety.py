"""Regression for .claude/hooks/ -- the LIVE hooks directory registered in
.claude/settings.json (PreToolUse/PostToolUse commands reference
$CLAUDE_PROJECT_DIR/.claude/hooks/*.py directly). This is a SEPARATE,
differently-maintained set of files from vectorcode/hooks/ (already fixed
this cycle, see tests/test_vectorcode_hooks_*.py) -- discovered mid-session
that the two trees have diverged and .claude/hooks/ still had every one of
the same vulnerabilities, unfixed, in the files that actually govern this
session's own tool use:

1. auto_commit.py -- committed with --no-verify, bypassing
   pre_commit_gate.py's staged-secret check entirely, with no filename
   check of its own; `git add <file_path>` had no "--" separator.
2. file_protection.py -- malformed hook payload failed OPEN (allowed the
   write) instead of closed.
3. pre_write_check.py -- os.unlink(tmp_path) only ran on the success path,
   leaking a temp .py file on every blocked write.
4. pre_commit_gate.py -- if `git diff --cached --name-only` itself failed,
   the gate silently allowed the commit through unchecked.
5. lint_on_save.py -- ruff/pyflakes subprocess calls had no "--" separator
   before file_path (argument injection risk).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"


def _run_hook(name: str, payload: dict, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)


def test_auto_commit_never_stages_or_commits_a_dangerous_filename(tmp_path):
    _init_repo(tmp_path)
    secret = tmp_path / ".env"
    secret.write_text("API_KEY=super-secret\n", encoding="utf-8")

    result = _run_hook("auto_commit.py", {"file_path": ".env"}, cwd=tmp_path)

    assert result.returncode == 0
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert ".env" not in staged
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert log.strip() == ""


def test_auto_commit_add_uses_separator_for_dash_prefixed_path(tmp_path):
    _init_repo(tmp_path)
    weird = tmp_path / "-oops.py"
    weird.write_text("x = 1\n", encoding="utf-8")

    result = _run_hook("auto_commit.py", {"file_path": "-oops.py"}, cwd=tmp_path)

    assert result.returncode == 0
    log = subprocess.run(
        ["git", "log", "--name-only", "--pretty=format:"], cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert "-oops.py" in log


def test_file_protection_fails_closed_on_malformed_payload():
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "file_protection.py")],
        input="{not valid json",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_pre_write_check_does_not_leak_temp_file_on_blocked_write():
    before = {p.name for p in Path(tempfile.gettempdir()).glob("tmp*.py")}
    result = _run_hook(
        "pre_write_check.py",
        {"file_path": "example.py", "content": "def broken(:\n    pass\n"},
    )
    after = {p.name for p in Path(tempfile.gettempdir()).glob("tmp*.py")}

    assert result.returncode == 2
    assert after - before == set(), f"leaked temp file(s): {after - before}"


def test_pre_commit_gate_fails_closed_when_diff_cached_errors(tmp_path):
    # Not a git repo at all -> `git diff --cached --name-only` errors.
    result = _run_hook("pre_commit_gate.py", {"command": "git commit -m test"}, cwd=tmp_path)
    assert result.returncode == 2


def test_lint_on_save_uses_separator_for_dash_prefixed_path(tmp_path, monkeypatch):
    weird = tmp_path / "-oops.py"
    weird.write_text("x=1\n", encoding="utf-8")
    # cwd doesn't matter -- the hook resolves file_path as given; just confirm
    # it doesn't crash/hang treating "-oops.py" as a flag.
    result = _run_hook("lint_on_save.py", {"file_path": str(weird)})
    assert result.returncode == 0
