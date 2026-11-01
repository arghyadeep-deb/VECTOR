# Ported from GitHub/VectorCode_vectorcode/repo/vector_cli/plugins.py (runtime parts)
"""Plugin discovery and loading for VectorCode."""
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

_PLUGIN_DIRS = [
    Path.home() / ".vectorcode" / "plugins",
    Path(__file__).parent / "builtin",
]


def discover_plugins(extra_dirs: Optional[List[Path]] = None) -> List[Path]:
    """Return list of plugin directories found in all plugin search paths."""
    dirs = list(_PLUGIN_DIRS)
    if extra_dirs:
        dirs.extend(extra_dirs)
    found = []
    for d in dirs:
        if not d.exists():
            continue
        for item in sorted(d.iterdir()):
            if item.is_dir() and (item / "plugin.toml").exists():
                found.append(item)
            elif item.is_file() and item.suffix == ".py" and item.stem != "__init__":
                found.append(item)
    return found


def load_plugin(plugin_path: Path) -> Optional[Any]:
    """Load a plugin from a directory (with plugin.toml) or a .py file."""
    try:
        if plugin_path.is_dir():
            return _load_package_plugin(plugin_path)
        elif plugin_path.suffix == ".py":
            return _load_file_plugin(plugin_path)
    except Exception as e:
        logger.warning(f"Failed to load plugin {plugin_path}: {e}")
    return None


def _load_package_plugin(plugin_dir: Path) -> Optional[Any]:
    manifest = _read_manifest(plugin_dir / "plugin.toml")
    name = manifest.get("plugin", {}).get("name", plugin_dir.name)
    init = plugin_dir / "__init__.py"
    if not init.exists():
        logger.warning(f"Plugin {name} has no __init__.py")
        return None
    spec = importlib.util.spec_from_file_location(f"vectorcode_plugin_{name}", init)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    logger.info(f"Loaded plugin: {name}")
    return mod


def _load_file_plugin(plugin_file: Path) -> Optional[Any]:
    name = plugin_file.stem
    spec = importlib.util.spec_from_file_location(f"vectorcode_plugin_{name}", plugin_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    logger.info(f"Loaded plugin: {name}")
    return mod


def _read_manifest(toml_path: Path) -> dict:
    if not toml_path.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return {}
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def activate_plugin(plugin_mod: Any, engine: Any) -> None:
    """Call plugin's activate() if it exists, passing the engine."""
    if hasattr(plugin_mod, "activate"):
        try:
            plugin_mod.activate(engine)
        except Exception as e:
            logger.warning(f"Plugin activate() failed: {e}")
