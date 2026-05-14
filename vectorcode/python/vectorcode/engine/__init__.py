# Ported from GitHub/NousResearch_vectorcode/repo/run_agent.py
"""VectorCode engine — the agent execution runtime."""
from .agent import AIAgent
from .budget import IterationBudget
from .safety import _SafeWriter, install_safe_stdio, _sanitize_surrogates, _is_destructive_command
from .tool_exec import (
    _should_parallelize_tool_batch,
    execute_tool_calls_sequential,
    execute_tool_calls_concurrent,
    _PARALLEL_SAFE_TOOLS,
    _NEVER_PARALLEL_TOOLS,
    _PATH_SCOPED_TOOLS,
)

__all__ = [
    "AIAgent",
    "IterationBudget",
    "_SafeWriter",
    "install_safe_stdio",
    "_sanitize_surrogates",
    "_is_destructive_command",
    "_should_parallelize_tool_batch",
    "execute_tool_calls_sequential",
    "execute_tool_calls_concurrent",
    "_PARALLEL_SAFE_TOOLS",
    "_NEVER_PARALLEL_TOOLS",
    "_PATH_SCOPED_TOOLS",
]
