# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py (AIAgent class)
"""AIAgent — main agent class. Orchestrates the think→act→observe loop."""
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .budget import IterationBudget
from .safety import install_safe_stdio, _sanitize_surrogates


class AIAgent:
    """AI Agent with tool calling capabilities.

    Manages conversation flow, tool execution, and response handling
    for AI models that support function calling.
    """

    def __init__(
        self,
        # Provider config
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: str = "",
        # Iteration control
        max_iterations: int = 90,
        tool_delay: float = 1.0,
        iteration_budget: Optional[IterationBudget] = None,
        # Toolsets
        enabled_toolsets: Optional[List[str]] = None,
        disabled_toolsets: Optional[List[str]] = None,
        # Session
        session_id: Optional[str] = None,
        session_db=None,
        parent_session_id: Optional[str] = None,
        # Callbacks
        tool_progress_callback: Optional[Callable] = None,
        tool_start_callback: Optional[Callable] = None,
        tool_complete_callback: Optional[Callable] = None,
        thinking_callback: Optional[Callable] = None,
        stream_delta_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        # Prompt / identity
        ephemeral_system_prompt: Optional[str] = None,
        platform: Optional[str] = None,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        # Misc
        save_trajectories: bool = False,
        verbose_logging: bool = False,
        quiet_mode: bool = False,
        credential_pool=None,
        permission_gateway=None,
        memory_manager=None,
        toolset: str = "coding",
        **kwargs,
    ):
        install_safe_stdio()

        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.provider = provider
        self.toolset = toolset
        self.tool_delay = tool_delay
        self.save_trajectories = save_trajectories
        self.verbose_logging = verbose_logging
        self.quiet_mode = quiet_mode
        self.platform = platform
        self.user_id = user_id
        self.user_name = user_name
        self.ephemeral_system_prompt = ephemeral_system_prompt
        self.enabled_toolsets = enabled_toolsets or []
        self.disabled_toolsets = disabled_toolsets or []
        self.credential_pool = credential_pool
        self.permission_gateway = permission_gateway
        self.memory_manager = memory_manager

        # Session
        self.session_id = session_id or str(uuid.uuid4())
        self.session_db = session_db
        self.parent_session_id = parent_session_id

        # Iteration budget — independent per agent
        if iteration_budget is not None:
            self.budget = iteration_budget
        else:
            self.budget = IterationBudget(max_total=max_iterations)

        # Callbacks
        self.tool_progress_callback = tool_progress_callback
        self.tool_start_callback = tool_start_callback
        self.tool_complete_callback = tool_complete_callback
        self.thinking_callback = thinking_callback
        self.stream_delta_callback = stream_delta_callback
        self.status_callback = status_callback

        # Conversation history
        self._history: List[Dict[str, Any]] = []
        self._system_prompt: Optional[str] = None

        # Lazy-import the tool registry to avoid circular imports
        self._registry = None

        logger.debug(f"AIAgent init: model={model!r} session={self.session_id} budget={self.budget}")

    def _get_registry(self):
        if self._registry is None:
            from vectorcode.tools.registry import ToolRegistry
            self._registry = ToolRegistry.global_instance()
        return self._registry

    def _get_provider(self):
        """Resolve the provider transport lazily."""
        try:
            from vectorcode.providers import get_model_router
            return get_model_router()
        except Exception:
            return None

    async def run_conversation(self, user_message: str) -> Dict[str, Any]:
        """Main think→act→observe loop.

        Calls the model, executes any tool calls, feeds results back,
        and repeats until the model stops calling tools or budget is exhausted.
        """
        from .conversation import run_conversation_loop
        return await run_conversation_loop(self, user_message)

    def __repr__(self) -> str:
        return (
            f"AIAgent(model={self.model!r}, session={self.session_id[:8]}, "
            f"budget={self.budget})"
        )
