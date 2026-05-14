# Ported from GitHub/NousResearch_hermes-agent/repo/hermes_cli/plugins.py
"""VectorCode plugin system."""
try:
    from vectorcode.plugins.loader import discover_plugins, load_plugin, activate_plugin
    from vectorcode.plugins.plugin import Plugin
except ImportError:
    from plugins.loader import discover_plugins, load_plugin, activate_plugin
    try:
        from plugins.plugin import Plugin
    except ImportError:
        Plugin = None

__all__ = ["discover_plugins", "load_plugin", "activate_plugin", "Plugin"]


def init_plugins(engine=None) -> list:
    """Discover and load all plugins. Returns list of loaded modules."""
    loaded = []
    for plugin_path in discover_plugins():
        mod = load_plugin(plugin_path)
        if mod is not None:
            if engine is not None:
                activate_plugin(mod, engine)
            loaded.append(mod)
    return loaded
