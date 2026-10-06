"""Regression for vectorcode/hooks/file_protection.py (the PreToolUse hook
blocking writes to .env/credentials/production config files).

A malformed JSON hook payload was caught and silently treated as
"allow" (exit 0) instead of "block" (exit 2) -- a classic fail-open on a
security gate. If the hook payload can't be parsed, the target file
can't be verified safe, so the hook must fail closed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "vectorcode" / "hooks" / "file_protection.py"


def _run(stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )


def test_malformed_payload_fails_closed_blocks():
    result = _run("not valid json {{{")
    assert result.returncode == 2


def test_empty_stdin_allows_through():
    # Empty input defaults to {} (valid JSON, no file_path) -- nothing to
    # protect, so this must still be allowed.
    result = _run("")
    assert result.returncode == 0


def test_protected_env_file_is_blocked():
    payload = json.dumps({"file_path": "/repo/.env"})
    result = _run(payload)
    assert result.returncode == 2


def test_unprotected_file_is_allowed():
    payload = json.dumps({"file_path": "/repo/README.md"})
    result = _run(payload)
    assert result.returncode == 0
