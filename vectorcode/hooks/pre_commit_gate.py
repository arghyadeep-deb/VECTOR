# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/pre_commit_gate.py

#!/usr/bin/env python3
"""
VECTOR Pre-Commit Gate — fires before git commit Bash commands.
Blocks commits that include .env files or dangerous patterns.
Exit 2 = block. Exit 0 = allow.
"""
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

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
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "git diff --cached failed")
    staged = result.stdout.strip().splitlines()
except Exception:
    # We already know this command is a git commit; if we can't verify
    # which files are staged, we cannot verify a secret isn't among them
    # -- fail closed rather than silently letting the commit through
    # unchecked.
    print("[VECTOR GATE] BLOCKED: could not verify staged files; failing closed.")
    sys.exit(2)

blocked = []
for f in staged:
    name = os.path.basename(f).lower()
    if name in (".env", ".env.local", ".env.production", ".env.hardened", ".env.development"):
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
