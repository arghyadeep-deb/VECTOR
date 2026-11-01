"""Central registry for all vectorcode tools.

Each tool file calls ``registry.register()`` at module level to declare its
schema, handler, toolset membership, and availability check.  ``model_tools.py``
queries the registry instead of maintaining its own parallel data structures.

Import chain (circular-import safe):
    tools/registry.py  (no imports from model_tools or tool files)
           ^
    tools/*.py  (import from tools.registry at module level)
           ^
    model_tools.py  (imports tools.registry + all tool modules)
           ^
    run_agent.py, cli.py, batch_runner.py, etc.
"""

import ast
import importlib
import json
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def _is_registry_register_call(node: ast.AST) -> bool:
    """Return True when *node* is a ``registry.register(...)`` call expression."""
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
    """Return True when the module contains a top-level ``registry.register(...)`` call.

    Only inspects module-body statements so that helper modules which happen
    to call ``registry.register()`` inside a function are not picked up.
    """
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (OSError, SyntaxError):
        return False

    return any(_is_registry_register_call(stmt) for stmt in tree.body)


def discover_builtin_tools(tools_dir: Optional[Path] = None) -> List[str]:
    """Import built-in self-registering tool modules and return their module names."""
    tools_path = Path(tools_dir) if tools_dir is not None else Path(__file__).resolve().parent
    module_names = [
        f"tools.{path.stem}"
        for path in sorted(tools_path.glob("*.py"))
        if path.name not in {"__init__.py", "registry.py", "mcp_tool.py"}
        and _module_registers_tools(path)
    ]

    imported: List[str] = []
    for mod_name in module_names:
        try:
            importlib.import_module(mod_name)
            imported.append(mod_name)
        except Exception as e:
            logger.warning("Could not import tool module %s: %s", mod_name, e)
    return imported


class ToolEntry:
    """Metadata for a single registered tool."""

    __slots__ = (
        "name", "toolset", "schema", "handler", "check_fn",
        "requires_env", "is_async", "description", "emoji",
        "max_result_size_chars", "dynamic_schema_overrides",
    )

    def __init__(self, name, toolset, schema, handler, check_fn,
                 requires_env, is_async, description, emoji,
                 max_result_size_chars=None, dynamic_schema_overrides=None):
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.requires_env = requires_env
        self.is_async = is_async
        self.description = description
        self.emoji = emoji
        self.max_result_size_chars = max_result_size_chars
        # Optional callable returning schema keys to overlay when definitions are built (e.g. a description
        # that reflects the currently configured backend). video_generation_tool passes one; the parameter
        # did not exist, so that whole tool failed to register.
        self.dynamic_schema_overrides = dynamic_schema_overrides


class ToolRegistry:
    """Singleton registry that collects tool schemas + handlers from tool files."""

    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}
        self._toolset_checks: Dict[str, Callable] = {}
        self._toolset_aliases: Dict[str, str] = {}
        # MCP dynamic refresh can mutate the registry while other threads are
        # reading tool metadata, so keep mutations serialized and readers on
        # stable snapshots.
        self._lock = threading.RLock()

    def _snapshot_state(self) -> tuple[List[ToolEntry], Dict[str, Callable]]:
        """Return a coherent snapshot of registry entries and toolset checks."""
        with self._lock:
            return list(self._tools.values()), dict(self._toolset_checks)

    def _snapshot_entries(self) -> List[ToolEntry]:
        """Return a stable snapshot of registered tool entries."""
        return self._snapshot_state()[0]

    def _snapshot_toolset_checks(self) -> Dict[str, Callable]:
        """Return a stable snapshot of toolset availability checks."""
        return self._snapshot_state()[1]

    def _evaluate_toolset_check(self, toolset: str, check: Callable | None) -> bool:
        """Run a toolset check, treating missing or failing checks as unavailable/available."""
        if not check:
            return True
        try:
            return bool(check())
        except Exception:
            logger.debug("Toolset %s check raised; marking unavailable", toolset)
            return False

    def get_entry(self, name: str) -> Optional[ToolEntry]:
        """Return a registered tool entry by name, or None."""
        with self._lock:
            return self._tools.get(name)

    def get_registered_toolset_names(self) -> List[str]:
        """Return sorted unique toolset names present in the registry."""
        return sorted({entry.toolset for entry in self._snapshot_entries()})

    def get_tool_names_for_toolset(self, toolset: str) -> List[str]:
        """Return sorted tool names registered under a given toolset."""
        return sorted(
            entry.name for entry in self._snapshot_entries()
            if entry.toolset == toolset
        )

    def register_toolset_alias(self, alias: str, toolset: str) -> None:
        """Register an explicit alias for a canonical toolset name."""
        with self._lock:
            existing = self._toolset_aliases.get(alias)
            if existing and existing != toolset:
                logger.warning(
                    "Toolset alias collision: '%s' (%s) overwritten by %s",
                    alias, existing, toolset,
                )
            self._toolset_aliases[alias] = toolset

    def get_registered_toolset_aliases(self) -> Dict[str, str]:
        """Return a snapshot of ``{alias: canonical_toolset}`` mappings."""
        with self._lock:
            return dict(self._toolset_aliases)

    def get_toolset_alias_target(self, alias: str) -> Optional[str]:
        """Return the canonical toolset name for an alias, or None."""
        with self._lock:
            return self._toolset_aliases.get(alias)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Callable = None,
        requires_env: list = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        max_result_size_chars: int | float | None = None,
        dynamic_schema_overrides: Callable | None = None,
    ):
        """Register a tool.  Called at module-import time by each tool file."""
        with self._lock:
            existing = self._tools.get(name)
            if existing and existing.toolset != toolset:
                # Allow MCP-to-MCP overwrites (legitimate: server refresh,
                # or two MCP servers with overlapping tool names).
                both_mcp = (
                    existing.toolset.startswith("mcp-")
                    and toolset.startswith("mcp-")
                )
                if both_mcp:
                    logger.debug(
                        "Tool '%s': MCP toolset '%s' overwriting MCP toolset '%s'",
                        name, toolset, existing.toolset,
                    )
                else:
                    # Reject shadowing — prevent plugins/MCP from overwriting
                    # built-in tools or vice versa.
                    logger.error(
                        "Tool registration REJECTED: '%s' (toolset '%s') would "
                        "shadow existing tool from toolset '%s'. Deregister the "
                        "existing tool first if this is intentional.",
                        name, toolset, existing.toolset,
                    )
                    return
            self._tools[name] = ToolEntry(
                name=name,
                toolset=toolset,
                schema=schema,
                handler=handler,
                check_fn=check_fn,
                requires_env=requires_env or [],
                is_async=is_async,
                description=description or schema.get("description", ""),
                emoji=emoji,
                max_result_size_chars=max_result_size_chars,
                dynamic_schema_overrides=dynamic_schema_overrides,
            )
            if check_fn and toolset not in self._toolset_checks:
                self._toolset_checks[toolset] = check_fn

    def deregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Also cleans up the toolset check if no other tools remain in the
        same toolset.  Used by MCP dynamic tool discovery to nuke-and-repave
        when a server sends ``notifications/tools/list_changed``.
        """
        with self._lock:
            entry = self._tools.pop(name, None)
            if entry is None:
                return
            # Drop the toolset check and aliases if this was the last tool in
            # that toolset.
            toolset_still_exists = any(
                e.toolset == entry.toolset for e in self._tools.values()
            )
            if not toolset_still_exists:
                self._toolset_checks.pop(entry.toolset, None)
                self._toolset_aliases = {
                    alias: target
                    for alias, target in self._toolset_aliases.items()
                    if target != entry.toolset
                }
        logger.debug("Deregistered tool: %s", name)

    # ------------------------------------------------------------------
    # Schema retrieval
    # ------------------------------------------------------------------

    def get_definitions(self, tool_names: Set[str], quiet: bool = False) -> List[dict]:
        """Return OpenAI-format tool schemas for the requested tool names.

        Only tools whose ``check_fn()`` returns True (or have no check_fn)
        are included.
        """
        result = []
        check_results: Dict[Callable, bool] = {}
        entries_by_name = {entry.name: entry for entry in self._snapshot_entries()}
        for name in sorted(tool_names):
            entry = entries_by_name.get(name)
            if not entry:
                continue
            if entry.check_fn:
                if entry.check_fn not in check_results:
                    try:
                        check_results[entry.check_fn] = bool(entry.check_fn())
                    except Exception:
                        check_results[entry.check_fn] = False
                        if not quiet:
                            logger.debug("Tool %s check raised; skipping", name)
                if not check_results[entry.check_fn]:
                    if not quiet:
                        logger.debug("Tool %s unavailable (check failed)", name)
                    continue
            # Ensure schema always has a "name" field — use entry.name as fallback
            schema_with_name = {**entry.schema, "name": entry.name}
            if entry.dynamic_schema_overrides:
                try:
                    schema_with_name.update(entry.dynamic_schema_overrides() or {})
                except Exception:
                    logger.debug("Tool %s dynamic schema overrides failed; using the static schema", name)
            result.append({"type": "function", "function": schema_with_name})
        return result

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, name: str, args: dict, **kwargs) -> str:
        """Execute a tool handler by name.

        * Async handlers are bridged automatically via ``_run_async()``.
        * All exceptions are caught and returned as ``{"error": "..."}``
          for consistent error format.
        """
        entry = self.get_entry(name)
        if not entry:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            if entry.is_async:
                from model_tools import _run_async
                return _run_async(entry.handler(args, **kwargs))
            return entry.handler(args, **kwargs)
        except Exception as e:
            logger.exception("Tool %s dispatch error: %s", name, e)
            return json.dumps({"error": f"Tool execution failed: {type(e).__name__}: {e}"})

    # ------------------------------------------------------------------
    # Query helpers  (replace redundant dicts in model_tools.py)
    # ------------------------------------------------------------------

    def get_max_result_size(self, name: str, default: int | float | None = None) -> int | float:
        """Return per-tool max result size, or *default* (or global default)."""
        entry = self.get_entry(name)
        if entry and entry.max_result_size_chars is not None:
            return entry.max_result_size_chars
        if default is not None:
            return default
        from tools.budget_config import DEFAULT_RESULT_SIZE_CHARS
        return DEFAULT_RESULT_SIZE_CHARS

    def get_all_tool_names(self) -> List[str]:
        """Return sorted list of all registered tool names."""
        return sorted(entry.name for entry in self._snapshot_entries())

    def get_schema(self, name: str) -> Optional[dict]:
        """Return a tool's raw schema dict, bypassing check_fn filtering.

        Useful for token estimation and introspection where availability
        doesn't matter — only the schema content does.
        """
        entry = self.get_entry(name)
        return entry.schema if entry else None

    def get_toolset_for_tool(self, name: str) -> Optional[str]:
        """Return the toolset a tool belongs to, or None."""
        entry = self.get_entry(name)
        return entry.toolset if entry else None

    def get_emoji(self, name: str, default: str = "⚡") -> str:
        """Return the emoji for a tool, or *default* if unset."""
        entry = self.get_entry(name)
        return (entry.emoji if entry and entry.emoji else default)

    def get_tool_to_toolset_map(self) -> Dict[str, str]:
        """Return ``{tool_name: toolset_name}`` for every registered tool."""
        return {entry.name: entry.toolset for entry in self._snapshot_entries()}

    def is_toolset_available(self, toolset: str) -> bool:
        """Check if a toolset's requirements are met.

        Returns False (rather than crashing) when the check function raises
        an unexpected exception (e.g. network error, missing import, bad config).
        """
        with self._lock:
            check = self._toolset_checks.get(toolset)
        return self._evaluate_toolset_check(toolset, check)

    def check_toolset_requirements(self) -> Dict[str, bool]:
        """Return ``{toolset: available_bool}`` for every toolset."""
        entries, toolset_checks = self._snapshot_state()
        toolsets = sorted({entry.toolset for entry in entries})
        return {
            toolset: self._evaluate_toolset_check(toolset, toolset_checks.get(toolset))
            for toolset in toolsets
        }

    def get_available_toolsets(self) -> Dict[str, dict]:
        """Return toolset metadata for UI display."""
        toolsets: Dict[str, dict] = {}
        entries, toolset_checks = self._snapshot_state()
        for entry in entries:
            ts = entry.toolset
            if ts not in toolsets:
                toolsets[ts] = {
                    "available": self._evaluate_toolset_check(
                        ts, toolset_checks.get(ts)
                    ),
                    "tools": [],
                    "description": "",
                    "requirements": [],
                }
            toolsets[ts]["tools"].append(entry.name)
            if entry.requires_env:
                for env in entry.requires_env:
                    if env not in toolsets[ts]["requirements"]:
                        toolsets[ts]["requirements"].append(env)
        return toolsets

    def get_toolset_requirements(self) -> Dict[str, dict]:
        """Build a TOOLSET_REQUIREMENTS-compatible dict for backward compat."""
        result: Dict[str, dict] = {}
        entries, toolset_checks = self._snapshot_state()
        for entry in entries:
            ts = entry.toolset
            if ts not in result:
                result[ts] = {
                    "name": ts,
                    "env_vars": [],
                    "check_fn": toolset_checks.get(ts),
                    "setup_url": None,
                    "tools": [],
                }
            if entry.name not in result[ts]["tools"]:
                result[ts]["tools"].append(entry.name)
            for env in entry.requires_env:
                if env not in result[ts]["env_vars"]:
                    result[ts]["env_vars"].append(env)
        return result

    def check_tool_availability(self, quiet: bool = False):
        """Return (available_toolsets, unavailable_info) like the old function."""
        available = []
        unavailable = []
        seen = set()
        entries, toolset_checks = self._snapshot_state()
        for entry in entries:
            ts = entry.toolset
            if ts in seen:
                continue
            seen.add(ts)
            if self._evaluate_toolset_check(ts, toolset_checks.get(ts)):
                available.append(ts)
            else:
                unavailable.append({
                    "name": ts,
                    "env_vars": entry.requires_env,
                    "tools": [e.name for e in entries if e.toolset == ts],
                })
        return available, unavailable


# Module-level singleton
registry = ToolRegistry()


# ---------------------------------------------------------------------------
# Helpers for tool response serialization
# ---------------------------------------------------------------------------
# Every tool handler must return a JSON string.  These helpers eliminate the
# boilerplate ``json.dumps({"error": msg}, ensure_ascii=False)`` that appears
# hundreds of times across tool files.
#
# Usage:
#   from tools.registry import registry, tool_error, tool_result
#
#   return tool_error("something went wrong")
#   return tool_error("not found", code=404)
#   return tool_result(success=True, data=payload)
#   return tool_result(items)            # pass a dict directly


def tool_error(message, **extra) -> str:
    """Return a JSON error string for tool handlers.

    >>> tool_error("file not found")
    '{"error": "file not found"}'
    >>> tool_error("bad input", success=False)
    '{"error": "bad input", "success": false}'
    """
    result = {"error": str(message)}
    if extra:
        result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def tool_result(data=None, **kwargs) -> str:
    """Return a JSON result string for tool handlers.

    Accepts a dict positional arg *or* keyword arguments (not both):

    >>> tool_result(success=True, count=42)
    '{"success": true, "count": 42}'
    >>> tool_result({"key": "value"})
    '{"key": "value"}'
    """
    if data is not None:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(kwargs, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ToolRouter -- the engine's view of the registry
# ---------------------------------------------------------------------------

#: Toolsets a local coding agent gets by default. Deliberately excludes anything that messages other
#: people or services (messaging, discord, spotify, homeassistant, cronjob, browser, delegation, rl ...):
#: a coding session must not gain those side effects just because their modules are installed.
DEFAULT_AGENT_TOOLSETS = (
    "file", "terminal", "todo", "memory", "skills", "session_search",
    "clarify", "code_execution", "web", "vision",
)

_READ_ONLY_AGENT_TOOLS = frozenset({"read_file", "search_files"})


class ToolRouter:
    """What ``engine/agent_loop.py`` imports (``from tools.registry import ToolRouter``).

    That class did not exist anywhere, so ``VectorAgent.run_conversation`` crashed before its first model
    call and the REPL silently degraded to a plain chat with no tools. It exposes the two calls the loop
    makes: ``get_schemas()`` and ``execute(name, args)``.
    """

    def __init__(self, project_dir=None, approval_callback=None, enabled_toolsets=None):
        import os
        from pathlib import Path

        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.approval_callback = approval_callback  # consulted by the agent loop before each call
        self.enabled_toolsets = list(enabled_toolsets or DEFAULT_AGENT_TOOLSETS)
        # Owner-configured MCP servers are added only for the default toolset list (an explicit list is honoured as
        # given) and only when an approval callback exists: the agent loop runs tools unprompted without one, and
        # external tools are side-effecting by default.
        self._include_mcp_toolsets = not enabled_toolsets and approval_callback is not None
        # File and terminal tools resolve relative paths against TERMINAL_CWD
        if os.environ.get("TERMINAL_ENV", "local") == "local":
            os.environ["TERMINAL_CWD"] = str(self.project_dir)
        self._schemas = None
        # State for the tools model_tools deliberately leaves to "the agent loop" (todo / memory /
        # session_search). Nothing implemented that, so each of them answered "must be handled by the agent
        # loop" and the agent could never keep a task list, remember anything or search past sessions.
        self._todo_store = None
        self._memory_store = None
        self._session_db = None
        self.session_id = None

    def bind_session(self, session_id: str) -> None:
        """Use the existing per-task environment mechanism for this coding session."""
        from tools.terminal_tool import _get_env_config, _task_env_overrides, register_task_env_overrides

        self.session_id = session_id
        overrides = dict(_task_env_overrides.get(session_id, {}))
        overrides.setdefault("cwd", _get_env_config()["cwd"])
        register_task_env_overrides(session_id, overrides)

    def get_schemas(self) -> list:
        """OpenAI-format schemas for the tools that are actually available right now."""
        if self._schemas is None:
            from model_tools import get_tool_definitions

            toolsets = self.enabled_toolsets + (self._connected_mcp_toolsets() if self._include_mcp_toolsets else [])
            if self._include_mcp_toolsets:
                toolsets.append('git_pr')
            self._schemas = get_tool_definitions(enabled_toolsets=toolsets, quiet_mode=True)
        from vectorcode.src.session import VectorCodeSession

        if VectorCodeSession.get().mode == "read-only":
            return [schema for schema in self._schemas
                    if schema["function"]["name"] in _READ_ONLY_AGENT_TOOLS]
        return [schema for schema in self._schemas if self.approval_callback is not None
                or schema['function']['name'] != 'git_create_pr']

    @staticmethod
    def _connected_mcp_toolsets() -> list:
        """``mcp-<server>`` toolsets of configured, enabled MCP servers that are connected right now.

        ``model_tools`` registers their tools at import from the ``mcp_servers`` config; the calls still go through
        the same agent-loop approval callback and read-only filter as every native tool.
        """
        try:
            from tools.mcp_tool import get_mcp_status

            return [f"mcp-{s['name']}" for s in get_mcp_status() if s.get("connected") and s.get("tools")]
        except Exception as exc:
            logger.debug("MCP toolsets unavailable: %s", exc)
            return []

    def tool_names(self) -> list:
        return [s["function"]["name"] for s in self.get_schemas()]

    def execute(self, name: str, args: dict) -> str:
        """Run one tool call and return its (JSON string) result. Unknown / unavailable tools are refused."""
        if name not in self.tool_names():
            return tool_error(f"tool '{name}' is not available to this agent")
        args = args or {}
        if name in ("todo", "memory", "session_search"):
            return self._execute_loop_tool(name, args)
        from model_tools import handle_function_call

        if name != "terminal" or self.approval_callback is None:
            return handle_function_call(name, args, task_id=self.session_id, session_id=self.session_id,
                                        enabled_tools=self.tool_names())

        # Command guards can require an informed approval after the ordinary
        # tool approval. Keep those guards intact and surface their explanation
        # through the same UI, rather than reading the bridge's protocol stdin.
        from tools.terminal_tool import _get_approval_callback, set_approval_callback

        previous = _get_approval_callback()

        def approve_command(command, description, *, allow_permanent=True):
            allowed = self.approval_callback("pre_tool_call", "terminal", {
                "command": command,
                "description": description,
                "approval_source": "command_guard",
            })
            return "once" if allowed is True else "deny"

        set_approval_callback(approve_command)
        try:
            return handle_function_call(name, args, task_id=self.session_id, session_id=self.session_id,
                                        enabled_tools=self.tool_names())
        finally:
            set_approval_callback(previous)

    def _execute_loop_tool(self, name: str, args: dict) -> str:
        import json

        if name == "todo":
            from tools.todo_tool import TodoStore, todo_tool

            self._todo_store = self._todo_store or TodoStore()
            return todo_tool(todos=args.get("todos"), merge=args.get("merge", False), store=self._todo_store)
        if name == "memory":
            from tools.memory_tool import MemoryStore, memory_tool

            if self._memory_store is None:
                self._memory_store = MemoryStore()
                self._memory_store.load_from_disk()
            return memory_tool(action=args.get("action"), target=args.get("target", "memory"),
                               content=args.get("content"), old_text=args.get("old_text"),
                               store=self._memory_store)
        if self._session_db is None:
            try:
                from vector_state import SessionDB

                self._session_db = SessionDB()
            except Exception as exc:
                return json.dumps({"success": False, "error": f"Session database not available: {exc}"})
        from tools.session_search_tool import session_search

        return session_search(query=args.get("query", ""), role_filter=args.get("role_filter"),
                              limit=args.get("limit", 3), db=self._session_db,
                              current_session_id=self.session_id)
