# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""RL environment for orchestrator training.

Adapted from IPW's ``environment.py``.  Uses VectorCode's
:class:`~vector.tools._abc.ToolExecutor` for real tool dispatch
(as opposed to IPW's cached-telemetry approach), making it suitable for
both training and evaluation.
"""

from __future__ import annotations

import json
import time
from typing import List, Tuple

from vectorcode.src.vc_core.types import ToolCall
from vectorcode.src.learning.intelligence.orchestrator.types import (
    EpisodeState,
    OrchestratorAction,
    OrchestratorObservation,
)
from vectorcode.src.vc_tools._abc import BaseTool, ToolExecutor

class OrchestratorEnvironment:
    """RL environment that executes tools via VectorCode ``ToolExecutor``.

    Parameters
    ----------
    tools:
        List of :class:`BaseTool` instances available to the agent.
    max_turns:
        Maximum number of turns per episode.
    """

    def __init__(
        self,
        tools: List[BaseTool],
        max_turns: int = 10,
    ) -> None:
        self._tools = tools
        self._executor = ToolExecutor(tools)
        self._max_turns = max_turns

    def reset(self, task: str) -> EpisodeState:
        """Reset the environment for a new episode.

        Args:
            task: The initial task/question.

        Returns:
            A fresh :class:`EpisodeState`.
        """
        return EpisodeState(initial_prompt=task)

    def step(
        self,
        state: EpisodeState,
        action: OrchestratorAction,
    ) -> Tuple[EpisodeState, OrchestratorObservation]:
        """Execute one step: dispatch the tool and observe the result.

        Raises:
            ValueError: If the tool is not available or max turns exceeded.
        """
        available = self.get_available_tools()

        if action.tool_name not in available:
            raise ValueError(
                f"Tool '{action.tool_name}' not available. Available: {available}"
            )

        if state.num_turns() >= self._max_turns:
            raise ValueError(f"Max turns ({self._max_turns}) exceeded")

        # Execute tool via ToolExecutor. ToolExecutor.execute() parses
        # `arguments` with json.loads() -- repr() produces Python literal
        # syntax (single-quoted strings), which is not valid JSON and
        # raised a guaranteed JSONDecodeError for every non-pre-JSON
        # tool_input (the common case for a plain-string argument like a
        # calculator expression). Use json.dumps() instead.
        tool_call = ToolCall(
            id=f"orch_{state.num_turns()}",
            name=action.tool_name,
            arguments=action.tool_input
            if action.tool_input.startswith("{")
            else json.dumps({"expression": action.tool_input}),
        )

        t0 = time.time()
        result = self._executor.execute(tool_call)
        latency = time.time() - t0

        observation = OrchestratorObservation(
            content=result.content,
            latency_seconds=latency,
            cost_usd=result.cost_usd,
            energy_joules=0.0,
            power_watts=0.0,
            tokens=result.usage.get("total_tokens", 0),
        )

        state.add_turn(action, observation)
        return state, observation

    def is_done(self, state: EpisodeState) -> bool:
        """Check if the episode is complete."""
        if state.final_answer is not None:
            return True
        if state.num_turns() >= self._max_turns:
            return True
        return False

    def get_available_tools(self) -> List[str]:
        """Return names of all available tools."""
        return [t.spec.name for t in self._tools]

__all__ = ["OrchestratorEnvironment"]
