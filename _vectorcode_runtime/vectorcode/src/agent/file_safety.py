"""Shared file safety rules used by both tools and ACP shims."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _vector_home_path() -> Path:
    """Resolve the active VECTOR_HOME (profile-aware) without circular imports."""
    try:
        from vector_constants import get_vector_home  # local import to avoid cycles
        return get_vector_home()
    except Exception:
        return Path(os.path.expanduser("~/.vectorcode"))


def _normalized_path(path: str) -> str:
    """Resolve a path using the platform's filesystem case semantics."""
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def build_write_denied_paths(home: str) -> set[str]:
    """Return exact sensitive paths that must never be written."""
    vector_home = _vector_home_path()
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
            os.path.join(home, ".zprofile"),
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
    """Return sensitive directory prefixes that must never be written."""
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


def get_safe_write_root() -> Optional[str]:
    """Return the resolved VECTOR_WRITE_SAFE_ROOT path, or None if unset."""
    root = os.environ.get("VECTOR_WRITE_SAFE_ROOT", "")
    if not root:
        return None
    try:
        return _normalized_path(root)
    except Exception:
        return None


def is_write_denied(path: str) -> bool:
    """Return True if path is blocked by the write denylist or safe root."""
    home = _normalized_path("~")
    resolved = _normalized_path(str(path))

    if resolved in build_write_denied_paths(home):
        return True
    for prefix in build_write_denied_prefixes(home):
        if resolved.startswith(prefix):
            return True

    safe_root = get_safe_write_root()
    if safe_root and not (resolved == safe_root or resolved.startswith(safe_root + os.sep)):
        return True

    return False


def get_read_block_error(path: str) -> Optional[str]:
    """Return an error message when a read targets internal VectorCode cache files."""
    resolved = Path(path).expanduser().resolve()
    vector_home = _vector_home_path().resolve()
    blocked_dirs = [
        vector_home / "skills" / ".hub" / "index-cache",
        vector_home / "skills" / ".hub",
    ]
    for blocked in blocked_dirs:
        try:
            resolved.relative_to(blocked)
        except ValueError:
            continue
        return (
            f"Access denied: {path} is an internal VectorCode cache file "
            "and cannot be read directly to prevent prompt injection. "
            "Use the skills_list or skill_view tools instead."
        )
    return None
