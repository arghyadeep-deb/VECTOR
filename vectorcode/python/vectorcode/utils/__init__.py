"""VectorCode utilities package."""
# Re-export common utilities so `from utils import X` works
try:
    from vectorcode.utils.core import (
        is_truthy_value,
        env_var_enabled,
        env_int,
        safe_json_loads,
        atomic_json_write,
        normalize_proxy_url,
        base_url_hostname,
        base_url_host_matches,
    )
except ImportError:
    pass

# Also re-export from top-level utils.py (legacy)
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils import (  # noqa: F811
        is_truthy_value,
        env_var_enabled,
        atomic_json_write,
        safe_json_loads,
        normalize_proxy_url,
        base_url_hostname,
        base_url_host_matches,
        env_int,
        env_bool,
        atomic_yaml_write,
        normalize_proxy_env_vars,
    )
except ImportError:
    pass
