#!/usr/bin/env python3
"""
VECTOR Auto-Commit Hook — PostToolUse on Edit|Write|MultiEdit
Stages + commits every successful file change so you never lose work.
Silent on failure — never blocks the session.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    data = {}

file_path = (
    data.get("file_path")
    or data.get("tool_input", {}).get("file_path")
    or ""
)

# Skip non-source files — don't auto-commit screenshots, temp files, logs
SKIP_PATTERNS = [".png", ".jpg", ".log", ".tmp", ".pyc", "__pycache__", ".screenshots"]
if any(s in file_path for s in SKIP_PATTERNS):
    sys.exit(0)

# Never auto-stage/auto-commit secret-bearing files. This hook commits via
# a raw subprocess call, not Claude's Bash tool, so .claude/hooks/
# pre_commit_gate.py (a PreToolUse-on-Bash hook) never sees this commit
# regardless of --no-verify -- it needs its own denylist rather than
# relying on that gate to ever run here.
DANGEROUS_NAMES = {
    ".env", ".env.local", ".env.production", ".env.hardened", ".env.development",
    "google_credentials.json", "service_account.json", "credentials.json",
}
_basename = os.path.basename(file_path).replace("\\", "/").split("/")[-1].lower()
if _basename in DANGEROUS_NAMES or _basename.endswith(".env"):
    sys.exit(0)

try:
    # Stage the specific file (safer than -A). "--" stops git from treating a
    # dash-prefixed file_path as an option.
    if file_path:
        subprocess.run(["git", "add", "--", file_path], capture_output=True, timeout=10)
    else:
        subprocess.run(["git", "add", "-A"], capture_output=True, timeout=10)

    # Only commit if there are staged changes
    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True, timeout=10
    )
    if diff_check.returncode != 0:
        ts = datetime.now().strftime("%H:%M:%S")
        msg = f"auto: {file_path.split('/')[-1].split(chr(92))[-1] or 'changes'} [{ts}]"
        # No --no-verify: this lets the real git-native pre-commit hook
        # (scripts/precommit_syntax_gate.py, installed at .git/hooks/
        # pre-commit) actually run and block an unparseable py/js/json/yaml
        # file or another dangerous-named file from being committed. A
        # rejected commit here just leaves the change staged, uncommitted --
        # consistent with "silent on failure, never blocks the session."
        subprocess.run(
            ["git", "commit", "-m", msg],
            capture_output=True, timeout=30
        )
except Exception as exc:
    print(f"[VECTOR AUTO-COMMIT] skipped: {exc}", file=sys.stderr)

sys.exit(0)
