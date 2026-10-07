# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/lint_on_save.py

#!/usr/bin/env python3
"""
VECTOR Lint-on-Save Hook — fires after every Edit/Write on a Python file.
Runs ruff (fast linter) to catch issues immediately.
Non-blocking: prints warnings but never exits 2 (doesn't stop the session).
"""
import json
import os
import subprocess
import sys

try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    data = {}

file_path = data.get("file_path", os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", ""))

if not file_path or not file_path.endswith(".py"):
    sys.exit(0)

if not os.path.exists(file_path):
    sys.exit(0)

# Try ruff first, fall back to pyflakes. "--" prevents a file_path that
# starts with "-" from being parsed as an option by either linter.
linters = [
    ["ruff", "check", "--select=E,F,W", "--quiet", "--", file_path],
    ["python", "-m", "pyflakes", "--", file_path],
]

for cmd in linters:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0 and result.stdout.strip():
            print(f"[VECTOR LINT] {file_path}:\n{result.stdout.strip()[:500]}")
        break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        continue

sys.exit(0)
