"""Install VECTOR's git hooks (currently: pre-commit syntax gate).

Usage:  python scripts/install_git_hooks.py

Writes .git/hooks/pre-commit (POSIX sh shim — Git for Windows runs hooks
through its bundled sh, so this works on Windows too). The shim calls
scripts/precommit_syntax_gate.py with whatever `python` is on PATH.

Idempotent: re-running overwrites the hook. A pre-existing custom pre-commit
hook is backed up to pre-commit.backup once.
"""

import stat
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

HOOK = """#!/bin/sh
# VECTOR pre-commit hook — syntax gate (installed by scripts/install_git_hooks.py)
# Blocks commits containing Python/JS/JSON/YAML files that don't parse,
# and any .env-like file. See scripts/precommit_syntax_gate.py.
python "$(git rev-parse --show-toplevel)/scripts/precommit_syntax_gate.py" || exit 1
"""


def main() -> int:
    hooks_dir = REPO / ".git" / "hooks"
    if not hooks_dir.exists():
        print("ERROR: .git/hooks not found — run from the repo (or git init first)")
        return 1
    target = hooks_dir / "pre-commit"
    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="replace")
        if "VECTOR pre-commit hook" not in existing:
            backup = hooks_dir / "pre-commit.backup"
            if not backup.exists():
                backup.write_text(existing, encoding="utf-8")
                print(f"existing hook backed up to {backup}")
    target.write_text(HOOK, encoding="utf-8", newline="\n")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"installed {target}")
    print("test it:  python scripts/precommit_syntax_gate.py")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
