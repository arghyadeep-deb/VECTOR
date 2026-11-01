from __future__ import annotations

__all__ = [
    "CACHE_FILE",
    "DEFAULT_TOOL_DIR",
    "GLOBAL_ENV_FILE",
    "GlobalPath",
    "HISTORY_FILE",
    "LOG_DIR",
    "LOG_FILE",
    "PLANS_DIR",
    "SESSION_LOG_DIR",
    "TRUSTED_FOLDERS_FILE",
    "VECTOR_CA_HOME",
]


from collections.abc import Callable
import os
from pathlib import Path

from core.coding_assistant import VIBE_ROOT


class GlobalPath:
    def __init__(self, resolver: Callable[[], Path]) -> None:
        self._resolver = resolver

    @property
    def path(self) -> Path:
        return self._resolver()


_DEFAULT_VECTOR_CA_HOME = Path.home() / ".vector_ca"


def _get_vibe_home() -> Path:
    if vibe_home := os.getenv("VECTOR_CA_HOME"):
        return Path(vibe_home).expanduser().resolve()
    return _DEFAULT_VECTOR_CA_HOME


VECTOR_CA_HOME = GlobalPath(_get_vibe_home)
GLOBAL_ENV_FILE = GlobalPath(lambda: VECTOR_CA_HOME.path / ".env")
SESSION_LOG_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "logs" / "session")
TRUSTED_FOLDERS_FILE = GlobalPath(lambda: VECTOR_CA_HOME.path / "trusted_folders.toml")
LOG_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "logs")
LOG_FILE = GlobalPath(lambda: VECTOR_CA_HOME.path / "logs" / "vibe.log")
CACHE_FILE = GlobalPath(lambda: VECTOR_CA_HOME.path / "cache.toml")
HISTORY_FILE = GlobalPath(lambda: VECTOR_CA_HOME.path / "vibehistory")
PLANS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "plans")

DEFAULT_TOOL_DIR = GlobalPath(lambda: VIBE_ROOT / "core" / "tools" / "builtins")
