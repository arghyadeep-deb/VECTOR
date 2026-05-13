# Ported from GitHub/NousResearch_hermes-agent/repo/tools/delegate_tool.py
"""Delegate tool — spawn a subagent with an independent iteration budget."""
import asyncio
import json
import threading
from typing import Any, Optional

from loguru import logger

from .registry import registry


def delegate_task(
    prompt: str,
    model: Optional[str] = None,
    max_iterations: int = 50,
    toolset: str = "coding",
    context: Any = None,
) -> str:
    """Spawn a subagent to handle a subtask with its own iteration budget.

    The subagent runs synchronously (blocks until complete).
    Parent's iteration budget is NOT consumed by subagent iterations.
    """
    from vectorcode.engine import AIAgent

    logger.info(f"Spawning subagent: max_iter={max_iterations} toolset={toolset!r}")

    # Inherit parent's provider/credentials if available
    parent_model = model
    if parent_model is None and context is not None:
        parent_model = getattr(context, "model", None) or ""

    subagent = AIAgent(
        model=parent_model or "",
        max_iterations=max_iterations,
        toolset=toolset,
        credential_pool=getattr(context, "credential_pool", None) if context else None,
        permission_gateway=getattr(context, "permission_gateway", None) if context else None,
        parent_session_id=getattr(context, "session_id", None) if context else None,
    )

    # Run in a new event loop (subagent is independent)
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(subagent.run_conversation(prompt))
        finally:
            loop.close()

    try:
        result = _run()
        return json.dumps({
            "status": result.get("status", "ok"),
            "text": result.get("text", ""),
            "tool_calls_total": result.get("tool_calls_total", 0),
            "iterations_used": result.get("iterations_used", 0),
        })
    except Exception as e:
        logger.error(f"Subagent failed: {e}")
        return json.dumps({"error": str(e)})


# ── Register ──────────────────────────────────────────────────────────────────

registry.register(
    name="delegate_task",
    handler=delegate_task,
    schema={
        "description": "Spawn a subagent to handle a subtask with its own iteration budget. Use for parallelizable or isolated work.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task description for the subagent"},
                "model": {"type": "string", "description": "Model to use (defaults to parent model)"},
                "max_iterations": {"type": "integer", "description": "Max iterations for subagent (default 50)"},
                "toolset": {"type": "string", "description": "Toolset for subagent (default: coding)"},
            },
            "required": ["prompt"],
        },
    },
    toolset="coding",
    risk_level="medium",
    emoji="🤖",
)
