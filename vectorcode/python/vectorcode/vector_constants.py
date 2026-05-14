"""VectorCode home directory constants — VectorCode implementation.

Import-safe: no heavy dependencies. All other VectorCode modules that need
canonical paths should import from here instead of hardcoding ~/.vector.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent))                       # vectorcode package

try:
    from core.config import CONFIG  # noqa: F401  (used by callers who import this module)
except ImportError:
    CONFIG = {}


# ── Home resolution ───────────────────────────────────────────────────────────


def get_vector_home() -> Path:
    """Return the VectorCode home directory.

    Respects the VECTOR_HOME environment variable; falls back to ~/.vector.
    """
    val = os.environ.get("VECTOR_HOME", "").strip()
    return Path(val) if val else Path.home() / ".vector"


def get_vector_skills_dir() -> Path:
    """Return the user skills directory: ~/.vector/skills (or $VECTOR_HOME/skills)."""
    return get_vector_home() / "skills"


def get_vector_sessions_dir() -> Path:
    """Return the sessions directory: ~/.vector/sessions."""
    return get_vector_home() / "sessions"


def get_vector_memory_path() -> Path:
    """Return the persistent memory file path: ~/.vector/memory.md."""
    return get_vector_home() / "memory.md"


def get_vector_config_path() -> Path:
    """Return the global config file path: ~/.config/vector/config.toml."""
    return Path.home() / ".config" / "vector" / "config.toml"


def display_vector_home() -> str:
    """Return a human-friendly string for the VectorCode home directory."""
    home = get_vector_home()
    home_str = str(home)
    user_home = str(Path.home())
    if home_str.startswith(user_home):
        return "~" + home_str[len(user_home):]
    return home_str


def get_vector_data_dir() -> Path:
    """Return the data subdirectory: ~/.vector/data."""
    return get_vector_home() / "data"


def get_vector_logs_dir() -> Path:
    """Return the logs subdirectory: ~/.vector/logs."""
    return get_vector_home() / "logs"


def get_config_path() -> Path:
    """Alias for get_vector_config_path — back-compat for legacy imports."""
    return get_vector_config_path()


# ── Module-level singletons (re-evaluated each import so env overrides work) ──

VECTOR_HOME = get_vector_home()
VECTOR_SKILLS_DIR = get_vector_skills_dir()
VECTOR_SESSIONS_DIR = get_vector_sessions_dir()
VECTOR_MEMORY_PATH = get_vector_memory_path()


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    home = get_vector_home()
    assert str(home).endswith(".vector") or "VECTOR_HOME" in os.environ, \
        f"unexpected home: {home}"

    skills = get_vector_skills_dir()
    assert skills == home / "skills", f"skills mismatch: {skills}"

    sessions = get_vector_sessions_dir()
    assert sessions == home / "sessions", f"sessions mismatch: {sessions}"

    mem = get_vector_memory_path()
    assert mem == home / "memory.md", f"memory path mismatch: {mem}"

    cfg = get_vector_config_path()
    assert cfg.name == "config.toml", f"config path mismatch: {cfg}"

    # Module-level constants must match function results
    assert VECTOR_HOME == home
    assert VECTOR_SKILLS_DIR == skills
    assert VECTOR_SESSIONS_DIR == sessions
    assert VECTOR_MEMORY_PATH == mem

    print("vector_constants.py OK")

