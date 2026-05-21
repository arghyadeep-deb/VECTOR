# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/auto_commit.py

#!/usr/bin/env python3
"""
VECTOR Auto-Commit Hook — PostToolUse on Edit|Write|MultiEdit
Stages + commits every successful file change so you never lose work.
Silent on failure — never blocks the session.
"""
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

try:
    # Stage the specific file (safer than -A)
    if file_path:
        subprocess.run(["git", "add", file_path], capture_output=True, timeout=10)
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
        subprocess.run(
            ["git", "commit", "-m", msg, "--no-verify"],
            capture_output=True, timeout=15
        )
except Exception:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

sys.exit(0)
