# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/auto_commit.py

#!/usr/bin/env python3
"""
VECTOR Auto-Commit Hook — PostToolUse on Edit|Write|MultiEdit
Stages + commits every successful file change so you never lose work.
Silent on failure — never blocks the session.
"""
from loguru import logger
import json
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

# This hook commits with --no-verify, bypassing pre_commit_gate.py's
# staged-secret check entirely -- never auto-commit a filename that gate
# would itself block, or a secret could be written straight into git
# history with no gate ever seeing it.
_basename = (file_path.split("/")[-1].split(chr(92))[-1] or "").lower()
DANGEROUS_NAMES = {
    ".env", ".env.local", ".env.production", ".env.hardened", ".env.development",
    "google_credentials.json", "service_account.json", "credentials.json",
}
if _basename in DANGEROUS_NAMES or _basename.endswith(".env"):
    sys.exit(0)

try:
    # Stage the specific file (safer than -A). "--" prevents a file_path
    # that starts with "-" from being parsed as a git option.
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
        msg = f"auto: {_basename or 'changes'} [{ts}]"
        subprocess.run(
            ["git", "commit", "-m", msg, "--no-verify"],
            capture_output=True, timeout=15
        )
except Exception:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

sys.exit(0)
