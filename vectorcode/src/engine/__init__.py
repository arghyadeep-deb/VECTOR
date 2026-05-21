"""
Gap 11: This src/engine/ directory is a shim that re-exports from src/vc_engine/.
Prefer importing from vectorcode.src.vc_engine directly.
"""
# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py
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

# Discovery helpers
from typing import List, Optional, Any

def discover_engines() -> List[str]:
    """Return available engine names."""
    from vectorcode.src.vc_core.registry import EngineRegistry
    return list(EngineRegistry._registry.keys()) if hasattr(EngineRegistry, '_registry') else []

def get_engine(name: str) -> Optional[Any]:
    """Get an engine by name."""
    from vectorcode.src.vc_core.registry import EngineRegistry
    return EngineRegistry.get(name) if hasattr(EngineRegistry, 'get') else None

def discover_models() -> List[str]:
    """Return available model names."""
    try:
        import subprocess
        r = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().splitlines()[1:]  # skip header
        return [l.split()[0] for l in lines if l.strip()]
    except Exception:
        return []
from vectorcode.src.engine import _discovery

