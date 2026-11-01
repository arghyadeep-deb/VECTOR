# Ported from GitHub/VectorCode_vectorcode/repo/agent/file_safety.py
"""File write/read safety rules."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional


def _vector_home() -> Path:
    return Path(os.path.expanduser(os.environ.get("VECTOR_HOME", "~/.vectorcode")))


def _normalized_path(path: str) -> str:
    """Resolve paths using the host filesystem's case semantics."""
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def build_write_denied_paths(home: str) -> set[str]:
    vector_home = _vector_home()
    return {
        _normalized_path(p)
        for p in [
            os.path.join(home, ".ssh", "authorized_keys"),
            os.path.join(home, ".ssh", "id_rsa"),
            os.path.join(home, ".ssh", "id_ed25519"),
            os.path.join(home, ".ssh", "config"),
            str(vector_home / ".env"),
            os.path.join(home, ".bashrc"),
            os.path.join(home, ".zshrc"),
            os.path.join(home, ".profile"),
            os.path.join(home, ".bash_profile"),
            os.path.join(home, ".netrc"),
            os.path.join(home, ".pgpass"),
            os.path.join(home, ".npmrc"),
            os.path.join(home, ".pypirc"),
            "/etc/sudoers",
            "/etc/passwd",
            "/etc/shadow",
        ]
    }


def build_write_denied_prefixes(home: str) -> list[str]:
    return [
        _normalized_path(p) + os.sep
        for p in [
            os.path.join(home, ".ssh"),
            os.path.join(home, ".aws"),
            os.path.join(home, ".gnupg"),
            os.path.join(home, ".kube"),
            "/etc/sudoers.d",
            "/etc/systemd",
            os.path.join(home, ".docker"),
            os.path.join(home, ".azure"),
            os.path.join(home, ".config", "gh"),
        ]
    ]


def is_write_denied(path: str) -> bool:
    """Return True if path is blocked by the write denylist."""
    home = _normalized_path("~")
    resolved = _normalized_path(str(path))
    if resolved in build_write_denied_paths(home):
        return True
    for prefix in build_write_denied_prefixes(home):
        if resolved.startswith(prefix):
            return True
    safe_root = os.environ.get("VECTOR_WRITE_SAFE_ROOT", "")
    if safe_root:
        safe_root = _normalized_path(safe_root)
        if not (resolved == safe_root or resolved.startswith(safe_root + os.sep)):
            return True
    return False


def is_safe_to_read(path: str) -> bool:
    """Return True if path is safe to read (not an internal cache file)."""
    resolved = Path(path).expanduser().resolve()
    vector_home = _vector_home().resolve()
    blocked_dirs = [
        vector_home / "skills" / ".hub" / "index-cache",
        vector_home / "skills" / ".hub",
    ]
    for blocked in blocked_dirs:
        try:
            resolved.relative_to(blocked)
            return False
        except ValueError:
            continue
    return True


_BLOCKED_DEVICE_PATHS = frozenset({
    "/dev/zero", "/dev/random", "/dev/urandom", "/dev/full",
    "/dev/stdin", "/dev/tty", "/dev/console",
    "/dev/stdout", "/dev/stderr",
    "/dev/fd/0", "/dev/fd/1", "/dev/fd/2",
})
