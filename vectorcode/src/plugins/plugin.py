"""VectorCode v3 Plugin — core contract for extensible capabilities."""

from loguru import logger
from typing import Any, Callable, Optional



class ExtensionPoint:
    """A point where plugins can extend system behavior."""
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._handlers: list[Callable] = []

    def register(self, handler: Callable):
        self._handlers.append(handler)
        return self

    async def execute(self, *args, **kwargs) -> list[Any]:
        results = []
        for h in self._handlers:
            try:
                r = h(*args, **kwargs)
                if hasattr(r, "__await__"):
                    r = await r
                results.append(r)
            except Exception as e:
                logger.warning(f"Extension point {self.name} handler failed: {e}")
        return results


class Plugin:
    def __init__(self, plugin_id: str, name: str, version: str = "1.0.0",
                 description: str = "", dependencies: Optional[list[str]] = None):
        self.id = plugin_id
        self.name = name
        self.version = version
        self.description = description
        self.dependencies = dependencies or []
        self._initialized = False
        self._extension_points: dict[str, ExtensionPoint] = {}

    def register_extension(self, point: ExtensionPoint):
        self._extension_points[point.name] = point

    def get_extension(self, name: str) -> Optional[ExtensionPoint]:
        return self._extension_points.get(name)

    def list_extensions(self) -> list[str]:
        return list(self._extension_points.keys())

    async def initialize(self, config: Optional[dict] = None):
        self._initialized = True
        logger.info(f"Plugin {self.id} v{self.version} initialized")

    async def shutdown(self):
        self._initialized = False
        logger.info(f"Plugin {self.id} shutdown")


class PluginManager:
    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._global_extensions: dict[str, ExtensionPoint] = {}

    def register(self, plugin: Plugin):
        self._plugins[plugin.id] = plugin
        for name, ep in plugin._extension_points.items():
            if name not in self._global_extensions:
                self._global_extensions[name] = ExtensionPoint(name)
            for handler in ep._handlers:
                self._global_extensions[name].register(handler)
        logger.info(f"Registered plugin: {plugin.id}")

    def get(self, plugin_id: str) -> Optional[Plugin]:
        return self._plugins.get(plugin_id)

    def list(self) -> list[Plugin]:
        return list(self._plugins.values())

    def get_extension(self, name: str) -> Optional[ExtensionPoint]:
        return self._global_extensions.get(name)

    async def initialize_all(self, configs: Optional[dict[str, dict]] = None):
        configs = configs or {}
        for pid, plugin in self._plugins.items():
            await plugin.initialize(configs.get(pid))

    async def shutdown_all(self):
        for plugin in self._plugins.values():
            await plugin.shutdown()
