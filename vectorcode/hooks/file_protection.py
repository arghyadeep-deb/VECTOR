# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/file_protection.py

#!/usr/bin/env python3
"""
VECTOR File Protection Hook — PreToolUse on Edit|Write|MultiEdit
Blocks any write to .env files, production configs, DB migrations, credentials.
Exit 2 = BLOCKED. Exit 0 = allowed.
"""
import json
import re
import sys

try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    # Malformed hook payload means we cannot verify the target file is
    # safe -- fail closed (block) rather than silently allowing the
    # write through unchecked.
    print("[VECTOR GATE] BLOCKED — could not parse hook payload; failing closed.")
    sys.exit(2)

file_path = (
    data.get("file_path")
    or data.get("tool_input", {}).get("file_path")
    or ""
)

PROTECTED = [
    r"\.env$",
    r"\.env\.",
    r"[/\\]\.env",
    r"supabase[/\\]migrations",
    r"production\.config",
    r"google_credentials\.json",
    r"service_account\.json",
    r"credentials\.json",
    r"secrets\.(json|yaml|yml|toml)",
    r"vector\.db$",
    r"memory\.db$",
]

for pattern in PROTECTED:
    if re.search(pattern, file_path, re.IGNORECASE):
        print(f"[VECTOR GATE] BLOCKED — protected file: {file_path}")
        print("To override: manually edit this file outside VectorCode.")
        sys.exit(2)

sys.exit(0)
