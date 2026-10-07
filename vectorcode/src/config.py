"""VectorCode TOML-based configuration system.

Global config : ~/.config/vector/config.toml
Project config: <project>/vector.toml  (overrides global)
Model registry: ~/.config/vector/model-registry.json  (capability cache)
Data dir      : ~/.vector/  (sessions, memory.md, audit.log)
"""

import sys
import json
from copy import deepcopy

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

from loguru import logger
from pathlib import Path
from vectorcode.src.utils import atomic_json_write

# ── Canonical paths ───────────────────────────────────────────────────────────

GLOBAL_CONFIG_DIR   = Path.home() / ".config" / "vector"
GLOBAL_CONFIG_PATH  = GLOBAL_CONFIG_DIR / "config.toml"
MODEL_REGISTRY_PATH = GLOBAL_CONFIG_DIR / "model-registry.json"
VECTOR_DATA_DIR     = Path.home() / ".vector"
SESSION_DIR         = VECTOR_DATA_DIR / "sessions"
MEMORY_MD_PATH      = VECTOR_DATA_DIR / "memory.md"
AUDIT_LOG_PATH      = VECTOR_DATA_DIR / "audit.log"

# ── Defaults (mirrors spec §10.2) ─────────────────────────────────────────────

_DEFAULTS: dict = {
    "model": {
        "default": "ollama/vector-focus",
        "fast":    "ollama/vector-fast",
        "local":   "ollama/vector-focus",
    },
    "providers": {
        "ollama": {"base_url": "http://localhost:11434"},
    },
    "agent": {
        "max_iterations":         50,
        "think_budget_tokens":    8000,
        "auto_compact_threshold": 0.85,
        "auto_approve_reads":     True,
        "auto_approve_bash":      False,
    },
    "permissions": {
        "mode":              "standard",
        "allow_bash":        [],
        "deny_bash":         ["rm -rf"],
        "allow_write_paths": [],
        "deny_write_paths":  [".env", "*.pem"],
    },
    "hooks": {
        "after_write_file":  [],
        "before_bash":       [],
        "after_git_commit":  [],
    },
    "ui": {
        "theme":               "dark",
        "show_diff_panel":     True,
        "show_token_counter":  True,
        "syntax_highlight":    True,
    },
}

_DEFAULT_TOML_TEMPLATE = """\
# Vector Code Configuration
# ~/.config/vector/config.toml

[model]
default = "ollama/vector-focus"
fast    = "ollama/vector-fast"
local   = "ollama/vector-focus"

[providers.ollama]
base_url = "http://localhost:11434"

# Uncomment and fill in to use cloud providers:
# [providers.anthropic]
# api_key_env = "ANTHROPIC_API_KEY"

# [providers.openai]
# api_key_env = "OPENAI_API_KEY"

# [providers.google]
# api_key_env = "GOOGLE_API_KEY"

# [providers.groq]
# api_key_env = "GROQ_API_KEY"

# [providers.mistral]
# api_key_env = "MISTRAL_API_KEY"

[agent]
max_iterations         = 50
think_budget_tokens    = 8000
auto_compact_threshold = 0.85
auto_approve_reads     = true
auto_approve_bash      = false

[permissions]
mode             = "standard"
deny_bash        = ["rm -rf"]
deny_write_paths = [".env", "*.pem"]

[ui]
theme              = "dark"
show_diff_panel    = true
show_token_counter = true
syntax_highlight   = true
"""


def _deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    if tomllib is None:
        logger.warning(f"[VECTOR][config] tomllib unavailable — {path} skipped")
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[VECTOR][config] failed to parse {path}: {e}")
        return {}


class VectorConfig:
    """
    Merged TOML configuration for VectorCode.
    Load order: built-in defaults → global config → project config.
    """

    def __init__(self, project_dir: Path | None = None) -> None:
        cfg = deepcopy(_DEFAULTS)
        cfg = _deep_merge(cfg, _load_toml(GLOBAL_CONFIG_PATH))
        if project_dir:
            cfg = _deep_merge(cfg, _load_toml(project_dir / "vector.toml"))
        self._cfg = cfg
        self._project_dir = project_dir

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, *keys, default=None):
        node = self._cfg
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def __getitem__(self, key: str):
        if key in self._cfg:
            return self._cfg[key]
        compat_defaults = {
            "version": "1.0.0",
            "env": "dev",
            "debug": False,
            "ollama_host": "http://127.0.0.1:11434",
            "data_dir": str(Path.home() / ".vector"),
            "models": {
                "ambient": "vector-ambient",
                "focus": "vector-focus",
                "multilingual": "vector-multilingual",
                "reasoning": "vector-reasoning",
                "coder": "vector-coder",
                "dev": "vector-dev",
                "r1": "vector-r1",
                "embed": "nomic-embed-text",
                "chairman": "vector-chairman",
            },
            "permission": {"green": [], "yellow": [], "red": []},
            "api_keys": {},
            "browser": {},
            "blog": {},
            "resilience": {},
        }
        if key in compat_defaults:
            return compat_defaults[key]
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self._cfg

    @property
    def default_model(self) -> str:
        return self.get("model", "default", default="ollama/vector-focus")

    @property
    def fast_model(self) -> str:
        return self.get("model", "fast", default="ollama/vector-fast")

    @property
    def local_model(self) -> str:
        return self.get("model", "local", default="ollama/vector-focus")

    @property
    def max_iterations(self) -> int:
        return int(self.get("agent", "max_iterations", default=50))

    @property
    def permission_mode(self) -> str:
        return self.get("permissions", "mode", default="standard")

    @property
    def auto_compact_threshold(self) -> float:
        return float(self.get("agent", "auto_compact_threshold", default=0.85))

    @property
    def auto_approve_reads(self) -> bool:
        return bool(self.get("agent", "auto_approve_reads", default=True))

    @property
    def auto_approve_bash(self) -> bool:
        return bool(self.get("agent", "auto_approve_bash", default=False))

    def provider_config(self, provider: str) -> dict:
        return self.get("providers", provider, default={})

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def write_global_default(self) -> None:
        """Write default config.toml to ~/.config/vector/ if absent."""
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not GLOBAL_CONFIG_PATH.exists():
            GLOBAL_CONFIG_PATH.write_text(_DEFAULT_TOML_TEMPLATE, encoding="utf-8")
            logger.info(f"[VECTOR][config] default config written to {GLOBAL_CONFIG_PATH}")


# ── Model capability registry ─────────────────────────────────────────────────

class ModelRegistry:
    """Persistent cache of probed model capabilities (~/.config/vector/model-registry.json)."""

    def __init__(self) -> None:
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if MODEL_REGISTRY_PATH.exists():
            try:
                self._data = json.loads(MODEL_REGISTRY_PATH.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _save(self) -> None:
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        atomic_json_write(MODEL_REGISTRY_PATH, self._data)

    def get(self, model_id: str) -> dict | None:
        return self._data.get(model_id)

    def set(self, model_id: str, caps: dict) -> None:
        self._data[model_id] = caps
        self._save()
        logger.debug(f"[VECTOR][config] cached capabilities for {model_id}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = VectorConfig()
    assert cfg.default_model.startswith("ollama/")
    assert cfg.max_iterations == 50
    assert cfg.permission_mode == "standard"
    assert isinstance(cfg.provider_config("ollama"), dict)
    reg = ModelRegistry()
    reg.set("ollama/test-model", {"context_window": 4096, "tool_use": False})
    assert reg.get("ollama/test-model")["context_window"] == 4096
    print("config.py OK")


