"""Regression for vectorcode/hooks/pre_commit_gate.py:

If `git diff --cached --name-only` itself failed (non-zero exit, or the
subprocess call raised), the gate silently allowed the commit through
(sys.exit(0)) without ever checking whether a secret file was staged --
even though the command was already confirmed to be a `git commit`. A
verification failure must not be treated as "nothing dangerous found."
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "vectorcode" / "hooks" / "pre_commit_gate.py"


def _run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"command": command})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def test_blocks_commit_when_staged_file_check_fails(tmp_path):
    # Not a git repo -- `git diff --cached` will fail with a non-zero exit.
    result = _run_hook("git commit -m test", tmp_path)
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout


def test_allows_non_commit_commands_even_outside_a_repo(tmp_path):
    result = _run_hook("ls -la", tmp_path)
    assert result.returncode == 0
