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


def get_vector_dir(*args, **kwargs) -> Path:
    """Alias for get_vector_home — matches some legacy callers (accepts ignored args)."""
    return get_vector_home()


# ── Provider base URLs ────────────────────────────────────────────────────────

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
OPENAI_BASE_URL = "https://api.openai.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
OLLAMA_DEFAULT_URL = "http://localhost:11434"


# ── Platform detection ───────────────────────────────────────────────────────

def is_termux() -> bool:
    """Detect if running under Termux (Android)."""
    return bool(os.environ.get("PREFIX", "").startswith("/data/data/com.termux"))


def is_windows() -> bool:
    return os.name == "nt"


def is_macos() -> bool:
    import sys
    return sys.platform == "darwin"


def is_linux() -> bool:
    import sys
    return sys.platform.startswith("linux") and not is_termux()


def get_config_path() -> Path:
    """Alias for get_vector_config_path — back-compat for legacy imports."""
    return get_vector_config_path()


def get_subprocess_home() -> Path:
    """Return the home directory for subprocess execution.

    Used by environment runners to set HOME env var for child processes.
    Defaults to the actual user home (not VECTOR_HOME).
    """
    return Path.home()


def get_log_dir() -> Path:
    """Return the logs directory: ~/.vector/logs."""
    return get_vector_logs_dir()


def get_skills_hub_dir() -> Path:
    """Return the skills hub cache directory."""
    return get_vector_skills_dir() / ".hub"


def display_home() -> str:
    """Alias for display_vector_home."""
    return display_vector_home()


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

