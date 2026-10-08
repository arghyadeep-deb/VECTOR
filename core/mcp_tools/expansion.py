"""VECTOR MCP expansion tools facade.

The expansion catalog is split by tool domain under
``core.mcp_tools.expansion_modules``. Keep this facade as the stable entry
point used by ``core.mcp_server``.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from core.mcp_tools import security as _security
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.expansion_modules.agents import add_agent_tools
from core.mcp_tools.expansion_modules.browser import add_browser_tools
from core.mcp_tools.expansion_modules.config import add_config_tools
from core.mcp_tools.expansion_modules.docs import add_doc_tools
from core.mcp_tools.expansion_modules.files import add_file_tools
from core.mcp_tools.expansion_modules.git import add_git_tools
from core.mcp_tools.expansion_modules.graph import add_graph_tools
from core.mcp_tools.expansion_modules.hooks import add_hook_tools
from core.mcp_tools.expansion_modules.memory import add_memory_tools
from core.mcp_tools.expansion_modules.neural import add_neural_tools
from core.mcp_tools.expansion_modules.performance import add_perf_tools
from core.mcp_tools.expansion_modules.security import add_security_tools
from core.mcp_tools.expansion_modules.swarm import add_swarm_tools
from core.mcp_tools.expansion_modules.tasks import add_task_tools
from core.mcp_tools.expansion_modules.tests import add_test_tools
from core.mcp_tools.expansion_modules.workers import add_worker_tools


class _AuditedMCP:
    """Transparent MCP facade that audits registered tool handlers."""

    def __init__(self, mcp: Any, district: str) -> None:
        self._mcp = mcp
        self._district = district

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mcp, name)

    def tool(
        self,
        name_or_fn: str | Callable[..., Any] | None = None,
        **tool_options: Any,
    ) -> Any:
        """Mirror FastMCP.tool while wrapping the registered callable."""
        if callable(name_or_fn):
            return self._register(name_or_fn, None, tool_options)

        configured_name = name_or_fn if isinstance(name_or_fn, str) else None

        def decorator(fn: Callable[..., Any]) -> Any:
            return self._register(fn, configured_name, tool_options)

        return decorator

    def _register(
        self,
        fn: Callable[..., Any],
        configured_name: str | None,
        tool_options: dict[str, Any],
    ) -> Any:
        tool_name = tool_options.get("name") or configured_name or fn.__name__

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def audited(*args: Any, **kwargs: Any) -> Any:
                if not _security.mcp_secure_call(tool_name, self._district, dict(kwargs)):
                    return _safe_json({"error": "blocked by MCP security rate limit"})
                return await fn(*args, **kwargs)
        else:
            @functools.wraps(fn)
            def audited(*args: Any, **kwargs: Any) -> Any:
                if not _security.mcp_secure_call(tool_name, self._district, dict(kwargs)):
                    return _safe_json({"error": "blocked by MCP security rate limit"})
                return fn(*args, **kwargs)

        if configured_name is not None:
            return self._mcp.tool(configured_name, **tool_options)(audited)
        return self._mcp.tool(audited, **tool_options)


def _audited(mcp: Any, district: str) -> _AuditedMCP:
    return _AuditedMCP(mcp, district)


def add_expansion_tools(mcp) -> None:
    """Wire VectorCode expansion tools across all domains."""
    add_agent_tools(_audited(mcp, "agents"))
    add_swarm_tools(_audited(mcp, "swarm"))
    add_memory_tools(_audited(mcp, "memory"))
    add_hook_tools(_audited(mcp, "hooks"))
    add_task_tools(_audited(mcp, "tasks"))
    add_security_tools(_audited(mcp, "security"))
    add_neural_tools(_audited(mcp, "neural"))
    add_file_tools(_audited(mcp, "files"))
    add_git_tools(_audited(mcp, "git"))
    add_test_tools(_audited(mcp, "tests"))
    add_doc_tools(_audited(mcp, "docs"))
    add_browser_tools(_audited(mcp, "browser"))
    add_graph_tools(_audited(mcp, "graph"))
    add_perf_tools(_audited(mcp, "performance"))
    add_worker_tools(_audited(mcp, "workers"))
    add_config_tools(_audited(mcp, "config"))
