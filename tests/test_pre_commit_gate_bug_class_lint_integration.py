"""Regression for .claude/hooks/pre_commit_gate.py's new bug-class-lint
wiring (gap 2 of the post-audit improvement plan): a staged .py file with a
banned import (flask/pickle/requests) must block the commit, and a clean
file must not.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "pre_commit_gate.py"


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)


def _run_gate(tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"command": "git commit -m test"}),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )


def test_staged_banned_import_blocks_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "bad.py").write_text("import requests\n", encoding="utf-8")
    subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, check=True)

    result = _run_gate(tmp_path)

    assert result.returncode == 2
    assert "bug-class lint" in result.stdout.lower() or "bug-class lint" in result.stderr.lower()


def test_staged_clean_file_does_not_block_commit(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "ok.py").write_text("import httpx\n\nx = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "ok.py"], cwd=tmp_path, check=True)

    result = _run_gate(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
