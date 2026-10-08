"""Compatibility-only delegate to ``core.sandbox``; no independent guarantees."""

from core.sandbox.mount_security import (
    AllowedRoot,
    DEFAULT_BLOCKED_PATTERNS,
    MountAllowlist,
    load_mount_allowlist,
    validate_mount,
    validate_mounts,
)

__all__ = [
    "AllowedRoot",
    "DEFAULT_BLOCKED_PATTERNS",
    "MountAllowlist",
    "load_mount_allowlist",
    "validate_mount",
    "validate_mounts",
]
