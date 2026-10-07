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
        print("[VECTOR GATE] BLOCKED — could not verify staged files, failing closed.")
        sys.exit(2)
    staged = result.stdout.strip().splitlines()
except Exception:
    print("[VECTOR GATE] BLOCKED — could not verify staged files, failing closed.")
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

# Syntax gate: block commits that stage unparseable py/js/json/yaml files.
_gate = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "scripts", "precommit_syntax_gate.py")
if os.path.exists(_gate):
    try:
        r = subprocess.run([sys.executable, _gate], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print("[VECTOR GATE] BLOCKED: syntax gate failed:")
            print((r.stdout or "") + (r.stderr or ""))
            sys.exit(2)
    except Exception as exc:
        print(f"[VECTOR GATE] syntax gate skipped: {exc}", file=sys.stderr)

sys.exit(0)
