"""Report tracked files that look like runtime artifacts or secrets.

This script is intentionally non-destructive. It only reads `git ls-files`
and prints cleanup candidates.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.repo_hygiene import audit_repo_paths


def _tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    findings = audit_repo_paths(_tracked_files())
    counts = Counter(finding.category for finding in findings)

    print("VECTOR repo hygiene audit")
    print(f"findings={len(findings)} runtime={counts['runtime']} sensitive={counts['sensitive']}")

    for finding in findings:
        print(
            f"{finding.severity}\t{finding.category}\t{finding.path}\t{finding.reason}"
        )

    return 1 if any(finding.category == "sensitive" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
