"""QE Security Bridge — ACL for V3 security (path validation, safe exec)."""

from pathlib import Path
from typing import Optional


class QESecurityBridge:
    def __init__(self, allowed_paths: Optional[list[str]] = None):
        self._allowed = allowed_paths or []

    def validate_path(self, path: str) -> bool:
        if not self._allowed: return True
        p = Path(path).resolve()
        return any(p.is_relative_to(Path(a).resolve()) for a in self._allowed)

    def validate_command(self, command: str) -> bool:
        blocked = ["rm -rf", "> /dev/", "| sh", "sudo", "chmod 777"]
        return not any(b in command for b in blocked)
