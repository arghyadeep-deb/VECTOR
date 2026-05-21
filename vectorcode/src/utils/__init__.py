"""VectorCode utilities package.
from loguru import logger

Re-exports the top-level utils.py contents so `from utils import X` works
whether callers expect the package or the legacy single-file module.
"""
import sys
from pathlib import Path as _Path

# Ensure parent dir is on sys.path so we can find utils.py
_parent = str(_Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# Import and re-export EVERYTHING from utils.py (top-level VectorCode module)
try:
    import importlib.util as _ilu
    _utils_py = _Path(__file__).parent.parent / "utils.py"
    if _utils_py.exists():
        _spec = _ilu.spec_from_file_location("_utils_module", _utils_py)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        # Copy all public names into this package namespace
        for _name in dir(_mod):
            if not _name.startswith("_"):
                globals()[_name] = getattr(_mod, _name)
except Exception as _sve:
    logger.debug("[VECTOR][utils.__init__] suppressed Exception: %s", _sve)

# Also import from local core.py for our additions
try:
    from .core import (
        is_truthy_value, env_var_enabled, env_int,
        safe_json_loads, atomic_json_write,
        normalize_proxy_url, base_url_hostname, base_url_host_matches,
    )
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
