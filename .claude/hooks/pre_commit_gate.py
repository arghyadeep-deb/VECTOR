#!/usr/bin/env python3
"""
VECTOR Pre-Commit Gate — fires before git commit Bash commands.
Blocks commits that include .env files or dangerous patterns.
Exit 2 = block. Exit 0 = allow.
"""
import json
import os
import subprocess
import sys

try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    data = {}

command = data.get("command", "")

# Only intercept git commit commands
if "git commit" not in command:
    sys.exit(0)

# Check staged files for dangerous items
try:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, timeout=10
    )
    staged = result.stdout.strip().splitlines()
except Exception:
    sys.exit(0)

blocked = []
for f in staged:
    name = os.path.basename(f).lower()
    if name in (".env", ".env.local", ".env.production", ".env.development"):
        blocked.append(f)
    elif name.endswith(".env"):
        blocked.append(f)
    elif name in ("google_credentials.json", "service_account.json", "credentials.json"):
        blocked.append(f)

if blocked:
    print(f"[VECTOR GATE] BLOCKED: Dangerous files staged for commit:")
    for f in blocked:
        print(f"  ❌ {f}")
    print("Unstage them with: git reset HEAD <file>")
    sys.exit(2)

sys.exit(0)
