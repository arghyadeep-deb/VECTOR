"""
HookRegistry — VectorCode VC-5.

17 named hooks with priority ordering and per-handler timeout protection.
Each handler runs in a daemon thread; timeouts and exceptions are swallowed
so a slow or crashing hook never blocks or kills the caller.

Also provides PluginRegistry — discovers Python plugins from ~/.vector/plugins/
and wires their hook functions into the VectorCode lifecycle.
"""
import sys
import importlib
import importlib.util
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from loguru import logger


class HookName(Enum):
    PRE_EDIT = "PRE_EDIT"
    POST_EDIT = "POST_EDIT"
    PRE_TASK = "PRE_TASK"
    POST_TASK = "POST_TASK"
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    ROUTE = "ROUTE"
    EXPLAIN = "EXPLAIN"
    PRETRAIN = "PRETRAIN"
    BUILD_AGENTS = "BUILD_AGENTS"
    TRANSFER = "TRANSFER"
    TEAMMATE_IDLE = "TEAMMATE_IDLE"
    TASK_COMPLETE = "TASK_COMPLETE"
    NOTIFY = "NOTIFY"
    INTELLIGENCE = "INTELLIGENCE"
    SESSION_RESTORE = "SESSION_RESTORE"
    POST_COMMAND = "POST_COMMAND"


class HookRegistry:
    """
    Central registry for VectorCode lifecycle hooks.

    register()   — attach a callable to a named hook with optional priority.
    unregister() — detach a callable from a hook.
    fire()       — run all handlers for a hook in priority order, each
                   guarded by a daemon thread + timeout.
    list_handlers() — return the ordered list of callables for a hook.
    """

    def __init__(self, default_timeout: float = 5.0) -> None:
        self.default_timeout = default_timeout
        # Each entry: (priority: int, fn: Callable)
        self._handlers: Dict[HookName, List[Tuple[int, Callable]]] = {
            h: [] for h in HookName
        }

    def register(self, hook: HookName, fn: Callable, priority: int = 5) -> None:
        """Attach fn to hook. Lower priority number runs first."""
        self._handlers[hook].append((priority, fn))
        self._handlers[hook].sort(key=lambda x: x[0])
        logger.debug(f"[VECTOR][hooks] registered {hook.name} priority={priority} fn={fn.__name__ if hasattr(fn, '__name__') else fn}")

    def unregister(self, hook: HookName, fn: Callable) -> None:
        """Remove the first registration of fn from hook."""
        self._handlers[hook] = [
            (p, f) for p, f in self._handlers[hook] if f is not fn
        ]
        logger.debug(f"[VECTOR][hooks] unregistered {hook.name}")

    def fire(self, hook: HookName, ctx: dict) -> None:
        """
        Execute all handlers for hook in priority order.
        Each handler runs in a daemon thread with self.default_timeout.
        Timeouts and exceptions are caught and logged — never re-raised.
        """
        for _, fn in self._handlers[hook]:
            exc: List[Exception] = []

            def _run(fn: Callable = fn, exc: List = exc) -> None:
                try:
                    fn(ctx)
                except Exception as e:
                    exc.append(e)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=self.default_timeout)

            if t.is_alive():
                logger.warning(
                    f"[VECTOR][hooks] {hook.name} handler timed out after {self.default_timeout}s — skipping"
                )
            elif exc:
                logger.error(
                    f"[VECTOR][hooks] {hook.name} handler raised: {exc[0]}"
                )

    def list_handlers(self, hook: HookName) -> List[Callable]:
        """Return callables registered to hook in current priority order."""
        return [fn for _, fn in self._handlers[hook]]


# ── Plugin system ─────────────────────────────────────────────────────────────

@dataclass
class PluginManifest:
    """Parsed contents of a plugin's plugin.toml manifest."""
    name: str
    version: str = "1.0"
    hooks: list = field(default_factory=list)   # list[str]
    enabled: bool = True


# Module-level PluginRegistry singleton
_plugin_registry_instance: Optional["PluginRegistry"] = None


class PluginRegistry:
    """
    Discovers and manages VectorCode plugins from ~/.vector/plugins/.

    Plugin layout:
        ~/.vector/plugins/
            my_plugin/
                plugin.toml    ← {"name": "my_plugin", "version": "1.0", "hooks": ["pre_tool_call"]}
                __init__.py    ← defines: pre_tool_call(tool_name, args) -> dict | None

    Plugin hook functions are called by invoke_hook() with keyword arguments.
    Non-None return values are collected and returned to the caller.
    """

    PLUGIN_DIR = Path.home() / ".vector" / "plugins"

    def __init__(self) -> None:
        # name -> (PluginManifest, module)
        self._plugins: Dict[str, Tuple[PluginManifest, Any]] = {}

    # ── Discovery & loading ───────────────────────────────────────────────────

    def discover(self) -> List[str]:
        """
        Scan PLUGIN_DIR for plugins.  For each sub-directory that contains a
        plugin.toml, parse the manifest, import __init__.py, and register the
        hooks declared in the manifest.

        Returns the list of successfully-loaded plugin names.
        """
        if not self.PLUGIN_DIR.is_dir():
            logger.debug(f"[plugins] plugin dir not found: {self.PLUGIN_DIR}")
            return []

        loaded: List[str] = []
        for entry in sorted(self.PLUGIN_DIR.iterdir()):
            if not entry.is_dir():
                continue
            toml_path = entry / "plugin.toml"
            if not toml_path.exists():
                continue

            try:
                manifest = self._load_toml(toml_path)
            except Exception as exc:
                logger.warning(f"[plugins] failed to parse {toml_path}: {exc}")
                continue

            if not manifest.enabled:
                logger.debug(f"[plugins] {manifest.name} is disabled — skipping")
                continue

            try:
                module = self._import_plugin(entry, manifest.name)
            except Exception as exc:
                logger.warning(f"[plugins] failed to import {manifest.name}: {exc}")
                continue

            self._plugins[manifest.name] = (manifest, module)
            loaded.append(manifest.name)
            logger.info(
                f"[plugins] loaded {manifest.name} v{manifest.version} "
                f"hooks={manifest.hooks}"
            )

        return loaded

    def invoke_hook(self, hook_name: str, **kwargs) -> List[dict]:
        """
        Call all registered plugins that declare `hook_name` in their manifest.

        Each plugin's hook function is called with the provided kwargs.
        Results that are not None are collected and returned.
        Plugin exceptions are caught and logged without propagating.
        """
        results: List[dict] = []
        for name, (manifest, module) in self._plugins.items():
            if hook_name not in manifest.hooks:
                continue
            fn = getattr(module, hook_name, None)
            if fn is None or not callable(fn):
                logger.warning(
                    f"[plugins] {name} declares hook '{hook_name}' "
                    "but does not define it"
                )
                continue
            try:
                result = fn(**kwargs)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.error(f"[plugins] {name}.{hook_name} raised: {exc}")
        return results

    def list_plugins(self) -> List[dict]:
        """Return a list of dicts describing all loaded plugins."""
        return [
            {
                "name": manifest.name,
                "version": manifest.version,
                "hooks": manifest.hooks,
                "enabled": manifest.enabled,
            }
            for manifest, _ in self._plugins.values()
        ]

    def enable(self, name: str) -> None:
        """Re-enable a previously disabled plugin (in-memory only)."""
        if name in self._plugins:
            self._plugins[name][0].enabled = True
            logger.info(f"[plugins] {name} enabled")
        else:
            logger.warning(f"[plugins] enable: plugin '{name}' not loaded")

    def disable(self, name: str) -> None:
        """Disable a plugin (in-memory only — it stays in the registry)."""
        if name in self._plugins:
            self._plugins[name][0].enabled = False
            logger.info(f"[plugins] {name} disabled")
        else:
            logger.warning(f"[plugins] disable: plugin '{name}' not loaded")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_toml(self, path: Path) -> PluginManifest:
        """
        Parse plugin.toml.  Uses tomllib (Python 3.11+) when available,
        otherwise falls back to a minimal hand-rolled regex parser for the
        simple key=value / array format used by plugin manifests.
        """
        text = path.read_text(encoding="utf-8")

        try:
            import tomllib  # Python 3.11+
            data = tomllib.loads(text)
        except ImportError:
            data = self._parse_toml_minimal(text)

        name = str(data.get("name", path.parent.name))
        version = str(data.get("version", "1.0"))
        hooks_raw = data.get("hooks", [])
        if isinstance(hooks_raw, str):
            hooks = [h.strip().strip('"').strip("'") for h in hooks_raw.strip("[]").split(",") if h.strip()]
        else:
            hooks = [str(h) for h in hooks_raw]
        enabled = bool(data.get("enabled", True))

        return PluginManifest(name=name, version=version, hooks=hooks, enabled=enabled)

    @staticmethod
    def _parse_toml_minimal(text: str) -> dict:
        """
        Minimal TOML parser for plugin manifests.  Handles:
          name = "value"
          version = "1.0"
          hooks = ["pre_tool_call", "post_tool_call"]
          enabled = true/false
        """
        data: dict = {}

        # String values
        for m in re.finditer(r'^(\w+)\s*=\s*"([^"]*)"', text, re.MULTILINE):
            data[m.group(1)] = m.group(2)

        # Boolean values
        for m in re.finditer(r'^(\w+)\s*=\s*(true|false)', text, re.MULTILINE | re.IGNORECASE):
            data[m.group(1)] = m.group(2).lower() == "true"

        # Inline array: hooks = ["a", "b"]
        arr_match = re.search(r'hooks\s*=\s*\[([^\]]*)\]', text)
        if arr_match:
            items = re.findall(r'"([^"]+)"', arr_match.group(1))
            data["hooks"] = items

        return data

    @staticmethod
    def _import_plugin(plugin_dir: Path, plugin_name: str) -> Any:
        """Import a plugin directory as a Python module."""
        init_path = plugin_dir / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            f"vectorcode_plugin_{plugin_name}", str(init_path)
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {init_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module


def get_plugin_registry() -> "PluginRegistry":
    """Return the module-level PluginRegistry singleton."""
    global _plugin_registry_instance
    if _plugin_registry_instance is None:
        _plugin_registry_instance = PluginRegistry()
        logger.debug("[plugins] PluginRegistry singleton created")
    return _plugin_registry_instance


# ── Smoke test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    reg = HookRegistry(default_timeout=1.0)

    fired: list = []
    reg.register(HookName.PRE_EDIT, lambda ctx: fired.append(ctx.get("file")), priority=1)
    reg.register(HookName.PRE_EDIT, lambda ctx: fired.append("second"), priority=2)
    reg.fire(HookName.PRE_EDIT, {"file": "main.py"})
    assert fired == ["main.py", "second"], f"unexpected: {fired}"

    reg.unregister(HookName.PRE_EDIT, reg.list_handlers(HookName.PRE_EDIT)[0])
    assert len(reg.list_handlers(HookName.PRE_EDIT)) == 1

    # PluginRegistry smoke test
    pr = get_plugin_registry()
    pr2 = get_plugin_registry()
    assert pr is pr2, "get_plugin_registry must be singleton"

    # discover() when plugin dir absent — should return []
    loaded = pr.discover()
    assert isinstance(loaded, list), "discover() must return a list"

    # invoke_hook with no plugins loaded — should return []
    results = pr.invoke_hook("pre_tool_call", tool_name="bash", args={})
    assert results == [], f"expected empty list, got {results}"

    # list_plugins
    info = pr.list_plugins()
    assert isinstance(info, list)

    logger.info("✅ hooks/registry.py OK")



