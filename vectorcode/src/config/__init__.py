"""VectorCode config package — environment detection and configuration utilities."""
from .env_detector import Environment, EnvInfo, detect, get_env

__all__ = ["Environment", "EnvInfo", "detect", "get_env"]


# `config/` (this package) and `config.py` (VectorConfig, SESSION_DIR, GLOBAL_CONFIG_PATH ...) share a name,
# and a package always wins over a same-named module -- so `from config import SESSION_DIR` / `VectorConfig`
# raised ImportError (breaking `vector sessions` and `vector models`). Re-export the module's public names here.
def _reexport_config_module() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "config.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("vectorcode_config_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in vars(module).items():
        if not name.startswith("__") and name not in globals():
            globals()[name] = value
            __all__.append(name)


_reexport_config_module()
