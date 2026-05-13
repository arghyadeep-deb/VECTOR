# Ported from GitHub/NousResearch_hermes-agent/repo/tools/registry.py + model_tools.py
"""Central registry for all VectorCode tools.

Each tool file calls ``registry.register()`` at module level to declare its
schema, handler, toolset membership, and availability check.

Import chain (circular-import safe):
    tools/registry.py  (no imports from engine or tool files)
           ^
    tools/*.py  (import from tools.registry at module level)
           ^
    engine/  (imports tools.registry via AIAgent._get_registry())
"""
import ast
import asyncio
import importlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Parallel-safety sets (shared with engine/tool_exec.py) ────────────────────
_PARALLEL_SAFE_TOOLS = frozenset({
    "ha_get_state", "ha_list_entities", "ha_list_services",
    "read_file", "search_files", "session_search",
    "skill_view", "skills_list",
    "vision_analyze", "web_extract", "web_search",
})
_NEVER_PARALLEL_TOOLS = frozenset({"clarify"})
_PATH_SCOPED_TOOLS = frozenset({"read_file", "write_file", "patch"})


# ── Async bridging ─────────────────────────────────────────────────────────────

_tool_loop: Optional[asyncio.AbstractEventLoop] = None
_tool_loop_lock = threading.Lock()
_worker_thread_local = threading.local()


def _get_tool_loop() -> asyncio.AbstractEventLoop:
    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
        return _tool_loop


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_worker_thread_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _worker_thread_local.loop = loop
    return loop


def _run_async(coro) -> Any:
    """Run an async coroutine from a sync context safely."""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None:
        # Already inside an event loop — run in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()

    # Check if we're in a worker thread
    worker_loop = getattr(_worker_thread_local, "loop", None)
    if worker_loop is not None and not worker_loop.is_closed():
        return worker_loop.run_until_complete(coro)

    # Main thread path — use persistent loop
    loop = _get_tool_loop()
    return loop.run_until_complete(coro)


# ── ToolEntry ──────────────────────────────────────────────────────────────────

class ToolEntry:
    """Metadata for a single registered tool."""

    __slots__ = (
        "name", "toolset", "schema", "handler", "check_fn",
        "requires_env", "is_async", "description", "emoji",
        "risk_level", "max_result_size_chars",
    )

    def __init__(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Optional[Callable] = None,
        requires_env: Optional[List[str]] = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "🔧",
        risk_level: str = "safe",
        max_result_size_chars: Optional[int] = None,
    ):
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.requires_env = requires_env or []
        self.is_async = is_async
        self.description = description
        self.emoji = emoji
        self.risk_level = risk_level
        self.max_result_size_chars = max_result_size_chars


# ── ToolRegistry ───────────────────────────────────────────────────────────────

class ToolRegistry:
    """Thread-safe registry for all VectorCode tools."""

    _instance: Optional["ToolRegistry"] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}
        self._lock = threading.RLock()

    @classmethod
    def global_instance(cls) -> "ToolRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance._discover_builtin_tools()
            return cls._instance

    def register(
        self,
        name: str,
        handler: Callable,
        schema: dict,
        toolset: str = "coding",
        check_fn: Optional[Callable] = None,
        requires_env: Optional[List[str]] = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "🔧",
        risk_level: str = "safe",
        max_result_size_chars: Optional[int] = None,
    ) -> None:
        """Register a tool. Called at module level by each tool file."""
        with self._lock:
            self._tools[name] = ToolEntry(
                name=name,
                toolset=toolset,
                schema=schema,
                handler=handler,
                check_fn=check_fn,
                requires_env=requires_env,
                is_async=is_async,
                description=description,
                emoji=emoji,
                risk_level=risk_level,
                max_result_size_chars=max_result_size_chars,
            )
            logger.debug(f"Registered tool: {name!r} (toolset={toolset!r})")

    def handle_function_call(
        self,
        function_name: str,
        function_args: dict,
        context: Any = None,
    ) -> Any:
        """Central dispatcher — routes a tool call to its handler.

        Equivalent to Hermes model_tools.handle_function_call().
        """
        with self._lock:
            entry = self._tools.get(function_name)

        if entry is None:
            logger.warning(f"Unknown tool: {function_name!r}")
            return f"Error: tool {function_name!r} is not registered."

        # Permission check if gateway available
        if context is not None:
            gateway = getattr(context, "permission_gateway", None)
            if gateway is not None:
                try:
                    decision = gateway.check(function_name, function_args, entry.risk_level)
                    if decision == "RED":
                        return f"Error: tool {function_name!r} blocked by permission gateway."
                except Exception as e:
                    logger.warning(f"Permission gateway error for {function_name}: {e}")

        try:
            if entry.is_async:
                result = _run_async(entry.handler(**function_args))
            else:
                result = entry.handler(**function_args)
        except TypeError as e:
            logger.error(f"Tool {function_name!r} called with wrong args {function_args}: {e}")
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"Tool {function_name!r} raised: {e}")
            return f"Error: {e}"

        # Truncate oversized results
        if isinstance(result, str) and entry.max_result_size_chars:
            if len(result) > entry.max_result_size_chars:
                result = result[:entry.max_result_size_chars] + "\n[...truncated]"

        return result

    def get_tool_definitions(self, toolset: str = "coding") -> List[dict]:
        """Return JSON schemas for all tools in the given toolset.

        Equivalent to Hermes model_tools.get_tool_definitions().
        """
        with self._lock:
            tools = list(self._tools.values())

        result = []
        for entry in tools:
            if toolset == "full" or entry.toolset == toolset or toolset == "all":
                result.append({
                    "type": "function",
                    "function": {
                        "name": entry.name,
                        "description": entry.description or entry.schema.get("description", ""),
                        "parameters": entry.schema.get("parameters", {"type": "object", "properties": {}}),
                    },
                })
        return result

    def get_all_tool_names(self) -> List[str]:
        with self._lock:
            return list(self._tools.keys())

    def get_toolset_for_tool(self, name: str) -> Optional[str]:
        with self._lock:
            entry = self._tools.get(name)
            return entry.toolset if entry else None

    def check_toolset_requirements(self, toolset: str = "coding") -> Dict[str, bool]:
        """Check which tools in a toolset have their requirements met."""
        with self._lock:
            tools = [e for e in self._tools.values() if e.toolset == toolset or toolset == "all"]

        results = {}
        for entry in tools:
            if entry.check_fn is not None:
                try:
                    results[entry.name] = bool(entry.check_fn())
                except Exception:
                    results[entry.name] = False
            else:
                results[entry.name] = True
        return results

    def _discover_builtin_tools(self) -> None:
        """Import all self-registering tool modules."""
        tools_dir = Path(__file__).parent
        for path in sorted(tools_dir.glob("*.py")):
            if path.name in {"__init__.py", "registry.py"}:
                continue
            if not _module_registers_tools(path):
                continue
            mod_name = f"vectorcode.tools.{path.stem}"
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                logger.warning(f"Could not import tool module {mod_name}: {e}")

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self._tools)} tools)"


# ── Module-level singleton ─────────────────────────────────────────────────────

# This IS the global instance — tool files import and call registry.register()
# at module level, which populates this same object.
# ToolRegistry.global_instance() returns this same object after first call.
registry = ToolRegistry()
ToolRegistry._instance = registry  # wire up so global_instance() returns this


# ── AST-based discovery helper ─────────────────────────────────────────────────

def _is_registry_register_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "register"
        and isinstance(func.value, ast.Name)
        and func.value.id == "registry"
    )


def _module_registers_tools(module_path: Path) -> bool:
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (OSError, SyntaxError):
        return False
    return any(_is_registry_register_call(stmt) for stmt in tree.body)


# ── Public API (matches Hermes model_tools.py signatures) ─────────────────────

def get_tool_definitions(
    enabled_toolsets: Optional[List[str]] = None,
    disabled_toolsets: Optional[List[str]] = None,
    quiet_mode: bool = False,
) -> List[dict]:
    reg = ToolRegistry.global_instance()
    toolset = "full" if not enabled_toolsets else enabled_toolsets[0]
    return reg.get_tool_definitions(toolset)


def handle_function_call(
    function_name: str,
    function_args: dict,
    task_id: str = "",
    user_task: str = "",
    context: Any = None,
) -> Any:
    reg = ToolRegistry.global_instance()
    return reg.handle_function_call(function_name, function_args, context)


def get_all_tool_names() -> List[str]:
    return ToolRegistry.global_instance().get_all_tool_names()


def get_toolset_for_tool(name: str) -> Optional[str]:
    return ToolRegistry.global_instance().get_toolset_for_tool(name)


def check_toolset_requirements(toolset: str = "coding") -> Dict[str, bool]:
    return ToolRegistry.global_instance().check_toolset_requirements(toolset)
