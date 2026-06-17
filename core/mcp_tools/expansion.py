"""VECTOR MCP expansion tools facade.

The expansion catalog is split by tool domain under
``core.mcp_tools.expansion_modules``. Keep this facade as the stable entry
point used by ``core.mcp_server``.
"""

from __future__ import annotations

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


def add_expansion_tools(mcp) -> None:
    """Wire VectorCode expansion tools across all domains."""
    add_agent_tools(mcp)
    add_swarm_tools(mcp)
    add_memory_tools(mcp)
    add_hook_tools(mcp)
    add_task_tools(mcp)
    add_security_tools(mcp)
    add_neural_tools(mcp)
    add_file_tools(mcp)
    add_git_tools(mcp)
    add_test_tools(mcp)
    add_doc_tools(mcp)
    add_browser_tools(mcp)
    add_graph_tools(mcp)
    add_perf_tools(mcp)
    add_worker_tools(mcp)
    add_config_tools(mcp)
