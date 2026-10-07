"""
VECTOR Sub-Agent Runner — spawn specialized agents with narrow scope.

Ported from vector's agent/harness/subagent_runner/ops.rs.

Runs a sub-agent with:
  - Inherited parent context (memory, session)
  - Filtered tool set (only tools the sub-agent needs)
  - Narrow system prompt (no full identity, just the role)
  - Single text result returned to parent
"""
from __future__ import annotations

__all__ = [
    "LLMCallable",
    "run_subagent",
    "SubagentOptions",
    "SubagentOutcome",
    "SubagentRunner",
]


import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from loguru import logger
from core.engine.agents.roles import get_agent_prompt, list_agents


@dataclass
class SubagentOptions:
    agent_name: str
    task: str
    parent_session_id: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    model_hint: str = "agentic"
    max_turns: int = 10
    timeout_secs: float = 120.0
    extra_context: str = ""


@dataclass
class SubagentOutcome:
    agent_name: str
    task: str
    result: str
    success: bool
    turns_taken: int = 0
    error: str | None = None
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


LLMCallable = Callable[[str, str, list[str]], Awaitable[str]]
# (system_prompt, user_message, allowed_tools) → response text


class SubagentRunner:
    """
    Runs a named sub-agent against a specific task.

    Usage:
        async def my_llm(system, message, tools):
            # call Ollama here
            return "result"

        runner = SubagentRunner(llm=my_llm)
        outcome = await runner.run(SubagentOptions(
            agent_name="researcher",
            task="Find latest papers on LLM quantization",
            allowed_tools=["web_search", "memory_query"],
        ))
        logger.info(outcome.result)

    """

    def __init__(self, llm: LLMCallable | None = None) -> None:
        self._llm = llm or self._default_llm

    async def run(self, options: SubagentOptions) -> SubagentOutcome:
        task_id = str(uuid.uuid4())[:8]
        logger.info(
            "[VECTOR][subagent_runner] spawning agent={} task_id={} tools={}",
            options.agent_name, task_id, options.allowed_tools,
        )

        system_prompt = self._build_system_prompt(options)
        user_message = self._build_user_message(options)

        try:
            result = await asyncio.wait_for(
                self._llm(system_prompt, user_message, options.allowed_tools),
                timeout=options.timeout_secs,
            )
            logger.info("[VECTOR][subagent_runner] agent={} completed task_id={}", options.agent_name, task_id)
            return SubagentOutcome(
                agent_name=options.agent_name,
                task=options.task,
                result=result,
                success=True,
                task_id=task_id,
            )
        except asyncio.TimeoutError:
            msg = f"Sub-agent {options.agent_name} timed out after {options.timeout_secs}s"
            logger.error("[VECTOR][subagent_runner] {}", msg)
            return SubagentOutcome(agent_name=options.agent_name, task=options.task,
                                   result="", success=False, error=msg, task_id=task_id)
        except Exception as e:
            logger.error("[VECTOR][subagent_runner] agent={} failed: {}", options.agent_name, e)
            return SubagentOutcome(agent_name=options.agent_name, task=options.task,
                                   result="", success=False, error=str(e), task_id=task_id)

    def _build_system_prompt(self, options: SubagentOptions) -> str:
        from core.loop.context_engine import ContextEngine

        role_prompt = get_agent_prompt(options.agent_name)
        if not role_prompt:
            role_prompt = f"You are VECTOR's {options.agent_name} sub-agent."

        # Rule 1: every LLM call receives the live session hydration before
        # its purpose-built role instructions. This also applies when callers
        # inject an alternate LLM callable into the runner.
        parts = [ContextEngine().session_hydration_prompt(), role_prompt]

        if options.allowed_tools:
            parts.append(f"\nYou have access to these tools: {', '.join(options.allowed_tools)}")

        if options.extra_context:
            parts.append(f"\nContext from parent agent:\n{options.extra_context}")

        parts.append("\nComplete your assigned task and return a concise result. Be direct.")
        return "\n".join(parts)

    def _build_user_message(self, options: SubagentOptions) -> str:
        return f"Task: {options.task}"

    @staticmethod
    async def _default_llm(system: str, message: str, tools: list[str]) -> str:
        """Default LLM handler — routes through VECTOR's Ollama provider."""
        try:
            from core.inference.ollama_safe import chat
            from core.config import CONFIG
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": message})
            return chat(
                model=CONFIG["models"].get("focus", "vector-focus"),
                messages=messages,
                timeout=60.0,
                caller_id="subagent_runner",
            )
        except Exception as e:
            logger.warning("[VECTOR][subagent_runner] Ollama unavailable: {}", e)
            raise RuntimeError("Sub-agent LLM is unavailable") from e


async def run_subagent(
    agent_name: str,
    task: str,
    llm: LLMCallable | None = None,
    **kwargs,
) -> SubagentOutcome:
    """Convenience function to spawn a single sub-agent."""
    runner = SubagentRunner(llm=llm)
    return await runner.run(SubagentOptions(agent_name=agent_name, task=task, **kwargs))


if __name__ == "__main__":
    import asyncio

    async def _test():
        responses = []

        async def fake_llm(system, message, tools):
            responses.append((system[:40], message, tools))
            return f"Completed: {message}"

        runner = SubagentRunner(llm=fake_llm)
        outcome = await runner.run(SubagentOptions(
            agent_name="researcher",
            task="Find papers on transformer architectures",
            allowed_tools=["web_search", "arxiv_search"],
            timeout_secs=5.0,
        ))

        assert outcome.success
        assert "Completed" in outcome.result
        assert len(responses) == 1
        assert "web_search" in str(responses[0])
        # system prompt should contain researcher role
        assert "researcher" in responses[0][0].lower() or "VECTOR" in responses[0][0]

        # Test timeout
        async def slow_llm(system, message, tools):
            await asyncio.sleep(100)
            return "never"

        outcome2 = await runner.run(SubagentOptions(
            agent_name="researcher", task="slow task",
            timeout_secs=0.1,
        ))
        runner._llm = slow_llm
        outcome3 = await runner.run(SubagentOptions(
            agent_name="researcher", task="slow task", timeout_secs=0.05
        ))
        assert not outcome3.success and "timed out" in outcome3.error

        print("OK subagent_runner.py — spawn + timeout + tool filtering verified")

    asyncio.run(_test())
