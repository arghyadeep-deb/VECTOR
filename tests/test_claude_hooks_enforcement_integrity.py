"""Regression for gap 7 of the post-audit improvement plan ("enforcement
integrity / bypass resistance"): two places where a configured control
could be silently routed around instead of actually enforced.

1. .claude/hooks/pre_commit_gate.py's syntax-gate subprocess call caught
   any exception (or a missing gate script) and just printed "skipped",
   falling through to allow (exit 0). A syntax gate that cannot run has
   NOT verified anything -- that must fail closed, the same as every
   other security-relevant check fixed this cycle.

2. .claude/hooks/auto_commit.py committed with `git commit --no-verify`,
   which bypasses the real git-native pre-commit hook
   (.git/hooks/pre-commit -> scripts/precommit_syntax_gate.py) -- NOT
   pre_commit_gate.py, which never sees this commit at all since
   auto_commit.py calls subprocess directly, not through Claude's Bash
   tool. --no-verify meant an unparseable py/js/json/yaml file (or
   another dangerous-named file) could be auto-committed with zero
   syntax verification.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)


def test_pre_commit_gate_fails_closed_when_syntax_gate_script_missing(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "ok.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "ok.txt"], cwd=tmp_path, check=True)

    # Run pre_commit_gate.py from a fake repo root three levels under
    # tmp_path/a/b/hooks so its own path math points at a nonexistent
    # scripts/precommit_syntax_gate.py -- simulating the gate script being
    # missing or moved.
    fake_hooks_dir = tmp_path / "a" / "b" / "hooks"
    fake_hooks_dir.mkdir(parents=True)
    gate_src = (HOOKS_DIR / "pre_commit_gate.py").read_text(encoding="utf-8")
    (fake_hooks_dir / "pre_commit_gate.py").write_text(gate_src, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(fake_hooks_dir / "pre_commit_gate.py")],
        input=json.dumps({"command": "git commit -m test"}),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 2, (
        f"expected fail-closed (exit 2) when the syntax gate script is missing, got "
        f"{result.returncode}: {result.stdout}{result.stderr}"
    )


def test_auto_commit_no_longer_passes_no_verify():
    # Check actual code lines only -- a comment may legitimately mention the
    # flag name while explaining why it was removed.
    code_lines = [
        line for line in (HOOKS_DIR / "auto_commit.py").read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ]
    offending = [line for line in code_lines if "--no-verify" in line]
    assert not offending, (
        "auto_commit.py must not bypass the real git-native pre-commit hook "
        f"(scripts/precommit_syntax_gate.py) -- found in code: {offending}"
    )


def test_auto_commit_respects_real_precommit_hook_rejection(tmp_path):
    _init_repo(tmp_path)

    # Install a minimal real git-native pre-commit hook that always rejects,
    # simulating precommit_syntax_gate.py catching a bad file.
    hooks_native_dir = tmp_path / ".git" / "hooks"
    pre_commit = hooks_native_dir / "pre-commit"
    pre_commit.write_text("#!/bin/sh\necho 'REJECTED' >&2\nexit 1\n", encoding="utf-8")
    pre_commit.chmod(0o755)

    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def broken(:\n", encoding="utf-8")

    hook_env_payload = json.dumps({"file_path": str(bad_file)})
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "auto_commit.py")],
        input=hook_env_payload,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0  # the hook itself never blocks the session

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert log.strip() == "", (
        "auto_commit.py committed despite the native pre-commit hook rejecting it -- "
        "--no-verify must have been reintroduced"
    )
    # The file should still be staged, just not committed.
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert "bad.py" in staged
